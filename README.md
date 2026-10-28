# Provenance Guard — Unit 7 instructor example

This is an AI-assisted instructor example built from the CodePath starter.
Codex authorship is disclosed. The service, criteria, real-model calibration,
audit trail and Unit 7 write-up are complete. No personal hours, unaided student
work or course-portal submission are claimed. Unit 8 evaluation is separate.

## What This Does

A local, English-text demonstration for a writing site; it estimates patterns,
not authorship proof. It will not automatically remove writing or punish a writer.

The submission path was committed before implementation and is now implemented:

1. Receive `POST /submit` JSON and validate `text` and `creator_id`.
2. Check word, character and byte limits; reject invalid input before inference.
3. Run the supplied local GPT-2 predictability signal once (model cached in memory).
4. Measure sentence-length variation, vocabulary repetition and punctuation shape.
5. Combine the two scores with the rule below and map the result to one of three labels.
6. Allocate a content ID and append a decision with timestamp, IDs, both scores,
   combined score, label and status.
7. Return the decision and appeal instructions; an appeal appends a new event and
   makes the current status `under_review` while retaining the original decision.

### Endpoint contracts (decided before implementation)

`POST /submit`: JSON object with string `text` (20 or more words, at most 10,000
characters) and nonblank string `creator_id` (at most 100 characters). Returns
HTTP 200 with `content_id`, `creator_id`, `guess` (`human`, `unsure`, `ai`),
`confidence` (0–1 AI-oriented score, not correctness probability), `label`,
`model_score`, `style_score`, `status="decided"` and appeal instructions.
Request bodies are limited to 64 KiB. The model reads only its first 400 tokens;
the full input supplies the style signal. That mismatch is a limitation.

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
starter model and mapping unchanged, as this implementation does.

**Style signal — `stylometry.py::style_signal`:** the features are sentence
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

The source preserves the declared rule and thresholds without post-result tuning.
Scores are not rounded before label mapping. Decimal comparison at the 0.50
disagreement boundary avoids treating `0.70 - 0.20` as slightly below 0.50 due to
binary floating-point representation. Words use Unicode alphanumerics and
internal apostrophes (case-folded); underscores do not count as words. Sentence
splitting is a rough punctuation-based heuristic, and sentences with no words
are excluded from the coefficient of variation. Empty standalone style input
returns neutral 0.5; the HTTP endpoint rejects empty or too-short input first.

## Label Variants

| Label | Exact range | Exact user-facing text |
|---|---|---|
| High-confidence human | [0, 0.20] | This writing looks more consistent with human writing to our tools. This is an estimate, not proof of authorship. You can request a review if this label seems wrong. |
| Unsure | (0.20, 0.85) | Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review. |
| High-confidence AI | [0.85, 1] | Our tools found patterns often associated with AI-generated writing. They can be wrong; this is not proof of how you wrote it. You can explain your process and request a review. |

The unsure text does not imply cheating and tells the writer what they can do.
The words high-confidence name score bands, not validated confidence in a fact.

### Actual calibration and signal disagreement

The seven development specimens and sources were committed before any model
outputs were seen. Human excerpts are from Carroll, the Declaration of
Independence and Joyce; the other fixtures have explicit AI or mixed provenance.
The user did not write these specimens. See [source notes](examples/SOURCES.md)
and [complete frozen texts](examples/calibration.json).

| Fixture | Known provenance | GPT-2 score | Style score | Combined score | Actual label |
|---|---|---:|---:|---:|---|
| `human_narrative` | Human: Carroll | 0.5855 | 0.4793 | 0.5589 | unsure |
| `human_formal` | Human: Declaration | 0.9915 | 0.4901 | 0.6831 | unsure |
| `human_literary` | Human: Joyce | 0.1261 | 0.3153 | 0.1734 | human |
| `ai_generic` | AI-generated | 0.7285 | 0.6301 | 0.7039 | unsure |
| `ai_repetitive` | AI-generated, deliberately repetitive | 0.9842 | 0.9106 | 0.9658 | ai |
| `ai_lightly_edited` | AI-generated and AI-edited | 0.6582 | 0.5268 | 0.6253 | unsure |
| `mixed_narrative` | Human excerpt + AI continuation | 0.6179 | 0.2863 | 0.5350 | unsure |

**A case where the signals split:** the human-authored Declaration excerpt has
model score **0.9915** but style score **0.4901**, a gap of **0.5014**. Its raw
weighted score is **0.8661**, which would receive the AI label without the
preregistered disagreement guard; the guard moves it to **0.6831, unsure**.
This makes the false-positive risk concrete without claiming the guard always
protects a human writer. The work is famous and may be familiar to GPT-2;
predictability does not establish authorship.

