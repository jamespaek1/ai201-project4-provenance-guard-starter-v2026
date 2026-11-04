#!/usr/bin/env python3
"""Run the frozen Unit 9 operational criteria without stubbing the model.

  .venv/bin/python run_capstone.py --phase before --output results/unit9/before
  .venv/bin/python run_capstone.py --phase after --output results/unit9/after

Owns one local service process at a time and executes the literal ./start.sh
command. Each trial uses a new log directory, ten real submissions in fixed
order, five failure paths, and an appeal/restart/lookup round-trip. Never
overwrites evidence. Clean-clone installation/start verification is a separate
required part of C1, not inferred from these in-checkout startup observations.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import socket
import statistics
import subprocess
import sys
import time

import requests

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "examples/unit9_requests.json"
REASON = "Please review this classroom example."
STAGES = ("model", "style", "scoring", "audit")
RUNTIME_FILES = (
    "criteria.md", "app.py", "config.py", "detector.py", "stylometry.py",
    "scoring.py", "audit.py", "operations.py", "start.sh", "gunicorn.conf.py",
    "requirements.txt", "requirements.lock", "prepare_model.py", "run_capstone.py",
    "examples/unit9_requests.json",
)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite_nonnegative(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value >= 0)


def relative(path):
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_json(path, value):
    # Evidence is initially created once, and only the runner-owned incomplete
    # phase manifest is refreshed between trials. Existing output dirs refuse.
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def read_jsonl(path):
    records, errors = [], []
    if not path.exists():
        return records, [f"missing {relative(path)}"]
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("record is not an object")
            records.append(item)
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(f"line {line_number}: {exc}")
    return records, errors


class Service:
    def __init__(self, trial_dir, port):
        self.trial_dir, self.port = trial_dir, port
        self.log_dir = trial_dir / "logs"
        self.log_dir.mkdir()
        self.url = f"http://127.0.0.1:{port}"
        self.process = None
        self.handle = None
        self.launch_number = 0
        self.session = requests.Session()
        self.session.trust_env = False
        self.events = []

    def start(self):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", self.port)) == 0:
                raise RuntimeError(f"Port {self.port} is occupied; refusing to reuse another service")
        self.launch_number += 1
        server_log = self.trial_dir / f"server-{self.launch_number}.log"
        self.handle = server_log.open("x", encoding="utf-8")
        environment = dict(os.environ)
        environment.update({
            "PORT": str(self.port), "HOST": "127.0.0.1",
            "AI201_LOG_DIR": str(self.log_dir), "AI201_DEBUG": "0",
            "AI201_RATE_LIMITS": "1",
            "HF_HOME": environment.get("HF_HOME", str(ROOT / ".cache/huggingface")),
            "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        })
        record = {"command": "./start.sh", "cwd": str(ROOT), "started_utc": now(),
                  "log_directory": relative(self.log_dir), "server_log": relative(server_log),
                  "ready": False, "health": None}
        started = time.monotonic()
        self.process = subprocess.Popen(["./start.sh"], cwd=ROOT, env=environment,
                                        stdout=self.handle, stderr=subprocess.STDOUT,
                                        start_new_session=True)
        record["pid"] = self.process.pid
        deadline = started + 60
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                record["error"] = f"Service exited with code {self.process.returncode}"
                break
            try:
                response = self.session.get(self.url + "/health", timeout=min(1, max(.01, deadline - time.monotonic())))
                health = response.json()
                if response.status_code == 200 and isinstance(health, dict) and health.get("ok") is True:
                    record.update({"ready": True, "health": health,
                                   "health_request_id": response.headers.get("X-Request-ID")})
                    break
            except (requests.RequestException, ValueError):
                pass
            time.sleep(.1)
        record["elapsed_seconds"] = time.monotonic() - started
        if not record["ready"]:
            record.setdefault("error", "No healthy response within 60 seconds")
        self.events.append(record)
        return record

    def stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=5)
            self.process = None
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    def close(self):
        self.stop()
        self.session.close()

    def call(self, case_id, method, path, payload=None, raw=None):
        body = json.dumps(payload, ensure_ascii=False) if payload is not None else (raw or "")
        record = {"case_id": case_id, "method": method, "path": path,
                  "input_body": body, "content_type": "application/json" if method == "POST" else "",
                  "started_utc": now(), "status": None, "output": None, "request_id": None}
        started = time.monotonic()
        try:
            response = self.session.request(method, self.url + path,
                                            data=body.encode("utf-8") if method == "POST" else None,
                                            headers={"Content-Type": "application/json"} if method == "POST" else {},
                                            timeout=180)
            record.update({"status": response.status_code,
                           "request_id": response.headers.get("X-Request-ID"),
                           "response_content_type": response.headers.get("Content-Type")})
            try:
                record["output"] = response.json()
            except ValueError:
                record["non_json_output"] = response.text
        except requests.RequestException as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        record["elapsed_seconds"] = time.monotonic() - started
        return record


def inspect_record(call, records, expected_status, failure=False, oversized=False):
    """Explicit exact-output assertions, including one-to-one correlation."""
    matches = [r for r in records if call.get("request_id") and r.get("request_id") == call["request_id"]]
    checks = {"http_status": call["status"] == expected_status,
              "request_id_returned": isinstance(call.get("request_id"), str) and bool(call["request_id"]),
              "exactly_one_record": len(matches) == 1}
    if len(matches) != 1:
        return {"passed": False, "checks": checks, "record": None}
    logged = matches[0]
    try:
        timestamp = dt.datetime.fromisoformat(logged.get("timestamp", "").replace("Z", "+00:00"))
        checks["utc_timestamp"] = timestamp.utcoffset() == dt.timedelta(0)
    except (AttributeError, TypeError, ValueError):
        checks["utc_timestamp"] = False
    checks.update({
        "method_path": logged.get("method") == call["method"] and logged.get("path") == call["path"],
        "status_matches": logged.get("status") == call["status"],
        "exact_json_output": isinstance(call.get("output"), dict) and logged.get("output") == call["output"],
        "wall_time": finite_nonnegative(logged.get("duration_seconds")),
        "cpu_time": finite_nonnegative(logged.get("cpu_seconds")),
    })
    recorded_input = logged.get("input", {})
    if not isinstance(recorded_input, dict):
        recorded_input = {}
    body = recorded_input.get("body")
    if oversized:
        checks["input_or_marked_prefix"] = (
            isinstance(body, str) and call["input_body"].startswith(body)
            and len(body.encode("utf-8")) <= 65536 and recorded_input.get("truncated") is True
            and (bool(body) or recorded_input.get("capture_reason") == "body_rejected_before_read")
        )
    else:
        checks["exact_input_body"] = body == call["input_body"] and recorded_input.get("truncated") is False
    checks["content_type"] = recorded_input.get("content_type") == call["content_type"]
    stages = logged.get("stages_seconds", {})
    checks["all_stage_durations"] = isinstance(stages, dict) and all(finite_nonnegative(stages.get(k)) for k in STAGES)
    if failure:
        checks["error_output"] = isinstance(call.get("output"), dict) and bool(call["output"].get("error"))
        checks["no_model_stage"] = isinstance(stages, dict) and stages.get("model") == 0
    return {"passed": all(checks.values()), "checks": checks, "record": logged}


def run_trial(args, number, fixtures, output):
    trial_dir = output / f"trial-{number}"
    trial_dir.mkdir()
    report = {"trial": number, "started_utc": now(), "successful_submissions": [],
              "failure_cases": [], "rate_limit_preliminaries": [], "criteria": {},
              "operation_log": relative(trial_dir / "logs/operations.jsonl"),
              "audit_log": relative(trial_dir / "logs/audit.jsonl")}
    service = Service(trial_dir, args.port)
    prefix = f"unit9-{args.phase}-t{number}"
    try:
        report["startup"] = service.start()
        if not report["startup"]["ready"]:
            raise RuntimeError(report["startup"]["error"])
        for fixture in fixtures:
            call = service.call(fixture["id"], "POST", "/submit",
                                payload={"text": fixture["text"], "creator_id": prefix + "-" + fixture["id"]})
            report["successful_submissions"].append(call)
        cases = [
            ("malformed_json", "/submit", None, '{"text":', 400),
            ("short_input", "/submit", {"text": "Too short.", "creator_id": prefix + "-short"}, None, 400),
            ("oversized_body", "/submit", None, "x" * 65538, 413),
            ("unknown_appeal", "/appeal", {"content_id": "unit9-does-not-exist", "reasoning": REASON}, None, 404),
        ]
        for case_id, path, payload, raw, status in cases:
            call = service.call(case_id, "POST", path, payload=payload, raw=raw)
            call["expected_status"] = status
            report["failure_cases"].append(call)
        burst_started = time.monotonic()
        for index in range(11):
            call = service.call(f"rate_limit_{index + 1}", "POST", "/submit",
                                payload={"text": "Short.", "creator_id": prefix + "-rate"})
            if index < 10:
                report["rate_limit_preliminaries"].append(call)
            else:
                call["expected_status"] = 429
                report["failure_cases"].append(call)
        report["rate_burst_seconds"] = time.monotonic() - burst_started
        first = report["successful_submissions"][0]
        content_id = (first.get("output") or {}).get("content_id")
        original_audit, original_errors = read_jsonl(service.log_dir / "audit.jsonl")
        report["original_decisions"] = [r for r in original_audit if r.get("content_id") == content_id and r.get("status") == "decided"]
        report["original_audit_parse_errors"] = original_errors
        report["appeal"] = service.call("appeal", "POST", "/appeal",
                                         payload={"content_id": content_id or "missing-first-submission", "reasoning": REASON})
        operations_before, operation_errors_before = read_jsonl(service.log_dir / "operations.jsonl")
        report["continuity_operations_before_restart"] = {
            "submission": [r for r in operations_before if first.get("request_id") and r.get("request_id") == first["request_id"]],
            "appeal": [r for r in operations_before if report["appeal"].get("request_id") and r.get("request_id") == report["appeal"]["request_id"]],
        }
        report["operation_parse_errors_before_restart"] = operation_errors_before
        service.stop()
        report["restart"] = service.start()
        if report["restart"]["ready"]:
            report["lookup"] = service.call("lookup_after_restart", "GET", "/content/" + (content_id or "missing-first-submission"))
        else:
            report["lookup"] = {"status": None, "output": None, "error": "Restart not ready"}
    except Exception as exc:
        report["runner_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        service.close()
    report["service_events"] = service.events
    records, parse_errors = read_jsonl(service.log_dir / "operations.jsonl")
    report["operation_record_count"] = len(records)
    report["operation_parse_errors"] = parse_errors
    audit_records, audit_errors = read_jsonl(service.log_dir / "audit.jsonl")
    report["audit_parse_errors"] = audit_errors

    successes = report["successful_submissions"]
    success_checks = [inspect_record(call, records, 200) for call in successes]
    failure_checks = [inspect_record(call, records, call["expected_status"], failure=True,
                                     oversized=call["case_id"] == "oversized_body") for call in report["failure_cases"]]
    preliminary_checks = [inspect_record(call, records, 400, failure=True) for call in report["rate_limit_preliminaries"]]
    startup = report.get("startup", {})
    c1_checks = {"ready": startup.get("ready") is True,
                 "within_60_seconds": finite_nonnegative(startup.get("elapsed_seconds")) and startup.get("elapsed_seconds", 61) <= 60}
    report["criteria"]["C1"] = {"met": all(c1_checks.values()), "checks": c1_checks,
                                   "scope": "Three-trial startup subcheck; clean-clone setup/start evidence is additionally required."}
    report["criteria"]["C2"] = {"met": len(success_checks) == 10 and not parse_errors and all(c["passed"] for c in success_checks),
                                   "complete_records": sum(c["passed"] for c in success_checks), "expected": 10,
                                   "records": success_checks}
    c3_checks = {"all_five_paths": len(failure_checks) == 5 and all(c["passed"] for c in failure_checks),
                 "ten_invalid_preliminaries": len(preliminary_checks) == 10 and all(c["passed"] for c in preliminary_checks),
                 "burst_within_one_minute": report.get("rate_burst_seconds", 61) < 60,
                 "no_parse_errors": not parse_errors}
    report["criteria"]["C3"] = {"met": all(c3_checks.values()), "checks": c3_checks,
                                   "recorded_paths": sum(c["passed"] for c in failure_checks), "expected": 5,
                                   "records": failure_checks, "preliminary_records": preliminary_checks}
    latency_checks = [{"case_id": call["case_id"], "seconds": call["elapsed_seconds"],
                       "met": call["status"] == 200 and finite_nonnegative(call["elapsed_seconds"]) and call["elapsed_seconds"] <= 2}
                      for call in successes]
    report["criteria"]["C4"] = {"met": len(latency_checks) == 10 and all(c["met"] for c in latency_checks),
                                   "maximum_seconds": max((c["seconds"] for c in latency_checks), default=None),
                                   "threshold_seconds": 2.0, "requests": latency_checks}
    first = successes[0] if successes else {}
    first_output = first.get("output") or {}
    content_id = first_output.get("content_id")
    originals = report.get("original_decisions", [])
    after_decisions = [r for r in audit_records if content_id and r.get("content_id") == content_id and r.get("status") == "decided"]
    appeals = [r for r in audit_records if content_id and r.get("content_id") == content_id and r.get("event") == "appeal"]
    appeal_call = report.get("appeal", {})
    lookup = report.get("lookup", {})
    lookup_output = lookup.get("output") or {}
    original = originals[0] if len(originals) == 1 else {}
    operation_snapshots = report.get("continuity_operations_before_restart", {})
    submission_after = [r for r in records if first.get("request_id") and r.get("request_id") == first["request_id"]]
    appeal_after = [r for r in records if appeal_call.get("request_id") and r.get("request_id") == appeal_call["request_id"]]
    appeal_instrumentation = inspect_record(appeal_call, records, 200) if appeal_call else {"passed": False}
    c5_checks = {
        "first_submission_success": first.get("status") == 200 and bool(content_id),
        "one_original_decision": len(originals) == 1,
        "original_matches_submission": bool(original) and all(first_output.get(k) == v for k, v in original.items()),
        "original_audit_unchanged": len(originals) == 1 and after_decisions == originals,
        "appeal_success": appeal_call.get("status") == 200 and (appeal_call.get("output") or {}).get("status") == "under_review",
        "one_exact_appeal": len(appeals) == 1 and appeals[0].get("reasoning") == REASON,
        "restart_ready": report.get("restart", {}).get("ready") is True,
        "lookup_success": lookup.get("status") == 200 and lookup_output.get("status") == "under_review",
        "lookup_original_fields": bool(original) and all(lookup_output.get(k) == v for k, v in original.items() if k != "status"),
        "lookup_exact_appeals": bool(appeals) and lookup_output.get("appeals") == appeals,
        "submission_operation_retained_once_unchanged": len(submission_after) == 1 and submission_after == operation_snapshots.get("submission"),
        "appeal_operation_retained_once_unchanged": len(appeal_after) == 1 and appeal_after == operation_snapshots.get("appeal"),
        "appeal_instrumentation": appeal_instrumentation["passed"],
        "operation_logs_parse": not parse_errors and not report.get("operation_parse_errors_before_restart", []),
        "audit_parses": not audit_errors and not report.get("original_audit_parse_errors", []),
    }
    report["criteria"]["C5"] = {"met": all(c5_checks.values()), "checks": c5_checks,
                                   "original_decision": original, "appeal_events_after_restart": appeals,
                                   "appeal_instrumentation": appeal_instrumentation}
    complete_cost_records = [c["record"] for c in success_checks if c["passed"]]
    if len(complete_cost_records) == 10:
        cpu_mean = statistics.mean(r["cpu_seconds"] for r in complete_cost_records)
        service_mean = statistics.mean(r["duration_seconds"] for r in complete_cost_records)
        client_mean = statistics.mean(c["elapsed_seconds"] for c in successes)
        report["cost"] = {
            "sample_request_ids": [r["request_id"] for r in complete_cost_records], "sample_size": 10,
            "mean_cpu_seconds": cpu_mean, "mean_service_wall_seconds": service_mean,
            "mean_client_wall_seconds": client_mean,
            "100_users_one_submission_each_cpu_seconds": cpu_mean * 100,
            "100_users_one_submission_each_service_wall_seconds_serial": service_mean * 100,
            "100_users_one_submission_each_client_wall_seconds_serial": client_mean * 100,
            "method": "Arithmetic mean of ten sequential real submissions, including the first after readiness. Process CPU spans all serving-worker threads; one sync worker prevents overlapping requests. CPU is compute usage, not cloud dollars. Request clocks exclude setup/startup and final operation-log append; client wall includes HTTP overhead and append.",
            "startup_seconds_excluded": startup.get("elapsed_seconds"),
            "restart_startup_seconds_excluded": report.get("restart", {}).get("elapsed_seconds"),
            "failures_and_other_routes_excluded": True,
        }
    else:
        report["cost"] = {"error": "Ten complete successful operation records required; no missing data imputed", "sample_size": len(complete_cost_records)}
    report["finished_utc"] = now()
    write_json(trial_dir / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, help="Evidence label: before, after, or a new reproduction label")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=5057)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,30}", args.phase):
        parser.error("phase must be 1–30 letters, digits, hyphens or underscores")
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    output = args.output.resolve()
    if output.exists():
        parser.error("Output already exists; choose a new directory to preserve evidence")
    fixture_document = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixtures = fixture_document["requests"]
    if len(fixtures) != 10 or len({f["id"] for f in fixtures}) != 10 or not all(40 <= len(f["text"].split()) <= 100 for f in fixtures):
        raise ValueError("Frozen fixtures must contain ten distinct IDs and 40–100-word texts")
    output.mkdir(parents=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    packages = {}
    for name in ("flask", "flask-limiter", "gunicorn", "torch", "transformers", "requests"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    summary = {"phase": args.phase, "started_utc": now(), "git_revision": revision,
               "git_status_at_start": status,
               "file_sha256": {name: sha256(ROOT / name) for name in RUNTIME_FILES if (ROOT / name).is_file()},
               "environment": {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
                               "packages": packages, "worker_model": "one Gunicorn sync worker; sequential HTTP requests"},
               "protocol": "Three fresh-worker trials with warm disk cache; ten fixed real submissions before any other inference; unchanged code and fixtures between trials; no mocked model calls.",
               "clean_clone_requirement": "PENDING EXTERNAL EVIDENCE: additionally verify documented setup and literal start command in a separate clean clone with a fresh venv. Trial C1 checks startup only.",
               "trials": []}
    write_json(output / "summary.json", summary)
    for number in range(1, 4):
        print(f"{args.phase}: trial {number}/3 starting", flush=True)
        trial = run_trial(args, number, fixtures, output)
        summary["trials"].append({"trial": number, "report": relative(output / f"trial-{number}/report.json"),
                                  "startup_seconds": trial.get("startup", {}).get("elapsed_seconds"),
                                  "startup_model_loaded": trial.get("startup", {}).get("health", {}).get("detector_loaded") if trial.get("startup", {}).get("health") else None,
                                  "maximum_request_seconds": trial["criteria"]["C4"]["maximum_seconds"],
                                  "criteria": {key: value["met"] for key, value in trial["criteria"].items()},
                                  "cost": trial["cost"],
                                  **({"runner_error": trial["runner_error"]} if "runner_error" in trial else {})})
        write_json(output / "summary.json", summary)
        print(json.dumps(summary["trials"][-1], ensure_ascii=False), flush=True)
    summary["criterion_trial_verdicts"] = {key: "MET" if all(t["criteria"][key] for t in summary["trials"]) else "MISSED"
                                             for key in ("C1", "C2", "C3", "C4", "C5")}
    summary["finished_utc"] = now()
    current_hashes = {name: sha256(ROOT / name) for name in summary["file_sha256"]}
    summary["runtime_unchanged_during_phase"] = current_hashes == summary["file_sha256"]
    write_json(output / "summary.json", summary)
    print(json.dumps({"verdicts": summary["criterion_trial_verdicts"], "runtime_unchanged": summary["runtime_unchanged_during_phase"],
                      "clean_clone_requirement": summary["clean_clone_requirement"]}), flush=True)
    return 0 if summary["runtime_unchanged_during_phase"] and not any("runner_error" in t for t in summary["trials"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
