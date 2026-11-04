# Running Provenance Guard — Unit 9 local path

This capstone uses **Path B: local with logs**. It extends the same Unit 7–8
service. No hosted URL, API key, account or paid inference API is needed.
The service binds only to `127.0.0.1`, runs one Gunicorn sync worker, and disables
Flask debug mode. Keep it local: authentication and a public deployment are
outside this capstone's scope.

## One-time setup

The pinned environment is **CPython 3.12.14 on macOS 27.0.1 arm64**. With
[uv](https://docs.astral.sh/uv/getting-started/installation/) installed and
CPython 3.12.14 discoverable on `PATH` (or available in uv's download catalog):

```bash
git clone https://github.com/jamespaek1/ai201-project4-provenance-guard-starter-v2026.git
cd ai201-project4-provenance-guard-starter-v2026
uv venv --python 3.12.14 .venv
uv pip install --python .venv/bin/python -r requirements.lock
.venv/bin/python prepare_model.py
```

If uv cannot find 3.12.14, put the `bin` directory of your installed CPython
3.12.14 on `PATH`, or pass its absolute executable path to `uv venv --python`.
The clean-clone check used an existing 3.12.14 interpreter on `PATH` and a new
virtual environment; it did not copy the original virtual environment.

Alternatively, with CPython 3.12.14 already installed, use
`python3.12 -m venv .venv` and `.venv/bin/python -m pip install -r requirements.lock`
in place of the two uv commands. Linux may work but has not been established
by this macOS record; native Windows needs WSL because this launcher uses POSIX
shell and Gunicorn.

`requirements.lock` pins every installed runtime dependency, including
Torch 2.14.1, Transformers 4.57.6, Flask 3.1.3, Flask-Limiter 3.12 and Gunicorn
23.0.0. `requirements.txt` retains the prior units' version ranges for history;
use the lock for capstone reproduction. The setup helper only downloads or
locates files. It does not load the model or perform a warm-up inference.

The model is GPT-2 repository `gpt2`, pinned to commit
`607a30d783dfa663caf39e06633721c8d4cfcd7e`. The helper requests only these seven
files. Sizes were read from the existing pinned snapshot, not estimated:

| File | Bytes |
|---|---:|
| `config.json` | 665 |
| `generation_config.json` | 124 |
| `merges.txt` | 456,318 |
| `model.safetensors` | 548,105,171 |
| `tokenizer.json` | 1,355,256 |
| `tokenizer_config.json` | 26 |
| `vocab.json` | 1,042,301 |
| **Total** | **550,959,861** |

That is about **551 MB decimal / 525.4 MiB**, excluding the Python environment,
download cache metadata, logs and runtime memory. Allow extra disk space for
package downloads and installation. Files are under `.cache/huggingface` by
default and are not committed. `start.sh` resolves this exact local snapshot,
sets `AI201_DETECTOR_MODEL` to its path, and makes runtime model access offline.
It fails with setup instructions if a required file is missing.

To reuse an existing model cache, set its **Hugging Face home** before both setup
and start; it must contain `hub/models--gpt2/snapshots/<revision>/...`:

```bash
export HF_HOME=/absolute/path/to/existing/.cache/huggingface
.venv/bin/python prepare_model.py --offline
```

This avoids another 551 MB download. A clean-clone verification may share this
explicit cache while installing a new `.venv`; that verifies the checkout and
setup instructions, not a fresh-machine network download. The final evidence
records exactly which setup was used.

## The single start command

From the repository root, after setup:

```bash
./start.sh
```

It runs in the foreground at `http://127.0.0.1:5057`. Press Ctrl-C to stop.
The final worker loads GPT-2 before accepting requests, so readiness includes
model loading and `/health` reports `detector_loaded=true`. This is the single
measured improvement after the baseline cold-request miss. Loading performs no
fixture inference; `logs/startup.jsonl` records its wall/CPU cost and any failure.
A failed model load prevents worker readiness. Startup and first-request times
are both reported so moving the work does not hide it.

Optional environment settings, set before that same command:

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5057` | Select another local port if this one is occupied. |
| `HF_HOME` | repository `.cache/huggingface` | Select a prepared pinned cache. |
| `AI201_LOG_DIR` | repository `logs` | Keep audit and operational logs together in a chosen directory. |

The launcher deliberately fixes one worker and one request at a time. This
makes per-request process CPU seconds interpretable for the sequential cost
sample and avoids pretending the in-memory limiter is shared across workers.
It leaves Torch's native thread policy unchanged. CPU seconds can exceed wall
seconds because native computation can use more than one CPU core.

## Check a real request

In another terminal:

```bash
curl http://127.0.0.1:5057/health
curl -i http://127.0.0.1:5057/submit \
  -H 'Content-Type: application/json' \
  -d '{"creator_id":"local-example","text":"We met beside the community garden after breakfast to organize the weekend cleanup. Maya brought gloves, and I counted the reusable bags. The gate was stuck again, so we carried everything through the narrow side entrance before the other volunteers arrived."}'
```

The JSON response includes `content_id`, `model_score`, `style_score`,
`combined_score`, `guess`, `label` and appeal instructions. The
`X-Request-ID` response header correlates it with `operations.jsonl`.
The score is a heuristic signal, not proof of authorship. This local service
does not remove writing or automatically punish a writer.

| Route | Behavior |
|---|---|
| `POST /ping` | Preserved starter control route. |
| `GET /health` | Process status and whether the detector is loaded. |
| `POST /submit` | Validate text, run both signals, score and append a decision. |
| `POST /appeal` | Append the exact reason and mark an existing item under review. |
| `GET /content/<id>` | Retrieve the original decision, current status and appeals. |
| `GET /log` | Read audit events. |

Input bounds and the 10/minute, 120/day per-creator limits remain those from
Unit 8. Restarting the single process resets the in-memory rate counters;
it must not reset either persistent log file.

## Logs and reproducible evaluation

`logs/audit.jsonl` holds decisions, appeals and rejections. `logs/operations.jsonl`
holds correlated request input/output, status, timestamp, wall duration, CPU
seconds and model/style/scoring/audit stage durations. Operational timing starts
before validation and ends before its own log append; client timing in the
evaluator includes transport and the log append. Rejected requests are recorded
too. Oversized bodies use an explicitly marked bounded prefix; when Werkzeug rejects
Content-Length before reading, the prefix is empty with
`capture_reason=body_rejected_before_read` and the declared byte length. These logs can
contain submitted text: committed examples use authored synthetic fixtures.

The five capstone targets are preregistered in [criteria.md](criteria.md).
The evaluator uses the ten frozen inputs in `examples/unit9_requests.json`,
three independent trials, separate logs per trial, and one restart per trial.
The README links the actual before/after evidence and cost calculation.
Use a new output directory for an additional run to preserve earlier evidence.

```bash
.venv/bin/python run_capstone.py --phase reproduction --output results/unit9/reproduction
.venv/bin/python -m unittest discover -s tests
```

The evaluator launches and stops its own service, so stop a manual service on
the chosen port first. The reported CPU cost is measured local compute time,
not a claim about cloud dollars or a free hosted service. The hundred-users/day
estimate assumes one successful submission each and reports startup separately.

## Troubleshooting

- Missing `.venv`: complete the install steps with the pinned Python version.
- Missing model files: run `prepare_model.py` with network access once, using
  the same `HF_HOME` as start. `--offline` only checks an existing cache.
- Port occupied: stop your earlier instance or set `PORT` to an unused local
  port before running `./start.sh`.
- Incomplete request evidence: inspect the foreground server's error log and
  ensure the selected `AI201_LOG_DIR` is writable.
- Startup failures: inspect `startup.jsonl` and the foreground error log; the
  worker does not become ready if loading fails. Preserve slow or failed runs
  with their timestamps rather than removing them from the evidence.

Prior unit commands remain in the repository (`run_eval.py`, `run_attacks.py`).
Their historical results and criteria are retained in README and
`docs/criteria-units7-8.md`; they do not replace the new capstone trials.