All three labels are reached through real HTTP submissions: Joyce is human,
the repetitive AI specimen is AI, and the other five are unsure. Formal human
writing and lightly edited AI both remain unsure, for different signal values.
The generic and edited AI pieces are **not** confidently detected, a useful
limitation rather than an omitted result. These seven selected development
examples do not estimate accuracy, satisfy the 20+20 evaluation criteria, or
replace Unit 8's independent attacks and three trials.

## Sample Run

These are actual `curl` requests and JSON responses from the local service on
**2026-10-21**, using the completed two-signal scoring implementation. Values below are copied
from [live evidence](evidence/05-live-service.json); nothing is a fabricated
terminal transcript. The sample text is a disclosed AI-generated fixture and
the appeal is explicitly a test, not a claim that a person wrote it.
This run precedes the final request-body validation fix; scoring and labels are
unchanged. A separate [final regression run](evidence/08-streamed-body-regression.json)
records the patched source commit and real HTTP verification.

**A submission**

```sh
curl --silent --show-error -X POST http://127.0.0.1:5057/submit \
  -H 'Content-Type: application/json' \
  --data-binary @examples/sample-submit.json
```

The exact request file contains:

```json
{
  "text": "The team will make a plan for the project. The team will share the plan with the group. The team will discuss the plan with the group. The team will review the plan with the group. The team will make a list of the tasks. The team will share the list with the group. The team will discuss the list with the group. The team will review the list with the group. The team will set a date for the meeting. The team will share the date with the group. The team will discuss the date with the group. The team will review the date with the group.",
  "creator_id": "sample-run"
}
```

Actual HTTP 200 response:

```json
{
  "appeal": {
    "endpoint": "/appeal",
    "method": "POST",
    "required_fields": [
      "content_id",
      "reasoning"
    ]
  },
  "combined_score": 0.9657959246369339,
  "confidence": 0.9657959246369339,
  "content_id": "6631bd5c-f449-48ec-ad10-656d3128e7e9",
  "creator_id": "sample-run",
  "guess": "ai",
  "implementation_stage": "two_signals",
  "label": "Our tools found patterns often associated with AI-generated writing. They can be wrong; this is not proof of how you wrote it. You can explain your process and request a review.",
  "model_score": 0.9842,
  "score_meaning": "Higher scores indicate more AI-associated patterns; this is not an authorship probability.",
  "status": "decided",
  "style_score": 0.9105836985477356,
  "timestamp": "2026-10-21T22:17:02+00:00"
}
```

`confidence` and `combined_score` are the same AI-oriented heuristic score:
0 means human-like patterns and 1 means AI-like patterns. A low score is not
low certainty about the human band; the number is not a calibrated probability.
The separately returned signal scores keep later diagnosis possible.

**An appeal**

```sh
curl --silent --show-error -X POST http://127.0.0.1:5057/appeal \
  -H 'Content-Type: application/json' \
  --data-binary @examples/sample-appeal.json
```

Exact request (use a newly returned content ID when reproducing a new run):

```json
{
  "content_id": "6631bd5c-f449-48ec-ad10-656d3128e7e9",
  "reasoning": "For this demonstration, please review the process notes for this sample. This is a test appeal, not a claim of human authorship."
}
```

Actual HTTP 200 response:

```json
{
  "content_id": "6631bd5c-f449-48ec-ad10-656d3128e7e9",
  "message": "Your explanation has been recorded and this item is under review. The original estimate remains in the history; no new assessment was made.",
  "reasoning": "For this demonstration, please review the process notes for this sample. This is a test appeal, not a claim of human authorship.",
  "status": "under_review"
}
```

**What the log shows afterwards**

```sh
curl --silent --show-error 'http://127.0.0.1:5057/log?limit=2'
```

Actual HTTP 200 response:

```json
{
  "count": 2,
  "entries": [
    {
      "combined_score": 0.9657959246369339,
      "content_id": "6631bd5c-f449-48ec-ad10-656d3128e7e9",
      "creator_id": "sample-run",
      "guess": "ai",
      "implementation_stage": "two_signals",
      "label": "Our tools found patterns often associated with AI-generated writing. They can be wrong; this is not proof of how you wrote it. You can explain your process and request a review.",
      "model_score": 0.9842,
      "status": "decided",
      "style_score": 0.9105836985477356,
      "timestamp": "2026-10-21T22:17:02+00:00"
    },
    {
      "content_id": "6631bd5c-f449-48ec-ad10-656d3128e7e9",
      "creator_id": "sample-run",
      "event": "appeal",
      "reasoning": "For this demonstration, please review the process notes for this sample. This is a test appeal, not a claim of human authorship.",
      "status": "under_review",
      "timestamp": "2026-10-21T22:17:02+00:00"
    }
  ]
}
```

