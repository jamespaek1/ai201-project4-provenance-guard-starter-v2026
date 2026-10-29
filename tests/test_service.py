"""Service-contract checks; detector calls are mocked, never downloaded.

These tests verify plumbing and the declared numeric rules. They do NOT
establish real-model label reachability, accuracy, or Unit 8 acceptance results.
Audit files are isolated in a temporary directory, never the committed demo log.
"""

import copy
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import app as service
import audit
import config
import detector
import scoring
import stylometry


TEXT = (
    "We walked beside the river after breakfast and watched the boats turn "
    "toward the bridge. The cold wind made us hurry home for tea."
)


class ServiceContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.log_dir = Path(temporary.name)
        self.log_path = self.log_dir / "audit.jsonl"
        for name, value in (("LOG_DIR", self.log_dir), ("AUDIT_LOG", self.log_path)):
            mock = patch.object(config, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        self.old_testing = service.app.config["TESTING"]
        service.app.config["TESTING"] = True
        self.addCleanup(service.app.config.__setitem__, "TESTING", self.old_testing)
        # Unit 8 enables the shared in-memory limiter. Each isolated contract
        # test starts with a fresh quota; this is not an accuracy trial.
        if hasattr(service.limiter, "reset"):
            service.limiter.reset()
        self.client = service.app.test_client()
        self.model_patch = patch.object(detector, "model_signal", return_value=0.6)
        self.model = self.model_patch.start()
        self.addCleanup(self.model_patch.stop)

    def submit(self, **changes):
        payload = {"text": TEXT, "creator_id": "contract-test-writer"}
        payload.update(changes)
        response = self.client.post("/submit", json=payload)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def assert_json_error(self, response, status):
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        self.assertTrue(response.is_json)
        self.assertIsInstance(response.get_json(), dict)
        self.assertTrue(response.get_json().get("error"))

    def assert_no_new_successful_events(self, prior):
        # Rejection tracing is allowed; it must not masquerade as a decision.
        extra = audit.read_entries()[len(prior):]
        self.assertTrue(all(row.get("event") == "rejected" for row in extra), extra)

    def test_submit_contract_and_audit_match_one_real_route_call(self):
        result = self.submit()
        for key in ("content_id", "creator_id", "guess", "confidence", "label",
                    "model_score", "style_score", "status"):
            self.assertIn(key, result)
        self.assertTrue(result["content_id"])
        self.assertEqual(result["creator_id"], "contract-test-writer")
        self.assertEqual(result["status"], "decided")
        self.assertEqual(result["model_score"], 0.6)
        self.assertAlmostEqual(result["style_score"], stylometry.style_signal(TEXT))
        expected = scoring.combine_signals(result["model_score"], result["style_score"])
        self.assertAlmostEqual(result["confidence"], expected)
        self.assertEqual((result["guess"], result["label"]), scoring.score_to_label(expected))
        self.model.assert_called_once_with(TEXT)
        entries = audit.read_entries()
        self.assertEqual(len(entries), 1)
        row = entries[0]
        for key in ("content_id", "creator_id", "guess", "label", "status",
                    "model_score", "style_score"):
            self.assertEqual(row[key], result[key])
        self.assertEqual(row["combined_score"], result["confidence"])
        self.assertTrue(row["timestamp"])
        logged = self.client.get("/log?limit=1").get_json()
        self.assertEqual(logged["entries"], entries)
        self.assertEqual(logged["count"], 1)

    def test_invalid_input_matrix_never_calls_detector_or_creates_content(self):
        good = {"text": TEXT, "creator_id": "writer"}
        cases = [
            ("wrong media", {"data": "hello", "content_type": "text/plain"}, 415),
            ("malformed JSON", {"data": '{"text":', "content_type": "application/json"}, 400),
            ("array", {"json": []}, 400),
            ("missing text", {"json": {"creator_id": "writer"}}, 400),
            ("numeric text", {"json": {**good, "text": 12}}, 400),
            ("blank text", {"json": {**good, "text": " \n\t "}}, 400),
            ("nineteen words", {"json": {**good, "text": " ".join(["word"] * 19)}}, 400),
            ("10001 characters", {"json": {**good, "text": ("word " * 2001)[:10001]}}, 413),
            ("missing creator", {"json": {"text": TEXT}}, 400),
            ("numeric creator", {"json": {**good, "creator_id": 3}}, 400),
            ("blank creator", {"json": {**good, "creator_id": " \t "}}, 400),
            ("101 character creator", {"json": {**good, "creator_id": "x" * 101}}, 400),
            ("oversized body", {"data": json.dumps({**good, "extra": "x" * 65536}),
                                "content_type": "application/json"}, 413),
        ]
        for name, kwargs, expected in cases:
            with self.subTest(case=name):
                prior = audit.read_entries()
                self.model.reset_mock()
                self.assert_json_error(self.client.post("/submit", **kwargs), expected)
                self.model.assert_not_called()
                self.assert_no_new_successful_events(prior)

    def test_valid_input_limits_are_inclusive(self):
        self.submit(text=" ".join(["word"] * 20), creator_id="x" * 100)
        self.submit(text="word " * 2000)
        self.assertEqual(self.model.call_count, 2)
        self.assertEqual(len([r for r in audit.read_entries() if r["status"] == "decided"]), 2)

    def test_oversized_body_precedes_media_and_field_validation_on_both_routes(self):
        decision = self.submit()
        original_log = copy.deepcopy(audit.read_entries())
        payloads = {
            "/submit": {"text": TEXT, "creator_id": "writer", "extra": "x" * 65536},
            "/appeal": {"content_id": decision["content_id"], "reasoning": "x" * 65536},
        }
        for route, payload in payloads.items():
            # The plain body is below 64 KiB in characters but above it in UTF-8
            # bytes. Both forms must fail at the body limit, even when the
            # Content-Type or individual fields would otherwise be invalid.
            bodies = (
                ("application/json", json.dumps(payload).encode("utf-8")),
                ("text/plain", ("é" * 32769).encode("utf-8")),
            )
            for content_type, body in bodies:
                with self.subTest(route=route, content_type=content_type):
                    self.assertGreater(len(body), 64 * 1024)
                    self.model.reset_mock()
                    response = self.client.post(route, data=body, content_type=content_type)
                    self.assert_json_error(response, 413)
                    self.model.assert_not_called()
                    self.assertEqual(audit.read_entries()[:len(original_log)], original_log)
                    self.assert_no_new_successful_events(original_log)

    def test_terminated_unknown_length_bodies_enforce_limit_without_truncation(self):
        self.submit()
        original_log = copy.deepcopy(audit.read_entries())
        for route in ("/submit", "/appeal"):
            for content_type in ("text/plain", "application/json"):
                for size in (65536, 65537, 70000):
                    with self.subTest(route=route, content_type=content_type, size=size):
                        self.model.reset_mock()
                        response = self.client.open(
                            route,
                            method="POST",
                            content_type=content_type,
                            environ_overrides={
                                "wsgi.input": io.BytesIO(b"x" * size),
                                "wsgi.input_terminated": True,
                                "CONTENT_LENGTH": "",
                            },
                        )
                        # An unknown-length stream must be checked with a
                        # lookahead, not silently accepted after truncation.
                        # Exactly 64 KiB is allowed through the size gate and
                        # then fails the ordinary media/JSON validation.
                        expected = 413 if size > 65536 else (
                            415 if content_type == "text/plain" else 400
                        )
                        self.assert_json_error(response, expected)
                        self.model.assert_not_called()
                        self.assertEqual(audit.read_entries()[:len(original_log)], original_log)
                        self.assert_no_new_successful_events(original_log)

    def test_appeal_retains_original_and_exact_reasoning_without_rescoring(self):
        decision = self.submit()
        original = copy.deepcopy(audit.read_entries()[0])
        reasoning = "  These are my own notes.\nPlease review the original draft.  "
        self.model.reset_mock()
        response = self.client.post("/appeal", json={
            "content_id": decision["content_id"], "reasoning": reasoning,
            "creator_id": "a-different-creator-claim",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "under_review")
        self.assertEqual(response.get_json()["content_id"], decision["content_id"])
        self.model.assert_not_called()
        rows = audit.entries_for(decision["content_id"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], original)
        self.assertEqual(rows[1]["event"], "appeal")
        self.assertEqual(rows[1]["status"], "under_review")
        self.assertEqual(rows[1]["creator_id"], original["creator_id"])
        self.assertEqual(rows[1]["reasoning"], reasoning)
        current = self.client.get(f"/content/{decision['content_id']}")
        self.assertEqual(current.status_code, 200)
        body = current.get_json()
        self.assertEqual(body["status"], "under_review")
        self.assertEqual(body["guess"], original["guess"])
        self.assertEqual(body["label"], original["label"])
        self.assertEqual(body["appeals"][0]["reasoning"], reasoning)
        self.assertEqual(self.client.get("/log").get_json()["entries"], audit.read_entries())

    def test_invalid_appeals_never_append_or_rescore(self):
        decision = self.submit()
        cases = [
            ({"content_id": "missing-content", "reasoning": "Please review this."}, 404),
            ({"content_id": decision["content_id"], "reasoning": " \n "}, 400),
            ({"content_id": decision["content_id"], "reasoning": "x" * 2001}, 400),
            ({"content_id": decision["content_id"], "reasoning": 123}, 400),
            ({"reasoning": "Please review this."}, 400),
        ]
        for payload, expected in cases:
            with self.subTest(payload=repr(payload)[:100]):
                prior = audit.read_entries()
                self.model.reset_mock()
                self.assert_json_error(self.client.post("/appeal", json=payload), expected)
                self.model.assert_not_called()
                self.assert_no_new_successful_events(prior)
        self.assert_json_error(self.client.get("/content/missing-content"), 404)

    def test_ten_appealed_items_survive_fresh_process_read(self):
        ids = []
        originals = {}
        for i in range(10):
            result = self.submit(creator_id=f"writer-{i}")
            content_id = result["content_id"]
            ids.append(content_id)
            originals[content_id] = copy.deepcopy(audit.entries_for(content_id)[0])
            reason = f"Reason {i}: Please check my saved draft and notes."
            response = self.client.post("/appeal", json={"content_id": content_id, "reasoning": reason})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(len(set(ids)), 10)
        self.assertEqual(self.model.call_count, 10, "Appeals must not call the detector")
        self.assertEqual(len(audit.read_entries()), 20)
        for content_id in ids:
            self.assertEqual(audit.entries_for(content_id)[0], originals[content_id])
        # A fresh process rules out status being held only in Flask/module memory.
        # No model method is called; it reads the same append-only audit file.
        code = """
import json, sys
from pathlib import Path
import config
config.LOG_DIR = Path(sys.argv[1])
config.AUDIT_LOG = config.LOG_DIR / 'audit.jsonl'
import app
client = app.app.test_client()
print(json.dumps([client.get('/content/' + value).get_json() for value in json.loads(sys.argv[2])]))
"""
        fresh = subprocess.run([sys.executable, "-c", code, str(self.log_dir), json.dumps(ids)],
                               cwd=Path(__file__).resolve().parents[1], text=True,
                               capture_output=True, check=True, timeout=30)
        bodies = json.loads(fresh.stdout)
        self.assertEqual(len(bodies), 10)
        for index, body in enumerate(bodies):
            self.assertEqual(body["content_id"], ids[index])
            self.assertEqual(body["status"], "under_review")
            self.assertEqual(body["guess"], originals[ids[index]]["guess"])
            self.assertEqual(len(body["appeals"]), 1)
            self.assertEqual(body["appeals"][0]["reasoning"],
                             f"Reason {index}: Please check my saved draft and notes.")


class ScoreContractTests(unittest.TestCase):
    def test_all_1001_points_follow_the_declared_inclusive_boundaries(self):
        seen = set()
        for integer in range(1001):
            score = integer / 1000
            expected = "human" if integer <= 200 else ("ai" if integer >= 850 else "unsure")
            with self.subTest(score=score):
                guess, label = scoring.score_to_label(score)
                self.assertEqual(guess, expected)
                self.assertIsInstance(label, str)
                self.assertNotIn("PLACEHOLDER", label)
                self.assertIn("review", label.lower())
                seen.add(guess)
        self.assertEqual(seen, {"human", "unsure", "ai"})
        self.assertNotEqual(scoring.score_to_label(0.51)[0], scoring.score_to_label(0.95)[0])

    def test_nonfinite_or_out_of_range_scores_are_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), -0.001, 1.001):
            with self.subTest(value=value):
                with self.assertRaises((ValueError, TypeError)):
                    scoring.score_to_label(value)
                with self.assertRaises((ValueError, TypeError)):
                    scoring.combine_signals(value, 0.5)
                with self.assertRaises((ValueError, TypeError)):
                    scoring.combine_signals(0.5, value)

    def test_agreement_keeps_score_and_disagreement_uses_unsure(self):
        self.assertAlmostEqual(scoring.combine_signals(0.8, 0.8), 0.8)
        self.assertAlmostEqual(scoring.combine_signals(1.0, 0.0), 0.5)
        self.assertAlmostEqual(scoring.combine_signals(0.0, 1.0), 0.5)
        self.assertAlmostEqual(scoring.combine_signals(0.75, 0.25), 0.5)
        self.assertAlmostEqual(scoring.combine_signals(0.7, 0.2), 0.475)
        self.assertAlmostEqual(scoring.combine_signals(math.nextafter(0.7, 0), 0.2), 0.45)
        self.assertAlmostEqual(scoring.combine_signals(0.7499, 0.25), 0.49995)
        for model, style in ((1, 0), (0, 1), (0.75, 0.25)):
            self.assertEqual(scoring.score_to_label(scoring.combine_signals(model, style))[0], "unsure")

    def test_style_features_have_the_declared_units(self):
        self.assertAlmostEqual(stylometry.sentence_length_spread("One two. Three four five six."), 1 / 3)
        self.assertEqual(stylometry.sentence_length_spread("One sentence here."), 0.0)
        self.assertAlmostEqual(stylometry.type_token_ratio("A a b"), 2 / 3)
        self.assertAlmostEqual(stylometry.punctuation_density("a—b!"), 0.5)
        self.assertAlmostEqual(stylometry.punctuation_density("a — b!"), 0.5)
        self.assertEqual(stylometry.type_token_ratio(""), 0.0)
        self.assertEqual(stylometry.punctuation_density(" \n\t "), 0.0)
        self.assertAlmostEqual(stylometry.style_signal(""), 0.5)
        for text in (TEXT, "word " * 100, "A.", "One two. Three four five six.", "— ! ?"):
            with self.subTest(text=text[:30]):
                score = stylometry.style_signal(text)
                self.assertGreaterEqual(score, 0.0)
                self.assertLessEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
