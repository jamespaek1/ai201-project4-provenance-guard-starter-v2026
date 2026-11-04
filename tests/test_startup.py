"""Readiness and startup evidence contract; model loading is mocked."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import config
import detector

spec = importlib.util.spec_from_file_location("gunicorn_settings", Path(__file__).resolve().parents[1] / "gunicorn.conf.py")
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)


class StartupTests(unittest.TestCase):
    def test_worker_loads_once_and_records_separate_cost(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, "LOG_DIR", Path(directory)):
            with patch.object(detector, "warm_up") as load:
                settings.post_worker_init(Mock())
            load.assert_called_once_with()
            rows = [json.loads(line) for line in (Path(directory) / "startup.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "ready")
            self.assertFalse(rows[0]["inference_performed"])
            self.assertGreaterEqual(rows[0]["model_load_cpu_seconds"], 0)
            self.assertGreaterEqual(rows[0]["model_load_wall_seconds"], 0)

    def test_failed_load_is_recorded_and_prevents_worker_initialization(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, "LOG_DIR", Path(directory)):
            with patch.object(detector, "warm_up", side_effect=detector.DetectorUnavailable("missing")):
                with self.assertRaises(detector.DetectorUnavailable):
                    settings.post_worker_init(Mock())
            row = json.loads((Path(directory) / "startup.jsonl").read_text())
            self.assertEqual(row["status"], "failed")
            self.assertEqual(row["error_type"], "DetectorUnavailable")
