#!/bin/sh
# Unit 9 Path B: one foreground, sequential worker on the local machine.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir"

if [ ! -x .venv/bin/python ] || [ ! -x .venv/bin/gunicorn ]; then
    printf '%s\n' 'Missing .venv. Follow the one-time setup in RUNNING.md.' >&2
    exit 1
fi

: "${HF_HOME:=$project_dir/.cache/huggingface}"
: "${PORT:=5057}"
export HF_HOME PORT
export HOST=127.0.0.1 AI201_DEBUG=0
export HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1
export HF_HUB_DISABLE_PROGRESS_BARS=1 TOKENIZERS_PARALLELISM=false

# Resolve a pinned local snapshot; no network request or model warm-up here.
AI201_DETECTOR_MODEL=$(.venv/bin/python prepare_model.py --offline)
export AI201_DETECTOR_MODEL
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

# No --preload: Torch must initialize inside the serving worker, not before fork.
exec .venv/bin/gunicorn app:app --config gunicorn.conf.py \
    --bind "127.0.0.1:$PORT" \
    --worker-class sync --workers 1 --threads 1 \
    --timeout 120 --graceful-timeout 30 \
    --access-logfile - --error-logfile -
