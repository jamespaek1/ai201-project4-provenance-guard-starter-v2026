"""Signal two: a transparent heuristic measuring text shape, not authorship.

The three measurements are sentence word-count variation, vocabulary repetition,
and Unicode punctuation density. The rule and constants were recorded before
implementation. Genre, length and small edits can change all three measurements;
none is evidence that an individual writer used AI.

Run independently with: python stylometry.py "some writing here"
"""

import re
import statistics
import unicodedata

import config


def sentences(text: str) -> list[str]:
    """Rough English sentence split after . ! or ? followed by whitespace.

    Abbreviations and quoted sentence endings can confuse this intentionally
    simple splitter. It is not a linguistic sentence-boundary model.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return [part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


def words(text: str) -> list[str]:
    """Casefold Unicode alphanumeric words; preserve internal apostrophes.

    Underscores and surrounding punctuation are separators. Straight and curly
    apostrophes inside a contraction are normalized to the same character.
    Numbers count as words, as in the starter. Unicode support does not make
    this English-language heuristic reliable for other languages.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    normalized = text.casefold().replace("’", "'")
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", normalized)


def _sentence_word_counts(text: str) -> list[int]:
    return [count for sentence in sentences(text) if (count := len(words(sentence)))]


def sentence_length_spread(text: str) -> float:
    """Population standard deviation / mean sentence word count.

    Return zero for fewer than two word-bearing sentences. The combining rule
    separately assigns neutral regularity in that case; it does not interpret
    an unmeasurable spread as evidence of perfectly regular writing.
    """
    counts = _sentence_word_counts(text)
    if len(counts) < 2:
        return 0.0
    return statistics.pstdev(counts) / statistics.mean(counts)


def type_token_ratio(text: str) -> float:
    """Unique words / total words, or zero when there are no words.

    This ratio is length-sensitive and is not comparable across arbitrary
    lengths. A low ratio contributes toward the heuristic's AI-oriented score.
    """
    tokens = words(text)
    return len(set(tokens)) / len(tokens) if tokens else 0.0


def punctuation_density(text: str) -> float:
    """Unicode punctuation (category P*) / non-whitespace characters.

    Includes full stops, apostrophes, dashes and quotation marks, but not symbols
    such as currency signs. Return zero for empty or whitespace-only input.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    characters = [character for character in text if not character.isspace()]
    if not characters:
        return 0.0
    return sum(unicodedata.category(character).startswith("P") for character in characters) / len(characters)


def style_signal(text: str) -> float:
    """Combine the three preregistered features into a finite 0–1 score.

    Higher is more AI-oriented under this heuristic, not more certain. Short
    inputs are shrunk toward neutral; empty text is neutral when called alone.
    The HTTP route independently rejects submissions shorter than 20 words.
    """
    tokens = words(text)
    counts = _sentence_word_counts(text)
    if len(counts) < 2:
        regularity = config.NEUTRAL_SCORE
    else:
        regularity = 1.0 - min(sentence_length_spread(text) / config.STYLE_SPREAD_CAP, 1.0)
    repetition = 1.0 - type_token_ratio(text)
    simplicity = 1.0 - min(punctuation_density(text) / config.STYLE_PUNCTUATION_SCALE, 1.0)
    raw = (
        config.STYLE_WEIGHT_REGULARITY * regularity
        + config.STYLE_WEIGHT_REPETITION * repetition
        + config.STYLE_WEIGHT_PUNCTUATION * simplicity
    )
    reliability = min(len(tokens) / config.STYLE_SHORT_TEXT_WORDS, 1.0)
    score = config.NEUTRAL_SCORE + reliability * (raw - config.NEUTRAL_SCORE)
    return min(max(score, 0.0), 1.0)


if __name__ == "__main__":
    import sys

    text = " ".join(sys.argv[1:]) or (
        "The system works well. It handles most cases correctly and provides "
        "good results. Users generally find it easy to use and understand."
    )
    print(f"{len(sentences(text))} sentence segments, {len(words(text))} words\n")
    print(f"sentence_length_spread   {sentence_length_spread(text)}")
    print(f"type_token_ratio         {type_token_ratio(text)}")
    print(f"punctuation_density      {punctuation_density(text)}")
    print(f"style_signal             {style_signal(text)}   (higher = more AI-oriented)")