The original decision remains `decided` as a historical event; the later appeal
makes the item's **current** status `under_review`. `GET /content/<id>` merges
that original decision with current status and appeal history. The actual server
was stopped and restarted; [restart evidence](evidence/06-restart.json) shows the
same appeal and status still present while `detector_loaded` is false. Reading
an appeal did not reload or call the model. This is a recorded request for
review; this demonstration does not contain a staffed reviewer workflow.

### Verification and reproducibility

- All **12 contract tests pass**, including the 1,001-point label sweep, boundary
  values, NaN/infinity rejection, input-size/type errors without inference,
  append-only appeal semantics, and ten appeals read by a fresh Python process.
  [Test output](evidence/unit-tests.log). The tests isolate their audit file and
  mock the detector; the live calibration above uses the actual model.
- Seven frozen specimens were submitted through actual HTTP with both signals;
  all three labels were observed. One additional submission and appeal produced
  the pasted sample and survived a real service restart. [Live run](evidence/05-live-service.json).
- The [final body-limit regression](evidence/08-streamed-body-regression.json) verifies
  that oversized JSON and non-JSON bodies on both write routes return JSON 413
  before loading the detector or changing the audit log, with both Content-Length
  and chunked transfer. A body exactly 64 KiB proceeds to media-type validation;
  65,537 streamed bytes return 413. The unchanged `/ping` control, persisted
  earlier appeal, and a new real-model submission and appeal also pass. Evidence
  hashes describe the log at each recorded point, before subsequent append-only runs.
  The [earlier body-limit run](evidence/07-body-limit-regression.json) is retained
  as staged evidence preceding the streamed-body correction.
- [Initial routing evidence](evidence/01-routing-only.json) clearly identifies its
  hardcoded development response. [Standalone model scores](evidence/02-model-signal.json)
  precede [one-signal HTTP integration](evidence/03-one-signal-http.json), followed
  by [both-signal measurements](evidence/04-two-signals.json). The first entry in
  the committed audit log is the historical one-signal stage; its null style and
  combined scores are explicitly marked. All later decision entries carry both
  real signals and the combined score.
- The five [criteria](criteria.md), pipeline contract, scoring rule and stretch
  choice were committed at `753217e` before implementation and any detector
  outputs. Their original targets are unchanged. Detector code, its GPT-2 model
  mapping and the `/ping` control handler are unchanged from the starter.
- The course [environment check](evidence/environment.log) records **7 passes,
  1 disk-space failure and 1 cache-path warning**. It requests 9 GB free and the
  machine had about 2.2 GB after installation. Its model check inspects only
  `~/.cache/huggingface`; this project uses `HF_HOME=.cache/huggingface` and the
  actual model runs succeeded. These checks have not been rewritten to hide the
  results. The API and tests ran successfully, but free space remains a local
  setup limitation for further installs or large logs.

To run locally with the existing environment:

```sh
export HF_HOME="$PWD/.cache/huggingface"
AI201_DEBUG=0 PORT=5057 .venv/bin/python app.py
```

Then use the `curl` commands above in a second terminal. Port 5057 was chosen for
this demonstration; the starter default remains 5000 unless `PORT` is set.
For a fresh checkout use supported Python 3.11–3.13, create `.venv`, and install
[requirements.txt](requirements.txt); [RUNNING.md](RUNNING.md) retains the starter's
setup reference. No hosted AI service or API key is used.

```sh
.venv/bin/python -m unittest discover -s tests -v
```

`POST /submit` rejects bad input before inference: JSON media type is required,
text must have at least 20 words and at most 10,000 characters, creator IDs must
be nonblank strings of at most 100 characters, and bodies are limited to 64 KiB.
Malformed JSON/types return 400, non-JSON media returns 415, and oversized
text/body returns 413. A missing model returns 503 without fabricating a score;
a text the model cannot score returns 422. Appeals require an existing ID and
nonblank reasoning of at most 2,000 characters; unknown content returns 404.
Reasoning is stored exactly, and no appeal overwrites or reverses the decision.

The server is intentionally loopback-only by default. Creator IDs are supplied
by callers and are **not authentication**; production identity, authorization,
review staffing, durable multi-process storage and privacy controls are outside
this classroom build. Logs contain IDs, scores and appeal reasoning; committed
demo IDs and reasoning are synthetic. The first 400 model tokens versus full-text
style features, heuristic sentence splitting, known-prose familiarity and genre
bias remain limitations. Nothing here establishes an author cheated.

