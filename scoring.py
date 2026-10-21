"""Combine different heuristic signals and communicate uncertainty.

The rule was recorded in README before implementation. A score is oriented from
human-like patterns (0) to AI-like patterns (1); it is not a calibrated probability
that either authorship claim is correct. No scores are rounded before labeling.
"""

import math
from decimal import Decimal
from numbers import Real

import config


LABEL_TEXT = {
    "human": (
        "This writing looks more consistent with human writing to our tools. "
        "This is an estimate, not proof of authorship. You can request a review "
        "if this label seems wrong."
    ),
    "unsure": (
        "Our tools cannot confidently tell how this writing was produced. "
        "This label is not an accusation. You can add context and request a review."
    ),
    "ai": (
        "Our tools found patterns often associated with AI-generated writing. "
        "They can be wrong; this is not proof of how you wrote it. You can "
        "explain your process and request a review."
    ),
}


def _score(value: float, name: str) -> float:
    """Reject invalid scores instead of clipping them into a trusted label."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number from 0 through 1")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be a finite number from 0 through 1")
    return number


def combine_signals(model_score: float, style_score: float) -> float:
    """Use 75% model and 25% style, shrinking strong disagreement toward 0.5.

    If the scores differ by at least 0.50, halve the combined score's distance
    from 0.5. Such disagreement therefore stays in the unsure band. The constants
    live in config.py. Returned values retain precision through label mapping.
    """
    model_score = _score(model_score, "model_score")
    style_score = _score(style_score, "style_score")
    raw = config.WEIGHT_MODEL_SIGNAL * model_score + config.WEIGHT_STYLE_SIGNAL * style_score
    # Compare the decimal score values so an exact .70 - .20 boundary does not
    # become .49999999999999994 and accidentally skip the disagreement guard.
    gap = abs(Decimal(str(model_score)) - Decimal(str(style_score)))
    if gap >= Decimal(str(config.SIGNAL_DISAGREEMENT_THRESHOLD)):
        raw = config.NEUTRAL_SCORE + config.DISAGREEMENT_SHRINK_FACTOR * (raw - config.NEUTRAL_SCORE)
    return _score(raw, "combined_score")


def score_to_label(score: float) -> tuple[str, str]:
    """Map [0,.20] to human, (.20,.85) to unsure, and [.85,1] to AI."""
    score = _score(score, "score")
    if score >= config.AI_THRESHOLD:
        guess = "ai"
    elif score <= config.HUMAN_THRESHOLD:
        guess = "human"
    else:
        guess = "unsure"
    return guess, LABEL_TEXT[guess]


def label_ranges() -> list[tuple[str, str]]:
    """Return exact nonoverlapping bands, with inclusive/exclusive notation."""
    return [
        ("high-confidence human", f"[0.00, {config.HUMAN_THRESHOLD:.2f}]"),
        ("unsure", f"({config.HUMAN_THRESHOLD:.2f}, {config.AI_THRESHOLD:.2f})"),
        ("high-confidence AI", f"[{config.AI_THRESHOLD:.2f}, 1.00]"),
    ]
