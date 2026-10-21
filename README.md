# Provenance Guard — Unit 7 instructor example

This is an AI-assisted instructor example built from the CodePath starter.
Codex authorship is disclosed; no personal hours, unaided student criteria,
human sample authorship or course submission will be invented.

## What This Does

A local, English-text demonstration for a writing site; it estimates patterns,
not authorship proof. It will not automatically remove writing or punish a writer.

The planned submission path, written before implementation:

1. Receive `POST /submit` JSON and validate `text` and `creator_id`.
2. Allocate a content ID after validation; reject invalid input before inference.
3. Run the supplied local GPT-2 predictability signal once (model cached in memory).
4. Measure sentence-length variation, vocabulary repetition and punctuation shape.
5. Combine the two scores with the rule below and map the result to one of three labels.
6. Append a decision with timestamp, IDs, both scores, combined score, label and status.
7. Return the decision and appeal instructions; an appeal appends a new event and
   makes the current status `under_review` while retaining the original decision.

### Endpoint contracts (decided before implementation)

`POST /submit`: JSON object with string `text` (20 or more words, at most 10,000
characters) and nonblank string `creator_id` (at most 100 characters). Returns
HTTP 200 with `content_id`, `creator_id`, `guess` (`human`, `unsure`, `ai`),
`confidence` (0–1 AI-oriented score, not correctness probability), `label`,
`model_score`, `style_score`, `status="decided"` and appeal instructions.
Request bodies are limited to 64 KiB. The model reads only its first 400 tokens;
the full input supplies the style signal. That mismatch will be disclosed.

`POST /appeal`: JSON object with an existing string `content_id` and nonblank
string `reasoning` (at most 2,000 characters). Returns HTTP 200 with content ID,
`status="under_review"` and confirmation. Unknown IDs return JSON 404; invalid
fields return JSON 400, oversized text/body 413, wrong Content-Type 415.
The original creator ID is taken from the stored decision, not an appeal claim.
This loopback classroom service has no authentication and is not a public
production moderation endpoint.

**Stretch declared before implementation:** `GET /content/<id>` returns the
stored decision, current status and appeal history. No third signal or verified
human credential is planned. Unit 8 rate limiting and attack trials are deferred.

### False-positive trace (illustrative, not a measured result)

A real writer could receive score 0.90 and the high-AI label even after writing
every word. The label says the tool can be wrong and invites an appeal; a
successful appeal preserves that decision, records their explanation, and moves
the item to under review without rescoring or automatic punishment. A human
review process would still need to be supplied by any real platform.

## Signals and Scoring

**Model signal — `detector.py::model_signal`:** the supplied GPT-2 measures next-token
predictability, mapped by `1 / (1 + (perplexity / 45)^1.6)`. This is a contextual
language-model signal, not an understanding of true authorship. Common human
phrasing or familiar/potentially memorized passages can score high; uncommon
words, edits or a different genre can make generated prose score low. Keep the
starter model and mapping unchanged.

**Style signal — `stylometry.py::style_signal`:** planned features are sentence
word-count coefficient of variation (population standard deviation / mean),
type-token ratio, and Unicode punctuation characters divided by non-whitespace
characters. A deliberately limited heuristic: regular sentences and repeated
words may arise in generated templates, but human genres, second-language prose,
length and editing also change these statistics. It cannot read meaning, and
style and model scores can correlate despite measuring different properties.

### Combining rule — recorded before code or results

All constants belong in `config.py`; implementation belongs in
`scoring.py::combine_signals`.

- Sentence regularity = `1 - min(CV, 1)`; use neutral 0.5 for fewer than two
  nonempty sentences.
- Repetition = `1 - unique_words / total_words`.
- Punctuation simplicity = `1 - min(punctuation_density / 0.15, 1)`.
- Raw style = `0.50 * regularity + 0.35 * repetition + 0.15 * simplicity`.
  For fewer than 40 words, shrink style toward 0.5 by `min(words / 40, 1)`.
- Raw combined score = **0.75 × model + 0.25 × style**.
- If the absolute difference between the signal scores is **at least 0.50**,
  use `0.5 + 0.5 * (raw_combined - 0.5)` to move the score into the unsure band.
  Otherwise use the raw combined score. This guard keeps disagreement visible
  instead of letting one strong heuristic become an accusation.
- Human: **0 ≤ score ≤ 0.20**; unsure: **0.20 < score < 0.85**;
  AI: **0.85 ≤ score ≤ 1**. Reject nonfinite/out-of-range scores.

The model has more weight because it uses context; style is a weak, editable
heuristic. The wide unsure interval and high AI cutoff prioritize avoiding false
accusations. These are design choices, not empirically calibrated probabilities.
A false negative remains possible and is preferable here to automated punishment.

## Label Variants

| Label | Exact range | Exact user-facing text |
|---|---|---|
| High-confidence human | [0, 0.20] | This writing looks more consistent with human writing to our tools. This is an estimate, not proof of authorship. You can request a review if this label seems wrong. |
| Unsure | (0.20, 0.85) | Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review. |
| High-confidence AI | [0.85, 1] | Our tools found patterns often associated with AI-generated writing. They can be wrong; this is not proof of how you wrote it. You can explain your process and request a review. |

The unsure text does not imply cheating and tells the writer what they can do.
The words high-confidence name score bands, not validated confidence in a fact.

## Sample Run

Pending actual execution; no sample response or model result has been invented.
The five criteria in [criteria.md](criteria.md) are committed before implementation
and before any detector results. Actual requests, responses and log entries will
be added after the service works.

## How I Used AI

The instructor requested completion; Codex is preparing the implementation,
criteria and documentation with explicit AI provenance. Two concrete development
moments and the actual resulting changes will be recorded after they occur.
