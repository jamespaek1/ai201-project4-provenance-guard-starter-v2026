# Unit 9 baseline diagnosis — before the measured improvement

The three complete real-model trials at `7a7f592` used the frozen criteria and
fixtures without runtime changes. C1 startup (with separate clean-clone setup
verification), C2 success logs, C3 failure logs and C5 restart continuity passed.
C4 MISSED: maximum request times were 6.273185, 1.506197 and 1.467946 seconds;
the 2.0-second limit must hold in every trial, not on average.

The failure is in `app.py::submit`'s model stage, calling
`detector.model_signal` → `detector._load`. `/health` reported ready with
`detector_loaded=false`; the first writer therefore paid the model import/load
cost. Later requests reused the in-process model. Fresh worker processes do not
flush OS file caches, and the large first-trial/clean-clone difference illustrates
that variation. These three trials do not isolate OS-cache effects or establish
production percentiles.

Select exactly one operational improvement: load the already-pinned model in
Gunicorn's serving worker before it begins accepting requests. Use the existing
`detector.warm_up()` (load only; no test-text inference), retain all score code,
criteria and fixtures, and record startup model wall/CPU time separately. This
moves work to readiness rather than eliminating it. Keep the 60-second startup
budget and rerun all five targets three times; do not relax the latency target.

Clean-clone setup evidence includes a failed uv interpreter discovery, corrected
by making the existing CPython 3.12.14 discoverable on PATH, and a first smoke
harness attempt referencing a not-yet-present fixture file. Both are preserved;
the successful retry uses the identical U9-01 fixture as an external HTTP input.
Neither is silently counted as a successful full smoke run. Final code will be
verified again in that separate clone using its independently installed venv.
