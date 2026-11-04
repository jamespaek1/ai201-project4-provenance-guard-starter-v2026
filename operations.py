"""Per-request operational evidence for the local, single-worker service.

Install immediately after constructing Flask so this before-request hook runs
before body validation, and this after-request hook runs after later hooks.
Durations stop before serializing/appending the operation itself: they measure
server handling, not network transit or the cost of writing this log. Process
CPU time is attributable to a request only for the documented sequential,
single-worker execution; it is not a monetary charge or a per-thread timer.
"""

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
import time
import uuid

from flask import g, has_request_context, request

import config


BODY_LIMIT = 64 * 1024
STAGES = ("model", "style", "scoring", "audit")
_lock = threading.Lock()


def _input_snapshot():
    """Use the size guard's cached bytes, never reread a rejected stream."""
    raw = request.__dict__.get("_cached_data")
    declared_length = request.content_length
    result = {
        "content_type": request.content_type,
        "body": "",
        "truncated": False,
        "content_length": declared_length,
    }
    if raw is None:
        # Werkzeug rejects known oversized Content-Length before reading the
        # body. An explicitly omitted prefix is safer than bypassing that guard.
        if declared_length is not None and declared_length > BODY_LIMIT:
            result.update(truncated=True, capture_reason="body_rejected_before_read")
        elif declared_length or request.environ.get("wsgi.input_terminated"):
            result.update(truncated=True, capture_reason="body_not_cached")
        return result

    prefix = raw[:BODY_LIMIT]
    result["truncated"] = len(raw) > BODY_LIMIT or (
        declared_length is not None and declared_length > len(prefix)
    )
    try:
        result["body"] = prefix.decode("utf-8")
    except UnicodeDecodeError:
        result["body"] = prefix.decode("utf-8", errors="replace")
        # Preserve the exact captured bytes if the input is invalid UTF-8 or a
        # truncation boundary splits a multibyte character.
        result["body_base64"] = base64.b64encode(prefix).decode("ascii")
        result["capture_reason"] = "non_utf8_prefix"
    return result


def _output_snapshot(response):
    if response.is_json:
        try:
            return response.get_json()
        except (ValueError, TypeError):
            pass
    raw = response.get_data()
    return {
        "content_type": response.content_type,
        "body": raw[:BODY_LIMIT].decode("utf-8", errors="replace"),
        "truncated": len(raw) > BODY_LIMIT,
    }


def _append(record):
    # Resolve at request time so isolated tests and separate trial log paths
    # cannot accidentally append to the repository's historical audit evidence.
    path = Path(getattr(config, "OPERATIONS_LOG", config.LOG_DIR / "operations.jsonl"))
    line = json.dumps(record, ensure_ascii=False, allow_nan=False)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


@contextmanager
def stage(name):
    """Accumulate stage wall time, including a stage that raises an exception."""
    if name not in STAGES:
        raise ValueError(f"Unknown operational stage: {name}")
    if not has_request_context() or not hasattr(g, "_operation"):
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = max(0.0, time.perf_counter() - started)
        g._operation["stages_seconds"][name] += elapsed


def install(app):
    """Register instrumentation once, before the application's other hooks."""
    if app.extensions.get("operations_installed"):
        return
    app.extensions["operations_installed"] = True

    @app.before_request
    def begin_operation():
        g._operation_wall_start = time.perf_counter()
        g._operation_cpu_start = time.process_time()
        g._operation_written = False
        g._operation = {
            "request_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "method": request.method,
            "path": request.path,
            "query_string": request.query_string.decode("utf-8", errors="replace"),
            "stages_seconds": {name: 0.0 for name in STAGES},
        }

    @app.after_request
    def finish_operation(response):
        record = getattr(g, "_operation", None)
        if record is None:
            return response
        response.headers["X-Request-ID"] = record["request_id"]
        if g._operation_written:
            return response
        g._operation_written = True
        # Stop before snapshots, serialization and disk write; this boundary is
        # deliberately consistent for successful and failed HTTP responses.
        record["duration_seconds"] = max(0.0, time.perf_counter() - g._operation_wall_start)
        record["cpu_seconds"] = max(0.0, time.process_time() - g._operation_cpu_start)
        try:
            record.update(
                input=_input_snapshot(),
                output=_output_snapshot(response),
                status=response.status_code,
            )
            _append(record)
        except (OSError, TypeError, ValueError) as exc:
            # Do not turn an already-persisted decision into a retryable 503:
            # that can duplicate user submissions. Make lost evidence visible
            # both to the client and operator, and retain the original response.
            response.headers["X-Operational-Log"] = "failed"
            print(
                f"[operations] log failed request_id={record['request_id']}: {exc}",
                file=sys.stderr,
                flush=True,
            )
        return response
