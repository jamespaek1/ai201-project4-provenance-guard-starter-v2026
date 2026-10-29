#!/usr/bin/env python3
"""Measure all five frozen criteria in three real, deterministic HTTP trials.

Use --manage-service to own and restart the local service and record actual model
calls without mocking it. The endpoint must be free before this mode starts:
  python run_eval.py --label before --url http://127.0.0.1:5057 --manage-service
  python run_eval.py --label after  --url http://127.0.0.1:5057 --manage-service

Without management, missing restart/call-observer evidence is a miss, not a pass.
The same input normally gives the same score; all three trials are still run.
"""
import argparse
import datetime as dt
from decimal import Decimal
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

import config
import scenarios
import scoring

ROOT = Path(__file__).resolve().parent
RUNTIME_FILES = ['app.py', 'config.py', 'detector.py', 'stylometry.py', 'scoring.py',
                 'audit.py', 'criteria.md', 'scenarios.py', 'run_eval.py',
                 'examples/unit8_corpus.json', 'examples/calibration.json']


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hashes():
    return {name: digest(ROOT / name) for name in RUNTIME_FILES}


def serve_observed(args):
    """Test observer: count calls while always invoking the real detector."""
    import app
    import detector
    actual_model_signal = detector.model_signal
    trace_path = Path(args.trace)

    def observed(text):
        with trace_path.open('a') as handle:
            handle.write(json.dumps({'event': 'model_call', 'timestamp': now(),
                                     'pid': os.getpid(), 'text_sha256': hashlib.sha256(text.encode()).hexdigest()}) + '\n')
        return actual_model_signal(text)

    detector.model_signal = observed
    parsed = urlparse(args.url)
    app.app.run(host=parsed.hostname, port=parsed.port, debug=False, use_reloader=False)


class Service:
    def __init__(self, args, stem):
        self.args = args
        self.process = None
        self.server_handle = None
        self.trace_path = Path(str(stem) + '_model_calls.jsonl')
        self.server_path = Path(str(stem) + '_server.log')
        self.events = []
        if args.manage_service:
            self.trace_path.touch(exist_ok=False)
            self.server_handle = self.server_path.open('x')

    def count_calls(self):
        if not self.args.manage_service:
            return None
        return len(self.trace_path.read_text().splitlines())

    def start(self):
        if not self.args.manage_service:
            return
        parsed = urlparse(self.args.url)
        with socket.socket() as probe:
            if probe.connect_ex((parsed.hostname, parsed.port)) == 0:
                raise RuntimeError('Managed-service port is occupied; stop the existing service first.')
        command = [sys.executable, str(ROOT / 'run_eval.py'), '--serve-observed',
                   '--url', self.args.url, '--trace', str(self.trace_path)]
        environment = dict(os.environ)
        environment.update({'AI201_DEBUG': '0', 'HF_HOME': str(ROOT / '.cache/huggingface'),
                            'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
                            'HF_HUB_DISABLE_PROGRESS_BARS': '1'})
        self.process = subprocess.Popen(command, cwd=ROOT, env=environment,
                                        stdout=self.server_handle, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        import requests
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f'Service exited {self.process.returncode}; see {self.server_path}')
            try:
                response = requests.get(self.args.url + '/health', timeout=1)
                if response.status_code == 200:
                    self.events.append({'event': 'service_started', 'pid': self.process.pid,
                                        'timestamp': now(), 'health': response.json()})
                    return
            except requests.RequestException:
                pass
            time.sleep(0.2)
        raise RuntimeError('Service did not start within 30 seconds')

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            pid = self.process.pid
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.events.append({'event': 'service_stopped', 'pid': pid, 'timestamp': now()})
        self.process = None

    def restart(self):
        if not self.args.manage_service:
            return False
        self.stop()
        self.start()
        return True

    def close(self):
        self.stop()
        if self.server_handle is not None:
            self.server_handle.close()


