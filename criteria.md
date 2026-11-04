# Unit 9 capstone acceptance criteria — preregistered

Shape A: deploy and instrument Provenance Guard. Path B: local with logs.
These five **new** criteria are AI-assisted instructor-example targets, authored
before Unit 9 implementation or measurements. They are not unaided student work.
[Original Unit 7–8 criteria](docs/criteria-units7-8.md) remain unchanged.

All five are tested in three full independent trials before and after one
measured improvement, using identical fixtures, pinned model/runtime and one
sequential Gunicorn worker. MET requires every assertion in all three trials;
never average away a failing trial. Record startup separately from request time.
A warm disk cache means downloaded files exist, not a model loaded in a process.

## 1. Cached startup: ready within 60 seconds (extension)

On each of three new service processes launched with the single command in
RUNNING.md, using the documented installed environment and cached pinned model,
`GET /health` must first return HTTP 200 with `ok=true` within **60 seconds**
of launch. Measure with a monotonic clock; record whether the model is loaded.
Repeat the documented setup/start in a separate clean clone with a fresh venv.

**Why 60 seconds:** this is a classroom laptop service with local model files;
a reviewer should reach a responsive process within one minute. Dependency
installation and first model download are setup costs, reported separately.

## 2. Success instrumentation: 10/10 complete records (extension)

For each trial's **ten fixed sequential valid submissions**, each returned
`X-Request-ID` must match exactly one parseable JSONL operation record containing
an ISO UTC timestamp, method/path, the exact input body, exact JSON output and
HTTP status, nonnegative finite wall/CPU seconds, and nonnegative model, style,
scoring and audit stage durations. Record every submission, not a sample.

**Why 10/10:** ten requests supply the required cost sample; losing even one
breaks the audit-to-cost correspondence. Fields and exact comparisons make the
contract independently checkable; only authored fixture inputs are published.

## 3. Failure instrumentation: 5/5 rejected paths recorded (extension)

In each trial, malformed JSON (**400**), fewer than 20 words (**400**), a body
larger than 64 KiB (**413**), an unknown appeal ID (**404**), and an eleventh
request by one creator within one minute (**429**) must each produce exactly
one correlated operation record with the actual error output/status, nonnegative
wall/CPU seconds and **zero model-stage time**. The record must retain the input
or explicitly mark a bounded prefix as truncated for an oversized body.

**Why 5/5:** these exercise parser, validation, byte limit, lookup and limiter
failures; silent gaps would make the operator underestimate rejected load.
Ten preliminary short requests for the rate-limit case are invalid and must
not call the model. Each trial uses its own creator IDs and log files.

## 4. Interactive latency: every response within 2.0 seconds (extension)

Each of the same **ten valid submissions per trial**, including the first one
immediately after health readiness, must return HTTP 200 within **2.0 seconds**
client-observed monotonic wall time. No warm-up submission may precede them;
report all ten times and the maximum, with startup time alongside.

**Why 2.0 seconds:** a short writing check should fit an interactive pause. This
is deliberately demanding for a first local-model call, and may fail. Loading
moved to startup must still satisfy criterion 1 and be reported, not hidden.

## 5. Restart continuity: one full appeal round-trip preserved (integration)

For the first valid submission in each trial, submit an appeal with the fixed
reason `Please review this classroom example.`; after a service restart using
the same log directory, `GET /content/<id>` must return the identical original
decision, the exact reason and current `status=under_review`. The original
submission and appeal operation records must each remain exactly once.

**Why one per trial:** the extension changes launch and log paths; one real
round-trip in each independent process/log lifecycle detects an accidental
reset or split between audit and operational storage. Unit 8 already tested ten
appeals per trial; this is a restart-integration check, not a new accuracy claim.

## Frozen test and review protocol

Freeze ten authored 40–100-word fixture texts in `examples/unit9_requests.json`
before the first run. Use the same order and content in both phases, with trial
prefixes only in creator IDs. Three trials are fresh worker processes with a
warm disk cache, run sequentially; restart once per trial for criterion 5. Use
CPU `process_time` as a local compute proxy, not money, plus wall time as user
latency. Report mean of each ten-request sample and multiply by 100 for a
one-submission-per-user/day estimate; separately disclose startup and failures.

The course self-check was read before this commit: each target has a visible or
numeric outcome, exact repeatable steps, a rationale and a failure condition.
C1 checks startup, C2 successful evidence, C3 failure evidence, C4 latency, C5
persistence. C4 is intentionally at risk. This is AI review and AI authorship,
not invented peer review or unaided student work. Scope and optional latency
breakdown stretch were declared in README before implementation. A single
improvement will be selected from actual baseline evidence; targets stay frozen.
