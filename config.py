"""
Settings for Provenance Guard.

Everything you're likely to change lives here, at the top, on purpose.

You'll edit the thresholds in Milestone 5 and the rate limits in unit 8.
"""

import os
from pathlib import Path

ROOT = Path(__file__).parent


# ─── The service ─────────────────────────────────────────────────────────────

# `127.0.0.1` is loopback — only your own machine can reach it, which is what
# you want all through units 7 and 8. A host somewhere else has to accept
# traffic from outside the box, and that means `0.0.0.0`. Setting the env var
# is how you get it; the default keeps your local `curl` commands unchanged.
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))

# Flask's debug mode gives anyone who can reach the service an interactive
# Python prompt inside your process. Fine on loopback, a gift to strangers
# anywhere else — so it turns itself off the moment HOST isn't loopback.
DEBUG = os.getenv("AI201_DEBUG", "1") == "1" and HOST in ("127.0.0.1", "localhost")


# ─── The local model ─────────────────────────────────────────────────────────
# Your first signal runs a language model ON YOUR OWN MACHINE. No account, no
# key, no card. It downloads about 550 MB the first time — do that before
# class, not during it.
#
# What it measures: how *predictable* your text is to a language model. Text a
# model finds easy to predict tends to be text a model wrote.
#
# The first call is the slow one — ten to twenty seconds while the model loads,
# longer on an older laptop. After that it stays in memory and a submission
# takes a second or two. That cost is part of what you're learning: this is
# what running a model inline in a request actually looks like.

DETECTOR_MODEL = os.getenv("AI201_DETECTOR_MODEL", "gpt2")

# Longer text gives a steadier reading but takes longer. 400 tokens is roughly
# 300 words, which is enough for the signal to mean something.
DETECTOR_MAX_TOKENS = 400


# ─── Scoring (Milestone 4) ───────────────────────────────────────────────────
# Written in README and committed before implementation or detector results.
# These are heuristic design choices, not calibrated authorship probabilities.
WEIGHT_MODEL_SIGNAL = 0.75
WEIGHT_STYLE_SIGNAL = 0.25

NEUTRAL_SCORE = 0.5
SIGNAL_DISAGREEMENT_THRESHOLD = 0.50
DISAGREEMENT_SHRINK_FACTOR = 0.5

STYLE_WEIGHT_REGULARITY = 0.50
STYLE_WEIGHT_REPETITION = 0.35
STYLE_WEIGHT_PUNCTUATION = 0.15
STYLE_SPREAD_CAP = 1.0
STYLE_PUNCTUATION_SCALE = 0.15
STYLE_SHORT_TEXT_WORDS = 40


# ─── Thresholds (Milestone 5) ────────────────────────────────────────────────
# Where one label becomes another. Scores run 0.0 (confidently human) to 1.0
# (confidently AI).
#
#   score <= HUMAN_THRESHOLD         -> high-confidence human
#   HUMAN_THRESHOLD < score < AI_THRESHOLD -> unsure
#   score >= AI_THRESHOLD            -> high-confidence AI
# The wide unsure interval prioritizes avoiding false accusations. The names
# identify score bands, not verified certainty about a writer's authorship.
HUMAN_THRESHOLD = 0.20
AI_THRESHOLD = 0.85


# ─── Rate limiting (UNIT 8) ──────────────────────────────────────────────────
# Off in Unit 7; enabled by default in Unit 8, Milestone 1.
#
# Think about two people: a real writer submitting their own work a few times
# an hour, and a script sending a thousand variations to map your thresholds.
# Your README has to say why your numbers and not others.

RATE_LIMITING_ENABLED = os.getenv("AI201_RATE_LIMITS", "1") == "1"

RATE_LIMIT_PER_MINUTE = 10
RATE_LIMIT_PER_DAY = 120

# Flask-Limiter warns loudly without this. In-memory is right for one laptop
# and wrong for anything real — a restart forgets every count, and two copies
# of the service wouldn't share limits.
RATE_LIMIT_STORAGE = "memory://"


# ─── Paths ───────────────────────────────────────────────────────────────────

LOG_DIR = ROOT / "logs"
AUDIT_LOG = LOG_DIR / "audit.jsonl"
RESULTS_DIR = ROOT / "results"

# Unit 7 input contract. Bounds apply before either signal runs.
MAX_REQUEST_BYTES = 64 * 1024
MIN_TEXT_WORDS = 20
MAX_TEXT_CHARACTERS = 10_000
MAX_CREATOR_CHARACTERS = 100
MAX_REASONING_CHARACTERS = 2_000