class Runner:
    def __init__(self, args, service, report):
        self.args, self.service, self.report = args, service, report

    def call(self, method, route, payload=None, raw=None, media='application/json', chunked=False):
        import requests
        headers = {}
        kwargs = {}
        sent = None
        if payload is not None:
            headers['Content-Type'] = media
            encoded = json.dumps(payload, ensure_ascii=False).encode()
            kwargs['data'] = encoded
            sent = {'json': payload}
        elif raw is not None:
            headers['Content-Type'] = media
            kwargs['data'] = (part for part in [raw]) if chunked else raw
            if chunked:
                headers['Transfer-Encoding'] = 'chunked'
            sent = {'raw_utf8': raw.decode(errors='replace')} if len(raw) <= 1024 else {
                'byte_length': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'construction': 'See scenarios.bad_input_cases for exact bytes'}
        record = {'method': method, 'route': route, 'request': sent,
                  'request_headers': headers, 'started_utc': now()}
        started = time.monotonic()
        try:
            response = requests.request(method, self.args.url + route, headers=headers,
                                        timeout=self.args.timeout, **kwargs)
            record.update({'http_status': response.status_code,
                           'response_content_type': response.headers.get('Content-Type')})
            try:
                record['response'] = response.json()
            except ValueError:
                record['response'] = None
                record['non_json_response'] = response.text
        except requests.RequestException as exc:
            record.update({'http_status': None, 'response': None,
                           'error': f'{type(exc).__name__}: {exc}'})
        record['elapsed_seconds'] = round(time.monotonic() - started, 6)
        return record

    def log(self):
        result = self.call('GET', '/log')
        if result['http_status'] != 200 or not isinstance(result['response'], dict):
            raise RuntimeError('Cannot read complete audit log')
        return result['response']['entries']

    def submit_rows(self, rows, prefix):
        records = []
        for index, specimen in enumerate(rows):
            result = self.call('POST', '/submit', {'text': specimen['text'], 'creator_id': f'{prefix}-{index}'})
            result['specimen_id'] = specimen['id']
            records.append(result)
            print(f"  {prefix} {index + 1}/{len(rows)}: HTTP {result['http_status']}", flush=True)
        return records

    def appeals(self, trial, prefix):
        sample = scenarios.calibration()[0]
        submissions = self.submit_rows([sample] * 10, prefix + '-appeal')
        ids = [(r.get('response') or {}).get('content_id') for r in submissions]
        originals = {row['content_id']: row for row in self.log() if row.get('content_id') in ids and row.get('status') == 'decided'}
        pre_restart = self.service.restart()
        calls_before = self.service.count_calls()
        health_before = self.call('GET', '/health')
        appeals = []
        before_unknown = None
        for index, content_id in enumerate(ids):
            reason = f'  Synthetic evaluation appeal {trial}/{index + 1}: please review the process notes.\nThis is a test, not a claim of human authorship.  '
            result = self.call('POST', '/appeal', {'content_id': content_id, 'reasoning': reason})
            appeals.append(result)
        before_unknown = self.log()
        unknown = self.call('POST', '/appeal', {'content_id': prefix + '-unknown', 'reasoning': 'Synthetic unknown-ID check.'})
        after_unknown = self.log()
        unknown_no_appeal = all(e.get('event') == 'rejected' for e in after_unknown[len(before_unknown):])
        calls_after = self.service.count_calls()
        persisted_restart = self.service.restart()
        reads = [self.call('GET', '/content/' + str(content_id)) for content_id in ids]
        final_log = self.log()
        successes = 0
        for index, (submission, appeal, read) in enumerate(zip(submissions, appeals, reads)):
            content_id = ids[index]
            rows = [e for e in final_log if e.get('content_id') == content_id]
            decision_rows = [e for e in rows if e.get('status') == 'decided']
            appeal_rows = [e for e in rows if e.get('event') == 'appeal']
            expected_reason = appeal['request']['json']['reasoning']
            body = read.get('response') or {}
            good = (submission['http_status'] == 200 and appeal['http_status'] == 200
                    and (appeal.get('response') or {}).get('status') == 'under_review'
                    and read['http_status'] == 200 and body.get('status') == 'under_review'
                    and decision_rows == [originals.get(content_id)] and len(appeal_rows) == 1
                    and appeal_rows[0].get('reasoning') == expected_reason
                    and body.get('guess') == originals.get(content_id, {}).get('guess')
                    and body.get('label') == originals.get(content_id, {}).get('label'))
            successes += bool(good)
        no_rescoring = calls_before is not None and calls_before == calls_after
        passed = (len(set(ids)) == 10 and None not in ids and successes == 10
                  and pre_restart and persisted_restart and no_rescoring
                  and unknown['http_status'] == 404 and unknown_no_appeal)
        return {'criterion': 4, 'passed': bool(passed), 'metric': f'{successes}/10 persistent exact appeals',
                'successful_appeals': successes, 'restart_before_appeals': pre_restart,
                'restart_after_appeals': persisted_restart, 'model_calls_before': calls_before,
                'model_calls_after': calls_after, 'no_rescoring_observed': no_rescoring,
                'unknown_no_appeal': unknown_no_appeal, 'health_before_appeals': health_before,
                'submissions': submissions, 'appeals': appeals, 'unknown': unknown,
                'reads_after_restart': reads}, next((i for i in ids if i), 'missing-known-id')

    def bad_inputs(self, prefix, content_id):
        results = []
        for case in scenarios.bad_input_cases(prefix + '-bad', content_id):
            prior = self.log()
            calls_before = self.service.count_calls()
            kwargs = {'media': case.get('media', 'application/json'), 'chunked': case.get('chunked', False)}
            if 'json' in case:
                kwargs['payload'] = case['json']
            else:
                kwargs['raw'] = case['raw']
            result = self.call('POST', case.get('route', '/submit'), **kwargs)
            after = self.log()
            calls_after = self.service.count_calls()
            extra = after[len(prior):]
            no_success = after[:len(prior)] == prior and all(e.get('event') == 'rejected' for e in extra)
            no_inference = calls_before is not None and calls_before == calls_after
            passed = (result['http_status'] == case['expected'] and isinstance(result.get('response'), dict)
                      and bool(result['response'].get('error')) and no_success and no_inference)
            result.update({'case': case['name'], 'expected_status': case['expected'],
                           'audit_events_added': extra, 'no_successful_event': no_success,
                           'model_calls_before': calls_before, 'model_calls_after': calls_after,
                           'no_inference_observed': no_inference, 'passed': passed})
            results.append(result)
        passed_count = sum(r['passed'] for r in results)
        return {'criterion': 5, 'passed': passed_count == len(results),
                'metric': f'{passed_count}/{len(results)} assertions', 'cases': results}


