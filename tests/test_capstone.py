"""Guard capstone verdicts against false passes; no service or model calls."""

from copy import deepcopy
import unittest

from run_capstone import inspect_record


def evidence(status=200, output=None):
    """An HTTP observation and its independently captured operation record."""
    if output is None:
        output = {"content_id": "example", "guess": "unsure"}
    call = {
        "request_id": "sample-request", "status": status,
        "method": "POST", "path": "/submit", "input_body": '{"text":"example"}',
        "content_type": "application/json", "output": deepcopy(output),
    }
    record = {
        "request_id": "sample-request", "timestamp": "2026-11-04T12:00:00+00:00",
        "method": "POST", "path": "/submit", "status": status,
        "input": {"body": call["input_body"], "truncated": False,
                  "content_type": "application/json"},
        "output": deepcopy(output), "duration_seconds": 0.2, "cpu_seconds": 0.1,
        "stages_seconds": {"model": 0.1, "style": 0.02, "scoring": 0.01, "audit": 0.01},
    }
    return call, record


class CapstoneEvidenceTests(unittest.TestCase):
    def test_missing_duplicate_or_uncorrelated_records_do_not_pass(self):
        call, record = evidence()
        self.assertTrue(inspect_record(call, [record], 200)["passed"])
        for records in ([], [record, deepcopy(record)], [{**record, "request_id": "different"}]):
            with self.subTest(records=records):
                self.assertFalse(inspect_record(call, records, 200)["passed"])
        call["request_id"] = None
        self.assertFalse(inspect_record(call, [record], 200)["passed"])

    def test_record_must_match_the_actual_input_and_output(self):
        call, record = evidence()
        altered_output = deepcopy(record)
        altered_output["output"]["guess"] = "ai"
        altered_input = deepcopy(record)
        altered_input["input"]["body"] = '{"text":"different"}'
        for candidate in (altered_output, altered_input):
            with self.subTest(candidate=candidate):
                self.assertFalse(inspect_record(call, [candidate], 200)["passed"])

    def test_invalid_clock_evidence_fails_without_crashing(self):
        call, record = evidence()
        for timestamp in (None, 123, "not a date", "2026-11-04T12:00:00", "2026-11-04T12:00:00+02:00"):
            with self.subTest(timestamp=timestamp):
                candidate = {**record, "timestamp": timestamp}
                self.assertFalse(inspect_record(call, [candidate], 200)["passed"])
        for field in ("duration_seconds", "cpu_seconds"):
            for value in (-0.001, float("nan"), float("inf"), True, "0.1"):
                with self.subTest(field=field, value=value):
                    candidate = {**record, field: value}
                    self.assertFalse(inspect_record(call, [candidate], 200)["passed"])

    def test_failure_requires_expected_status_error_and_zero_model_work(self):
        call, record = evidence(400, {"error": "text_too_short", "message": "Provide at least 20 words."})
        record["stages_seconds"]["model"] = 0
        self.assertTrue(inspect_record(call, [record], 400, failure=True)["passed"])
        self.assertFalse(inspect_record(call, [record], 429, failure=True)["passed"])
        misleading_call, misleading_record = evidence(400, {"message": "Everything worked."})
        misleading_record["stages_seconds"]["model"] = 0
        self.assertFalse(inspect_record(misleading_call, [misleading_record], 400, failure=True)["passed"])
        wrong_output = deepcopy(record)
        wrong_output["output"] = {"error": "different_error"}
        self.assertFalse(inspect_record(call, [wrong_output], 400, failure=True)["passed"])
        record["stages_seconds"]["model"] = 0.000001
        self.assertFalse(inspect_record(call, [record], 400, failure=True)["passed"])

    def test_oversized_body_omission_needs_explicit_capture_metadata(self):
        call, record = evidence(413, {"error": "payload_too_large"})
        call["input_body"] = "x" * 65538
        record["stages_seconds"]["model"] = 0
        record["input"].update(body="", truncated=True, capture_reason="body_rejected_before_read")
        self.assertTrue(inspect_record(call, [record], 413, failure=True, oversized=True)["passed"])
        for change in ({"capture_reason": None}, {"truncated": False},
                       {"body": "not the submitted prefix"}, {"body": "x" * 65537}):
            with self.subTest(change=change):
                candidate = deepcopy(record)
                candidate["input"].update(change)
                self.assertFalse(inspect_record(call, [candidate], 413, failure=True, oversized=True)["passed"])


if __name__ == "__main__":
    unittest.main()
