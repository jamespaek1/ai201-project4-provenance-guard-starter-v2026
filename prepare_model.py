#!/usr/bin/env python3
"""Prepare or locate the exact GPT-2 files used for the Unit 9 capstone.

This resolves files only: it does not import Torch, load a model, or run inference.
The path on stdout is consumed by start.sh; diagnostics go to stderr.
"""

import argparse
import os
from pathlib import Path
import sys

MODEL_REPO = "gpt2"
MODEL_REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"
MODEL_FILES = (
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
)


def resolve_model(*, offline: bool) -> Path:
    # Set these before importing huggingface_hub, which reads its environment
    # at import time. Neither authentication nor telemetry is needed here.
    root = Path(__file__).resolve().parent
    os.environ.setdefault("HF_HOME", str(root / ".cache" / "huggingface"))
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    from huggingface_hub import snapshot_download

    snapshot = Path(snapshot_download(
        repo_id=MODEL_REPO,
        revision=MODEL_REVISION,
        allow_patterns=list(MODEL_FILES),
        local_files_only=offline,
        token=False,
    ))
    missing = [name for name in MODEL_FILES
               if not (snapshot / name).is_file()
               or (snapshot / name).stat().st_size == 0]
    if missing:
        raise FileNotFoundError("Pinned snapshot is incomplete: " + ", ".join(missing))
    return snapshot.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true",
                        help="require the pinned files already cached; never download")
    args = parser.parse_args()
    try:
        print(resolve_model(offline=args.offline))
    except Exception as exc:
        print(f"Model setup failed: {exc}", file=sys.stderr)
        print("Run .venv/bin/python prepare_model.py once with network access "
              "and the same HF_HOME.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