def valid_decisions(records):
    return all(r['http_status'] == 200 and isinstance(r.get('response'), dict)
               and r['response'].get('guess') in ('human', 'unsure', 'ai')
               and isinstance(r['response'].get('confidence'), (int, float))
               and math.isfinite(r['response']['confidence'])
               and 0 <= r['response']['confidence'] <= 1 for r in records)


def corpus_metrics(human, ai):
    valid_human = len(human) == 20 and valid_decisions(human)
    false_positives = sum((r.get('response') or {}).get('guess') == 'ai' for r in human)
    c1 = {'criterion': 1, 'passed': valid_human and false_positives <= 1,
          'metric': f'{false_positives}/20 flagged ai', 'valid_20_human_responses': valid_human,
          'false_positives': false_positives, 'responses': human}
    complete = valid_human and len(ai) == 20 and valid_decisions(ai)
    # Compare decimal values actually transmitted by the API without rounding
    # displayed means, avoiding a binary .70-.50 boundary artifact.
    mean_human = sum(Decimal(str(r['response']['confidence'])) for r in human) / 20 if complete else None
    mean_ai = sum(Decimal(str(r['response']['confidence'])) for r in ai) / 20 if complete else None
    gap = mean_ai - mean_human if complete else None
    c2 = {'criterion': 2, 'passed': complete and gap >= Decimal('.20'),
          'metric': f'{gap:.6f} mean gap' if complete else 'Incomplete responses',
          'human_mean': float(mean_human) if complete else None,
          'ai_mean': float(mean_ai) if complete else None, 'mean_gap': float(gap) if complete else None,
          'comparison': 'Decimal arithmetic on returned scores; no rounding before comparison',
          'human_response_reference': 'criterion 1 of this same trial', 'ai_responses': ai}
    return c1, c2


