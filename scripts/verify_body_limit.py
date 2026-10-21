"""Verify final body-limit fix over real HTTP, preserving separate evidence."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:5057"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", default="evidence/07-body-limit-regression.json")
parser.add_argument("--include-chunked", action="store_true")
args = parser.parse_args()
OUT = ROOT / args.output
if OUT.exists():
    raise SystemExit("Preserve existing evidence; refusing to overwrite this run.")


def call(method, route, body=None, content_type="application/json", chunked=False):
    command = ["curl", "--silent", "--show-error", "--max-time", "120",
               "-X", method, BASE + route]
    if body is not None:
        command += ["-H", "Content-Type: " + content_type, "--data-binary", "@-"]
        if chunked:
            command += ["-H", "Transfer-Encoding: chunked"]
    command += ["--write-out", "\n%{http_code}"]
    result = subprocess.run(command, input=body, capture_output=True, check=True)
    response, status = result.stdout.decode().rsplit("\n", 1)
    return {"method": method, "route": route, "http_status": int(status),
            "content_type": content_type if body is not None else None,
            "transfer_encoding": "chunked" if chunked else "Content-Length",
            "body_bytes": len(body) if body is not None else 0,
            "body_sha256": hashlib.sha256(body).hexdigest() if body is not None else None,
            "response": json.loads(response)}


def json_call(method, route, payload):
    result = call(method, route, json.dumps(payload).encode())
    result["request"] = payload
    return result


def log_hash():
    return hashlib.sha256((ROOT / "logs/audit.jsonl").read_bytes()).hexdigest()


report = {
    "scope": "Real HTTP regression after final body-limit fix; no model mocks. Prior calibration is preserved separately.",
    "started_utc": datetime.now(timezone.utc).isoformat(),
    "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "app_sha256": hashlib.sha256((ROOT / "app.py").read_bytes()).hexdigest(),
    "health_before": call("GET", "/health"),
    "audit_sha256_before_rejections": log_hash(),
    "oversized": [],
}
assert report["health_before"]["response"]["detector_loaded"] is False, "Start a fresh service first."
for chunked in ((False, True) if args.include_chunked else (False,)):
    for route in ("/submit", "/appeal"):
        for media in ("application/json", "text/plain"):
            body = b'{"padding":"' + b"x" * 70000 + b'"}'
            result = call("POST", route, body, media, chunked=chunked)
            assert result["http_status"] == 413, result
            assert result["response"]["error"] == "payload_too_large", result
            report["oversized"].append(result)
report["exact_limit_non_json"] = call("POST", "/submit", b"x" * 65536, "text/plain")
assert report["exact_limit_non_json"]["http_status"] == 415
if args.include_chunked:
    report["exact_limit_chunked"] = call("POST", "/submit", b"x" * 65536, "text/plain", chunked=True)
    assert report["exact_limit_chunked"]["http_status"] == 415
    report["one_byte_over_chunked"] = call("POST", "/submit", b"x" * 65537, "text/plain", chunked=True)
    assert report["one_byte_over_chunked"]["http_status"] == 413
report["ping"] = json_call("POST", "/ping", {"message": "body-limit regression"})
assert report["ping"]["http_status"] == 200 and report["ping"]["response"]["ok"] is True
prior = json.loads((ROOT / "examples/sample-appeal.json").read_text())
report["prior_appeal_after_restart"] = call("GET", "/content/" + prior["content_id"])
assert report["prior_appeal_after_restart"]["response"]["status"] == "under_review"
report["health_after_rejections"] = call("GET", "/health")
report["audit_sha256_after_rejections"] = log_hash()
assert report["health_after_rejections"]["response"]["detector_loaded"] is False
assert report["audit_sha256_after_rejections"] == report["audit_sha256_before_rejections"]

# Check a positive path too: the cached-body guard must still permit JSON parsing.
payload = json.loads((ROOT / "examples/sample-submit.json").read_text())
payload["creator_id"] = "body-limit-regression"
report["valid_submit"] = json_call("POST", "/submit", payload)
assert report["valid_submit"]["http_status"] == 200, report["valid_submit"]
assert report["valid_submit"]["response"]["guess"] == "ai"
content_id = report["valid_submit"]["response"]["content_id"]
report["valid_appeal"] = json_call("POST", "/appeal", {
    "content_id": content_id,
    "reasoning": "Synthetic regression appeal verifying JSON parsing after the body-size fix.",
})
assert report["valid_appeal"]["http_status"] == 200
report["content"] = call("GET", "/content/" + content_id)
assert report["content"]["response"]["status"] == "under_review"
report["health_after_positive_path"] = call("GET", "/health")
assert report["health_after_positive_path"]["response"]["detector_loaded"] is True
assert report["health_after_positive_path"]["response"]["log_entries"] == report["health_before"]["response"]["log_entries"] + 2
report["audit_sha256_final"] = log_hash()
report["finished_utc"] = datetime.now(timezone.utc).isoformat()
report["status"] = "passed"
OUT.write_text(json.dumps(report, indent=2) + "\n")
print(f"Passed: {len(report['oversized'])} oversized requests, inclusive byte boundary, unchanged control, durable prior appeal, real submit and appeal.")
