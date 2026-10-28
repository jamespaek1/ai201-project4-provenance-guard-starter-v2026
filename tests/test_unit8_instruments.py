"""Isolated Unit 8 instrument checks, with a mocked detector and temporary log.

These validate limiter and audit behavior, not model accuracy or attack outcomes.
"""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app as service
import audit
import config
import detector


TEXT = (
    "We walked beside the river after breakfast and watched the boats turn "
    "toward the bridge. The cold wind made us hurry home for tea."
)


class Unit8InstrumentTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(config.RATE_LIMITING_ENABLED, "Instrument checks require the default enabled limiter")
        self.assertEqual(config.RATE_LIMIT_PER_MINUTE, 10)
        self.assertEqual(config.RATE_LIMIT_PER_DAY, 120)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        for name, value in (("LOG_DIR", directory), ("AUDIT_LOG", directory / "audit.jsonl")):
            mock = patch.object(config, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        old_testing = service.app.config["TESTING"]
        service.app.config["TESTING"] = True
        self.addCleanup(service.app.config.__setitem__, "TESTING", old_testing)
        service.limiter.reset()
        self.client = service.app.test_client()
        mock = patch.object(detector, "model_signal", return_value=0.6)
        self.model = mock.start()
        self.addCleanup(mock.stop)

    def submit(self, creator):
        return self.client.post("/submit", json={"text": TEXT, "creator_id": creator})

    def assert_one_rejection(self, response, expected_status, before, route="/submit"):
        self.assertEqual(response.status_code, expected_status, response.get_data(as_text=True))
        self.assertTrue(response.is_json)
        rows = audit.read_entries()
        self.assertEqual(rows[:len(before)], before)
        extra = rows[len(before):]
        self.assertEqual(len(extra), 1, extra)
        row = extra[0]
        self.assertEqual(row["event"], "rejected")
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(row["http_status"], expected_status)
        self.assertEqual(row["reason"], response.get_json()["error"])
        self.assertEqual(row["route"], route)
        self.assertEqual(row["method"], "POST")
        self.assertTrue(row["timestamp"])
        self.assertNotIn("guess", row)
        self.assertNotIn("content_id", row)

    def test_tenth_request_allowed_eleventh_logged_once_and_other_creator_independent(self):
        responses = [self.submit("quota-writer") for _ in range(10)]
        self.assertEqual([r.status_code for r in responses], [200] * 10)
        before = audit.read_entries()
        limited = self.submit("quota-writer")
        self.assert_one_rejection(limited, 429, before)
        self.assertEqual(audit.read_entries()[-1]["creator_id"], "quota-writer")
        self.assertIn("limit", audit.read_entries()[-1])
        self.assertEqual(self.model.call_count, 10)
        self.assertEqual(self.submit("other-writer").status_code, 200)
        self.assertEqual(self.model.call_count, 11)
        self.assertEqual(len(audit.read_entries()), 12)

    def test_missing_or_invalid_identity_uses_one_address_bucket(self):
        # Non-object and object requests must use the same fallback namespace.
        # Otherwise varying only JSON shape would create two address quotas.
        for _ in range(10):
            response = self.client.post("/submit", data="hello", content_type="text/plain")
            self.assertEqual(response.status_code, 415)
        before = audit.read_entries()
        limited = self.client.post("/submit", json={"text": TEXT, "creator_id": 123})
        self.assert_one_rejection(limited, 429, before)
        self.assertEqual(audit.read_entries()[-1]["creator_id"], "unknown")
        self.model.assert_not_called()
        # A different source address and a valid creator are separate buckets.
        other_address = self.client.post("/submit", data="hello", content_type="text/plain",
                                         environ_overrides={"REMOTE_ADDR": "192.0.2.8"})
        self.assertEqual(other_address.status_code, 415)
        self.assertEqual(self.submit("127.0.0.1").status_code, 200)
        self.assertEqual(self.model.call_count, 1)

    def test_route_and_pre_route_refusals_each_append_one_rejection_without_inference(self):
        oversize = json.dumps({"text": TEXT, "creator_id": "oversized", "padding": "x" * 65536})
        cases = [
            ("/submit", {"data": '{"text":', "content_type": "application/json"}, 400),
            ("/submit", {"data": "hello", "content_type": "text/plain"}, 415),
            ("/submit", {"json": {"text": "word " * 2001, "creator_id": "too-long"}}, 413),
            ("/submit", {"data": oversize, "content_type": "application/json"}, 413),
            ("/submit", {"data": b"x" * 70000, "content_type": "text/plain"}, 413),
            ("/appeal", {"json": {"content_id": "absent", "reasoning": "Please review."}}, 404),
            ("/appeal", {"data": b"x" * 70000, "content_type": "text/plain"}, 413),
        ]
        for route, kwargs, expected in cases:
            with self.subTest(route=route, expected=expected, media=kwargs.get("content_type")):
                before = audit.read_entries()
                response = self.client.post(route, **kwargs)
                self.assert_one_rejection(response, expected, before, route)
                self.model.assert_not_called()

    def test_streamed_oversize_refusal_is_logged_once_without_reread_failure(self):
        for route in ("/submit", "/appeal"):
            for media in ("application/json", "text/plain"):
                with self.subTest(route=route, media=media):
                    before = audit.read_entries()
                    response = self.client.open(route, method="POST", content_type=media,
                        environ_overrides={"wsgi.input": io.BytesIO(b"x" * 70000),
                                           "wsgi.input_terminated": True, "CONTENT_LENGTH": ""})
                    self.assert_one_rejection(response, 413, before, route)
                    self.model.assert_not_called()

    def test_decision_has_all_nine_fields_and_log_endpoint_preserves_order(self):
        responses = [self.submit(f"audit-writer-{i}") for i in range(3)]
        self.assertEqual([r.status_code for r in responses], [200] * 3)
        rows = audit.read_entries()
        required = {"timestamp", "content_id", "creator_id", "guess", "model_score",
                    "style_score", "combined_score", "label", "status"}
        for row, response in zip(rows, responses):
            self.assertTrue(required <= row.keys())
            self.assertTrue(all(row[key] is not None for key in required))
            self.assertEqual(row["status"], "decided")
            for key in required:
                self.assertEqual(row[key], response.get_json()[key])
        self.assertEqual(self.client.get("/log").get_json()["entries"], rows)
        self.assertEqual(self.model.call_count, 3)


if __name__ == "__main__":
    unittest.main()
