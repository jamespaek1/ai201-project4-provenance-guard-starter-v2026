"""Operational contract checks with isolated Flask apps; no detector runs."""

from contextlib import redirect_stderr
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

import config
import operations


class OperationsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.log_path = Path(temporary.name) / "operations.jsonl"
        setting = patch.object(config, "OPERATIONS_LOG", self.log_path, create=True)
        setting.start()
        self.addCleanup(setting.stop)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False,
                               MAX_CONTENT_LENGTH=operations.BODY_LIMIT + 1)
        operations.install(self.app)
        operations.install(self.app)  # Installation must not duplicate records.

        @self.app.before_request
        def size_guard():
            if len(request.get_data(cache=True)) > operations.BODY_LIMIT:
                raise RequestEntityTooLarge()

        @self.app.after_request
        def downstream_response_change(response):
            if request.path == "/echo" and response.is_json:
                payload = response.get_json()
                payload["after_request"] = "complete"
                response.set_data(json.dumps(payload))
            return response

        @self.app.errorhandler(RequestEntityTooLarge)
        def too_large(_error):
            return jsonify(error="payload_too_large"), 413

        @self.app.post("/echo")
        def echo():
            with operations.stage("model"):
                payload = request.get_json()
            with operations.stage("audit"):
                pass
            return jsonify(received=payload)

        @self.app.post("/crash")
        def crash():
            with operations.stage("model"):
                raise RuntimeError("deliberate test failure")

        @self.app.get("/health")
        def health():
            return jsonify(ok=True)

        self.client = self.app.test_client()

    def records(self):
        return [json.loads(line) for line in self.log_path.read_text().splitlines()]

    def assert_record(self, response):
        records = self.records()
        matching = [row for row in records
                    if row["request_id"] == response.headers["X-Request-ID"]]
        self.assertEqual(len(matching), 1)
        record = matching[0]
        self.assertEqual(record["status"], response.status_code)
        self.assertTrue(record["timestamp"].endswith("+00:00"))
        for value in (record["duration_seconds"], record["cpu_seconds"],
                      *record["stages_seconds"].values()):
            self.assertTrue(math.isfinite(value))
            self.assertGreaterEqual(value, 0)
        self.assertEqual(set(record["stages_seconds"]), set(operations.STAGES))
        return record

    def test_exact_raw_input_and_final_output_are_correlated_once(self):
        raw = '{  "text": "café", "extra": [1, true] }\n'
        response = self.client.post("/echo?trial=1", data=raw.encode("utf-8"),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        record = self.assert_record(response)
        self.assertEqual(record["input"]["body"], raw)
        self.assertFalse(record["input"]["truncated"])
        self.assertEqual(record["output"], response.get_json())
        self.assertEqual(record["output"]["after_request"], "complete")
        self.assertEqual((record["method"], record["path"], record["query_string"]),
                         ("POST", "/echo", "trial=1"))
        self.assertEqual(len(self.records()), 1)

    def test_known_oversized_request_logs_without_bypassing_size_guard(self):
        response = self.client.post("/echo", data=b"x" * (operations.BODY_LIMIT + 2),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 413)
        record = self.assert_record(response)
        self.assertEqual(record["output"], response.get_json())
        self.assertTrue(record["input"]["truncated"])
        self.assertEqual(record["input"]["capture_reason"], "body_rejected_before_read")
        self.assertEqual(record["input"]["body"], "")
        self.assertEqual(record["stages_seconds"]["model"], 0)

    def test_unknown_length_oversized_stream_retains_only_bounded_prefix(self):
        response = self.client.open("/echo", method="POST", content_type="application/json",
                                    environ_overrides={
                                        "wsgi.input": io.BytesIO(b"x" * 70000),
                                        "wsgi.input_terminated": True,
                                        "CONTENT_LENGTH": "",
                                    })
        self.assertEqual(response.status_code, 413)
        record = self.assert_record(response)
        self.assertEqual(record["input"]["body"], "x" * operations.BODY_LIMIT)
        self.assertTrue(record["input"]["truncated"])
        self.assertEqual(record["stages_seconds"]["model"], 0)

    def test_unhandled_failure_and_read_request_are_both_recorded(self):
        with self.assertLogs(self.app.logger, level="ERROR"):
            failed = self.client.post("/crash", data="failure input", content_type="text/plain")
        self.assertEqual(failed.status_code, 500)
        record = self.assert_record(failed)
        self.assertEqual(record["input"]["body"], "failure input")
        self.assertEqual(record["output"]["body"], failed.get_data(as_text=True))
        self.assertGreater(record["stages_seconds"]["model"], 0)
        healthy = self.client.get("/health")
        record = self.assert_record(healthy)
        self.assertEqual(record["output"], {"ok": True})
        self.assertEqual(record["input"]["body"], "")
        self.assertEqual(len(self.records()), 2)

    def test_sink_failure_is_visible_without_changing_completed_response(self):
        stderr = io.StringIO()
        with patch.object(operations, "_append", side_effect=OSError("disk unavailable")):
            with redirect_stderr(stderr):
                response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})
        self.assertEqual(response.headers["X-Operational-Log"], "failed")
        self.assertIn(response.headers["X-Request-ID"], stderr.getvalue())
        self.assertIn("disk unavailable", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