def coverage(records):
    grid = []
    failures = []
    for index in range(1001):
        score = index / 1000
        expected = 'ai' if score >= config.AI_THRESHOLD else ('human' if score <= config.HUMAN_THRESHOLD else 'unsure')
        try:
            guess, label = scoring.score_to_label(score)
            good = guess == expected and label == scoring.LABEL_TEXT[expected]
            grid.append([score, guess])
        except Exception as exc:
            good = False
            grid.append([score, f'{type(exc).__name__}: {exc}'])
        if not good:
            failures.append(score)
    invalid = []
    for name, value in [('NaN', float('nan')), ('positive infinity', float('inf')),
                        ('negative infinity', -float('inf')), ('below zero', -.001), ('above one', 1.001)]:
        rejected = False
        try:
            scoring.score_to_label(value)
        except (ValueError, TypeError):
            rejected = True
        invalid.append({'input': name, 'rejected': rejected})
    distinct = scoring.score_to_label(.51)[0] != scoring.score_to_label(.95)[0]
    seen = sorted({(r.get('response') or {}).get('guess') for r in records if (r.get('response') or {}).get('guess')})
    thresholds_valid = 0 <= config.HUMAN_THRESHOLD < config.AI_THRESHOLD <= 1
    passed = thresholds_valid and valid_decisions(records) and set(seen) == {'human', 'unsure', 'ai'} and not failures and distinct and all(v['rejected'] for v in invalid)
    return {'criterion': 3, 'passed': bool(passed), 'metric': f'{len(seen)}/3 labels; {1001-len(failures)}/1001 grid',
            'labels_observed': seen, 'real_submissions': records,
            'thresholds': {'human': config.HUMAN_THRESHOLD, 'ai': config.AI_THRESHOLD},
            'label_text': scoring.LABEL_TEXT, 'grid_points': grid, 'grid_failures': failures,
            'scores_0_51_and_0_95_differ': distinct, 'invalid_scores': invalid,
            'grid_producer': 'run_eval.py::coverage -> scoring.py::score_to_label'}


def persist(report, stem):
    """Checkpoint after each criterion group; never reuse an earlier run name."""
    path = Path(str(stem) + '.json')
    temporary = Path(str(path) + '.tmp')
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temporary.replace(path)