## How I Used AI

**Disclosure:** this is the instructor-authorized AI-assisted example continuing
the prior projects. Codex wrote the five criteria, code and report and executed
the tests. No unaided student work, user-authored samples, human review, personal
hours or course-portal submission is claimed.

**Moment 1 — building in observable stages.** The instructor asked to complete
Unit 7. Codex turned the brief into a committed endpoint contract and scoring
plan, then first returned an explicitly marked hardcoded route response. After
real standalone detector measurements, the code replaced the stub with a real
0.7285 model score for the generic AI example and verified that an audit event
was written; later it added the separate style signal, final labels and appeals.
The retained stage evidence shows those changes rather than presenting the
initial stub as a working detector.

**Moment 2 — testing an exact disagreement boundary.** An AI implementation/review
pass checked the rule at model 0.70 versus style 0.20. Binary subtraction can
produce 0.49999999999999994, so code that compares that directly with 0.50 can
skip the intended uncertainty guard. The implementation now compares the decimal
representations at that boundary, and a regression test checks both the exact
boundary and a neighboring value. This changed numeric behavior to match the
already committed rule; it did not tune the weights or criteria after results.

AI also drafted and reviewed the source-provenance records. Public-domain human
excerpts are attributed; generated, edited and mixed specimens are labeled as
such. The formal-human false-positive risk and undetected generic AI were
retained in the report. An independent AI code/report review is additional
checking, not independent human validation of detection accuracy.

That review caught a validation-order defect: an oversized non-JSON body returned
415 before the byte limit was enforced. The service now reads the bounded body
in a pre-request hook, so every oversized body returns 413 first. Regression
tests cover both write routes, both media types, and multibyte input. A follow-up
check found that Werkzeug can truncate a chunked body at its stream cap without
raising. The guard now allows one bounded lookahead byte and explicitly compares
the cached body's byte count to 64 KiB. Exact-limit and oversized streamed inputs
are tested; live HTTP checks verify rejected requests neither load the model nor
alter the log. The original criterion and all scoring constants are unchanged.

### Unit 7 completion and Unit 8 handoff

Unit 7's required endpoints, two distinct signals, variable score, three exact
labels, appeal audit trail, five preregistered criteria, five README sections
and at least four new commits are present. The declared stretch
`GET /content/<id>` is implemented and verified. Nothing has been submitted
through the course portal.

Unit 8's rate limits, independent attack set, fixed 20+20 provenance corpus,
three-trial criterion verdicts and measured improvement have **not** been run
or claimed. The original `run_eval.py`, `run_attacks.py` and `scenarios.py` remain
available for that next task. Use this same fork for Unit 8:
[jamespaek1/ai201-project4-provenance-guard-starter-v2026](https://github.com/jamespaek1/ai201-project4-provenance-guard-starter-v2026).

## Rate Limiting

Unit 8 plan, recorded before implementation and before opening the staff attack
inputs: enable **10 submissions per minute and 120 per day per creator**. Ten
allows a writer to revise several passages while restricting a script's burst;
120 bounds sustained probing for that claimed identity. These are classroom
policy choices, not measurements of normal writer traffic.

**Declared Unit 8 stretch: per-creator limits.** The starter's caller key already
uses a claimed creator ID; this unit will enable that policy and use the remote
address when a valid creator ID is unavailable. Shared-address writers can have
separate quotas, but callers can evade them by inventing new IDs because this
service has no authentication. Memory-only counters reset with a process restart
and are not shared across workers. A production service needs verified identity,
shared storage and a complementary address/global budget.

The baseline will add only limiting and rejection logging. The five original
criteria and the two signals, weights, thresholds and labels remain fixed until
the before runs are committed and a diagnosis selects one measured improvement.
The instructor-example authorship disclosure from Unit 7 continues to apply.

Milestone 1 verified on 2026-10-28, before opening the staff inputs:

```text
200 200 200 200 200 200 200 200 200 200 429 429 429 429 429
```

The [15-request flood](results/flood_2026-10-28_183550_762597.json) used one
creator. Five rejections appear once each in the audit log. Three additional
real submissions have all nine decision fields and are returned by `/log`;
a missing-text refusal is recorded too ([HTTP evidence](results/milestone1-http.json)).
All 17 contract/instrument tests passed ([output](results/milestone1-tests.log)).
Rejections are written by one response hook, including malformed, oversized,
wrong-media and rate-limited requests, without inventing decision scores.
