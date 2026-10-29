"""Render recorded Unit 8 evidence into the existing README; never run a model."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
MARKER = '<!-- UNIT8_EVALUATION -->'


def latest(pattern):
    matches = sorted(RESULTS.glob(pattern))
    return matches[-1] if matches else None


def read(path):
    return json.loads(path.read_text())


def link(path, label):
    return f'[{label}]({path.relative_to(ROOT)})'


def block(value):
    return '```json\n' + json.dumps(value, indent=2, ensure_ascii=False) + '\n```\n'


def attack_table(run, assessment):
    verdicts = {r['id']: r for r in assessment['results']}
    lines = ['| ID | HTTP | Guess | Model | Style | Combined | Verdict |',
             '|---|---:|---|---:|---:|---:|---|']
    def score(value):
        return '—' if value is None else f'{value:.6f}'
    for row in run['results']:
        lines.append(f"| {row['id']} | {row['status']} | {row['guess'] or '—'} | "
                     f"{score(row['model_score'])} | {score(row['style_score'])} | "
                     f"{score(row['confidence'])} | {verdicts[row['id']]['verdict']} |")
    return '\n'.join(lines) + '\n'


def trial_table(run):
    names = ['Human false positives', 'Mean score separation', 'Label coverage', 'Persistent appeals', 'Bad input']
    targets = ['≤1/20 AI accusations', 'AI mean − human mean ≥0.20', '3 real labels + 1001 grid points',
               '10/10 persistent, exact, no rescoring', '13 field/media + 4 byte assertions']
    lines = ['| Criterion | Original target | Run 1 | Run 2 | Run 3 | Verdict |',
             '|---|---|---|---|---|---|']
    for index, name in enumerate(names, 1):
        metrics = [next(c['metric'] for c in t['criteria'] if c['criterion'] == index) for t in run['trials']]
        lines.append(f"| {index}. {name} | {targets[index-1]} | {' | '.join(metrics)} | {run['verdicts'][str(index)]} |")
    return '\n'.join(lines) + '\n'


before_path = latest('attack_run_*_before.json')
eval_before_path = latest('eval_*_before.json')
before, evaluation = read(before_path), read(eval_before_path)
assessment = read(RESULTS / 'attack_before_assessment.json')
rows = {r['id']: r for r in before['results']}
audit = [json.loads(line) for line in (ROOT / 'logs/audit.jsonl').read_text().splitlines()]
attack_log = audit[before['metadata_before']['audit_lines']:before['metadata_after']['audit_lines']]
extract = []
for attack_id in ['EV01', 'EV02', 'EV03', 'EV04', 'EV05', 'EV06', 'EV09', 'EV10', 'FP03']:
    extract.append(next(e for e in attack_log if e.get('content_id') == rows[attack_id]['content_id']))
extract.append(next(e for e in attack_log if e.get('http_status') == 429))
(RESULTS / 'unit8-audit-extract.json').write_text(json.dumps(extract, indent=2) + '\n')

sections = [MARKER, '## Attack Run — Before',
'''The official staff ZIP came from the course TF guide after the limiter/log
milestone was committed (`e0fa196`). Only the CSV headers were inspected before
running every input. Source URL, archive hash and both CSV hashes are recorded in
[attack-source.json](results/attack-source.json). No rows were skipped.

**48 HELD / 8 BROKE out of 56**, with no crash or 5xx. For evasion, an accepted
AI-derived specimen that avoids the AI band counts as BROKE: “unsure” fails that
detection objective, but is not a human-authorship finding. False-positive
attacks are BROKE only for an AI accusation; safe rejection is reported separately
as an availability limitation. Injection is judged against its specific requested
override or forgery, not inferred from a low score. These judgment rules stay
the same for the after run.''',
link(before_path, 'Complete actual requests and responses') + ' · [all 56 diagnoses and judgment rules](results/attack_before_assessment.json)',
attack_table(before, assessment),
'''All six injection attempts retained both signals, fixed label text and genuine
audit decisions. GPT-2 computes likelihood rather than executing chat instructions;
an unsure result is not evidence it obeyed the injected text. All 20 malformed
requests were safely refused. RQ02/RQ06 hit the short-text check before creator
validation, so those rows alone do not demonstrate creator validation.

The flood family contains **12 rows**, although its target text says 20. Its
9-word inputs return 400 for the first ten requests, then 429 twice; rejected
requests still consume the quota. The separate 15-request valid-text flood above
demonstrates ten actual decisions followed by five rate-limit refusals.

FP08 is genuine human writing according to staff, but has only 9 words and gets
400 under the preexisting 20-word minimum. That avoids a false accusation while
excluding a legitimate short submission; it is not successful authorship detection.

### Every broken attack: stage and mechanism''']
for row in assessment['results']:
    if row['verdict'] == 'BROKE':
        sections.append(f"**{row['id']} — {', '.join(row['stages'])}.** {row['mechanism']}")
sections += ['''The set contains variants without paired original controls. The scores and
features explain the returned outcome; they do not establish that a particular
typo or edit alone caused a score change.

### Worst attack outcome

EV01 is the accepted AI-derived typo-bearing text closest to the human band.
Its model score is 0.1635, style score 0.601724, and combined score 0.273056:
the dominant predictability signal pulls the result toward human despite the
higher style signal. It receives unsure, not human. Three candidate explanations
considered were model sensitivity to unusual tokens, stylometry treating edits
as human variation, and the wide label mapping; the measured style score and
75% model weight identify the dominant signal/combination as the clearest
explanation. No causal claim about a single edit is made.

Exact staff input and actual response:''', block({'request': rows['EV01']['request']['body'], 'http_status': rows['EV01']['status'], 'response': rows['EV01']['response']}),
'''### Ten actual audit entries

All ten come from this attack run: seven missed evasions, the detected repetitive
evasion, the second-language-writing specimen, and one 429 rejection. Decision
events have all nine required fields; rejections intentionally have no invented
scores. The complete append-only file is [logs/audit.jsonl](logs/audit.jsonl).''',
block(extract), '## Run Log and Verdicts',
'''The original [five criteria](criteria.md) are unchanged from Unit 7 commit
`753217e`. Three complete trials use the same committed 20+20 corpus; no text was
replaced after scoring. It contains externally sourced human excerpts, not the
user's writing, plus disclosed Codex-authored counterparts matched by topic and
length. [Provenance and selection](examples/UNIT8_SOURCES.md) explains the six-work
convenience sample, historical-language confound and possible GPT-2 familiarity.

The evaluator invokes the real model 171 times per phase (57 per trial). Its
observer records call hashes while calling the original function unchanged.
Each trial restarts the actual service before appeals and again before reading
their persisted state. Input failures and appeals show no detector calls.
Restarts reset memory-only rate counters; each ordinary test uses a distinct
creator, and the limiter remains enabled. This is explicit test isolation,
not evidence of durable rate counters.

### Before — three trials''', link(eval_before_path, 'Complete baseline evaluation'), trial_table(evaluation),
'''C1 is MET because each trial has exactly one false accusation out of 20, equal
to the allowed maximum—not because the detector is harmless. The accused item,
`human_16`, is a Constitution excerpt about bills and executive objections:
model 0.9112 + style 0.710726 produces 0.861082, crossing the 0.85 AI threshold.
This is the worst writer-facing result across the criterion corpus.

C2 is MISSED: the mean gap is **−0.077545**, far below +0.20 in every trial.
At **signal one**, human passages average 0.629810 versus AI 0.483850 (gap
−0.145960); **signal two** averages 0.493116 versus 0.597165 (gap +0.104049).
The **combining rule** gives 75% weight to the signal whose ordering is reversed
on this corpus. Predictability and familiar formal wording are not authorship.
The convenience sample cannot establish which training examples GPT-2 memorized.

C3 is MET before the change: all three labels occur on real texts, all 1,001
grid scores map correctly, invalid values are rejected, and 0.51 and 0.95 differ.
C4 is MET because all ten exact appeals retain original decisions through real
restarts in every trial; unknown IDs return 404 and no appeal reruns inference.
C5 is MET because all 13 original field/media assertions plus four body-limit
checks return their specified JSON errors without a model call or new decision.
Rejection log events are permitted by the original target.

### Actual JSON from one baseline trial

The following are selected recorded outputs, not hypothetical examples. Full
requests and all three trials are in the linked JSON.''']
criteria = {c['criterion']: c for c in evaluation['trials'][0]['criteria']}
for n in range(1, 6):
    c = criteria[n]
    value = {k: v for k, v in c.items() if k not in ('grid_points','responses','ai_responses','real_submissions','submissions','appeals','reads_after_restart','cases','unknown')}
    if n == 1:
        value['actual_response'] = next(r for r in c['responses'] if r['response']['guess'] == 'ai')
    elif n == 3:
        value['actual_response'] = next(r for r in c['real_submissions'] if r['response']['guess'] == 'human')
    elif n == 4:
        value['actual_appeal_response'] = c['appeals'][0]
        value['actual_read_after_restart'] = c['reads_after_restart'][0]
    elif n == 5:
        value['actual_case'] = c['cases'][0]
    source = {1:'corpus_metrics',2:'corpus_metrics',3:'coverage',4:'Runner.appeals',5:'Runner.bad_inputs'}[n]
    sections += [f'**Criterion {n}: `run_eval.py::{source}`.**', block(value)]

sections += ['## The Improvement',
'''The diagnosis selects **one reweighting change**: model/style weights from
**0.75/0.25 to 0.50/0.50** in `config.py`. The detector, stylometry, disagreement
guard, thresholds, labels, validation, rate policy and criterion targets stay
fixed. Equal weights reduce the influence of the signal that reverses the
human/AI ordering in the baseline corpus. This is a diagnostic experiment on
the same data, not an independently validated new detector.

Before rerunning, the expected trade is explicit: `human_16` should drop below
the AI threshold, but EV10 may lose its AI label and Joyce may lose the only
human label in the calibration set. The original criterion will be marked
MISSED if label coverage is lost. No threshold adjustment will conceal that
regression.''']

after_path = latest('attack_run_*_after.json')
eval_after_path = latest('eval_*_after.json')
after_assessment_path = RESULTS / 'attack_after_assessment.json'
if after_path and eval_after_path and after_assessment_path.exists():
    after, after_eval, after_assessment = read(after_path), read(eval_after_path), read(after_assessment_path)
    sections += ['### Attack Run — After', link(after_path, 'Complete after requests and responses') + ' · [all after judgments](results/attack_after_assessment.json)', attack_table(after, after_assessment),
                 '### After — three trials', link(eval_after_path, 'Complete after evaluation'), trial_table(after_eval)]
else:
    sections += ['The before evidence is complete and committed before this change. After measurements are pending.']

readme = ROOT / 'README.md'
prefix = readme.read_text().split(MARKER)[0].rstrip()
readme.write_text(prefix + '\n\n' + '\n\n'.join(sections) + '\n')
print('Rendered Unit 8 report from recorded evidence.')