def markdown(report):
    lines = [f"# Unit 8 criterion run — {report['label']}", '',
             '- Producer: `run_eval.py::main`, using `scenarios.py` and real local HTTP.',
             '- The observer counts calls to the unchanged actual model; no model is mocked.',
             '- Scores may be identical across three trials because inference is deterministic.', '',
             '| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |', '|---|---|---|---|---|---|']
    for spec in scenarios.SCENARIOS:
        values = [next((c for c in t['criteria'] if c['criterion'] == spec['criterion']), None) for t in report['trials']]
        met = report.get('status') == 'complete' and len(values) == 3 and all(v and v['passed'] for v in values)
        metrics = [v['metric'] if v else 'Incomplete' for v in values]
        metrics += ['Incomplete'] * (3 - len(metrics))
        lines.append(f"| {spec['criterion']}. {spec['name']} | {spec['target']} | {' | '.join(metrics)} | {'MET' if met else 'MISSED'} |")
    lines += ['', 'Full requests, HTTP responses, call observations, score-grid results and lifecycle evidence are in the paired JSON file.', '',
              '## Actual output from the first trial', '']
    if report['trials']:
        for criterion in report['trials'][0]['criteria']:
            number = criterion['criterion']
            compact = {k: v for k, v in criterion.items() if k not in ('grid_points', 'responses', 'ai_responses', 'real_submissions', 'submissions', 'appeals', 'reads_after_restart', 'cases')}
            source = {'1': 'corpus_metrics', '2': 'corpus_metrics', '3': 'coverage', '4': 'Runner.appeals', '5': 'Runner.bad_inputs'}[str(number)]
            lines += [f'### Criterion {number}', '', f'Producer: `run_eval.py::{source}`.', '', '```json', json.dumps(compact, indent=2), '```', '']
    if report.get('error'):
        lines += ['## Interrupted run', '', report['error'], '']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='before')
    parser.add_argument('--url', default=f'http://{config.HOST}:{config.PORT}')
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--manage-service', action='store_true')
    parser.add_argument('--serve-observed', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--trace', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve_observed:
        serve_observed(args)
        return
    if args.trials != 3:
        parser.error('This frozen evaluation requires exactly three trials.')
    if not args.label.replace('-', '').replace('_', '').isalnum():
        parser.error('Use a simple label containing letters, digits, hyphens or underscores.')
    parsed = urlparse(args.url)
    if args.manage_service and (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or not parsed.port):
        parser.error('Managed service requires an explicit loopback HTTP port.')
    problems = scenarios.validate()
    if problems:
        raise SystemExit('\n'.join(problems))
    # A tracked, unchanged corpus is required before the first inference.
    corpus_relative = str(scenarios.CORPUS.relative_to(ROOT))
    committed = subprocess.run(['git', 'show', 'HEAD:' + corpus_relative], cwd=ROOT, capture_output=True)
    if committed.returncode or committed.stdout != scenarios.CORPUS.read_bytes():
        raise SystemExit('Commit the frozen corpus before evaluation; no model call was made.')
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d_%H%M%S_%f')
    config.RESULTS_DIR.mkdir(exist_ok=True)
    stem = config.RESULTS_DIR / f'eval_{stamp}_{args.label}'
    if Path(str(stem) + '.json').exists():
        raise SystemExit('Refusing to overwrite evidence.')
    service = Service(args, stem)
    report = {'label': args.label, 'started_utc': now(), 'status': 'in_progress',
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'source_hashes_before': hashes(), 'criteria_sha256': digest(ROOT/'criteria.md'),
              'corpus_sha256': digest(scenarios.CORPUS), 'url': args.url,
              'managed_service': args.manage_service, 'model_observer': 'Call-only wrapper; invokes original detector.model_signal without changing input/output.',
              'packages': {name: importlib.metadata.version(name) for name in ['Flask', 'torch', 'transformers', 'Flask-Limiter']},
              'trials': [], 'service_events': service.events}
    persist(report, stem)
    runner = Runner(args, service, report)
    corpus = scenarios.load_corpus()
    failure = None
    try:
        service.start()
        report['initial_health'] = runner.call('GET', '/health')
        if not (report['initial_health'].get('response') or {}).get('rate_limiting'):
            raise RuntimeError('Evaluation requires rate limiting enabled.')
        for trial in range(1, 4):
            print(f'Beginning trial {trial}/3 ({args.label})', flush=True)
            prefix = f'eval-{stamp[-13:]}-{args.label[:12]}-t{trial}'
            current = {'trial': trial, 'started_utc': now(), 'criteria': []}
            report['trials'].append(current)
            human = runner.submit_rows(corpus['human'], prefix + '-human')
            ai = runner.submit_rows(corpus['ai'], prefix + '-ai')
            current['criteria'].extend(corpus_metrics(human, ai))
            persist(report, stem)
            current['criteria'].append(coverage(runner.submit_rows(scenarios.calibration(), prefix + '-coverage')))
            persist(report, stem)
            appeal_result, known_id = runner.appeals(trial, prefix)
            current['criteria'].append(appeal_result)
            persist(report, stem)
            current['criteria'].append(runner.bad_inputs(prefix, known_id))
            current['finished_utc'] = now()
            print('Trial verdicts: ' + ', '.join(f"C{c['criterion']} {'MET' if c['passed'] else 'MISSED'}" for c in current['criteria']), flush=True)
            persist(report, stem)
        report['status'] = 'complete'
    except Exception as exc:
        failure = exc
        report['status'] = 'interrupted'
        report['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        service.close()
        report['finished_utc'] = now()
        report['source_hashes_after'] = hashes()
        report['source_unchanged_during_trials'] = report['source_hashes_before'] == report['source_hashes_after']
        if not report['source_unchanged_during_trials']:
            report['status'] = 'invalidated_source_changed'
        report['audit_sha256_final'] = digest(config.AUDIT_LOG) if config.AUDIT_LOG.exists() else None
        report['model_call_count'] = service.count_calls()
        report['verdicts'] = {str(s['criterion']): ('MET' if report['status'] == 'complete' and len(report['trials']) == 3 and all(
            any(c['criterion'] == s['criterion'] and c['passed'] for c in t['criteria']) for t in report['trials']) else 'MISSED') for s in scenarios.SCENARIOS}
        persist(report, stem)
        Path(str(stem) + '.md').write_text(markdown(report))
        print(f'Wrote {stem}.json and .md', flush=True)
    if failure:
        raise SystemExit(f'Evaluation interrupted, retained evidence: {failure}')


if __name__ == '__main__':
    main()
