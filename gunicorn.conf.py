"""Unit 9's single measured improvement: prepare the model before readiness.

Load inside the serving worker, never in the pre-fork master. No fixture is
scored here. Startup cost is recorded separately rather than hidden in request
cost statistics. A failed load prevents this worker from accepting requests.
"""

from datetime import datetime, timezone
import json
import os
import time


def post_worker_init(worker):
    import config
    import detector

    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    record = {
        "event": "model_startup",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "pid": os.getpid(),
        "model": config.DETECTOR_MODEL,
        "status": "ready",
        "inference_performed": False,
    }
    try:
        detector.warm_up()
    except Exception as exc:
        record.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        record["model_load_wall_seconds"] = time.perf_counter() - started_wall
        record["model_load_cpu_seconds"] = time.process_time() - started_cpu
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (config.LOG_DIR / "startup.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        worker.log.info("model startup status=%s wall=%.6fs cpu=%.6fs",
                        record["status"], record["model_load_wall_seconds"],
                        record["model_load_cpu_seconds"])
