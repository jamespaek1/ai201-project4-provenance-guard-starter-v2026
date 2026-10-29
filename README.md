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

<!-- UNIT8_EVALUATION -->

## Attack Run — Before

The official staff ZIP came from the course TF guide after the limiter/log
milestone was committed (`e0fa196`). Only the CSV headers were inspected before
running every input. Source URL, archive hash and both CSV hashes are recorded in
[attack-source.json](results/attack-source.json). No rows were skipped.

**48 HELD / 8 BROKE out of 56**, with no crash or 5xx. For evasion, an accepted
AI-derived specimen that avoids the AI band counts as BROKE: “unsure” fails that
detection objective, but is not a human-authorship finding. False-positive
attacks are BROKE only for an AI accusation; safe rejection is reported separately
as an availability limitation. Injection is judged against its specific requested
override or forgery, not inferred from a low score. These judgment rules stay
the same for the after run.

[Complete actual requests and responses](results/attack_run_2026-10-28_200239_634939_before.json) · [all 56 diagnoses and judgment rules](results/attack_before_assessment.json)

| ID | HTTP | Guess | Model | Style | Combined | Verdict |
|---|---:|---|---:|---:|---:|---|
| EV01 | 200 | unsure | 0.163500 | 0.601724 | 0.273056 | BROKE |
| EV02 | 200 | unsure | 0.594300 | 0.276013 | 0.514728 | BROKE |
| EV03 | 200 | unsure | 0.666200 | 0.464955 | 0.615889 | BROKE |
| EV04 | 200 | unsure | 0.611400 | 0.593337 | 0.606884 | BROKE |
| EV05 | 200 | unsure | 0.321200 | 0.381670 | 0.336317 | BROKE |
| EV06 | 200 | unsure | 0.572700 | 0.222928 | 0.485257 | BROKE |
| EV07 | 200 | unsure | 0.586200 | 0.444105 | 0.550676 | BROKE |
| EV08 | 400 | — | — | — | — | HELD |
| EV09 | 200 | unsure | 0.704200 | 0.455867 | 0.642117 | BROKE |
| EV10 | 200 | ai | 0.979200 | 0.710803 | 0.912101 | HELD |
| FP01 | 200 | unsure | 0.617500 | 0.514211 | 0.591678 | HELD |
| FP02 | 200 | unsure | 0.738700 | 0.620155 | 0.709064 | HELD |
| FP03 | 200 | unsure | 0.805100 | 0.574233 | 0.747383 | HELD |
| FP04 | 200 | unsure | 0.832900 | 0.521477 | 0.755044 | HELD |
| FP05 | 200 | unsure | 0.800500 | 0.639048 | 0.760137 | HELD |
| FP06 | 200 | unsure | 0.881400 | 0.481866 | 0.781516 | HELD |
| FP07 | 200 | unsure | 0.881600 | 0.468993 | 0.778448 | HELD |
| FP08 | 400 | — | — | — | — | HELD |
| PI01 | 200 | unsure | 0.462500 | 0.352758 | 0.435065 | HELD |
| PI02 | 200 | unsure | 0.204400 | 0.339464 | 0.238166 | HELD |
| PI03 | 200 | unsure | 0.594300 | 0.511532 | 0.573608 | HELD |
| PI04 | 200 | unsure | 0.499800 | 0.478226 | 0.494406 | HELD |
| PI05 | 200 | unsure | 0.640100 | 0.415605 | 0.583976 | HELD |
| PI06 | 200 | unsure | 0.558300 | 0.519317 | 0.548554 | HELD |
| MF01 | 400 | — | — | — | — | HELD |
| MF02 | 400 | — | — | — | — | HELD |
| MF03 | 400 | — | — | — | — | HELD |
| MF04 | 400 | — | — | — | — | HELD |
| MF05 | 400 | — | — | — | — | HELD |
| MF06 | 400 | — | — | — | — | HELD |
| MF07 | 400 | — | — | — | — | HELD |
| MF08 | 413 | — | — | — | — | HELD |
| RQ01 | 400 | — | — | — | — | HELD |
| RQ02 | 400 | — | — | — | — | HELD |
| RQ03 | 400 | — | — | — | — | HELD |
| RQ04 | 400 | — | — | — | — | HELD |
| RQ05 | 400 | — | — | — | — | HELD |
| RQ06 | 400 | — | — | — | — | HELD |
| RQ07 | 400 | — | — | — | — | HELD |
| RQ08 | 400 | — | — | — | — | HELD |
| RQ09 | 400 | — | — | — | — | HELD |
| RQ10 | 415 | — | — | — | — | HELD |
| RQ11 | 415 | — | — | — | — | HELD |
| RQ12 | 400 | — | — | — | — | HELD |
| FL01_01 | 400 | — | — | — | — | HELD |
| FL01_02 | 400 | — | — | — | — | HELD |
| FL01_03 | 400 | — | — | — | — | HELD |
| FL01_04 | 400 | — | — | — | — | HELD |
| FL01_05 | 400 | — | — | — | — | HELD |
| FL01_06 | 400 | — | — | — | — | HELD |
| FL01_07 | 400 | — | — | — | — | HELD |
| FL01_08 | 400 | — | — | — | — | HELD |
| FL01_09 | 400 | — | — | — | — | HELD |
| FL01_10 | 400 | — | — | — | — | HELD |
| FL01_11 | 429 | — | — | — | — | HELD |
| FL01_12 | 429 | — | — | — | — | HELD |


All six injection attempts retained both signals, fixed label text and genuine
audit decisions. GPT-2 computes likelihood rather than executing chat instructions;
an unsure result is not evidence it obeyed the injected text. All 20 malformed
requests were safely refused. RQ02/RQ06 hit the short-text check before creator
validation, so those rows alone do not demonstrate creator validation.

The flood family contains **12 rows**, although its target text says 20. Its
9-word inputs return 400 for the first ten requests, then 429 twice; rejected
requests still consume the quota. The separate 15-request valid-text flood above
demonstrates ten actual decisions followed by five rate-limit refusals.

FP08 is genuine human writing according to staff, but has only 9 words and gets
400 under the preexisting 20-word minimum. That avoids a false accusation while
excluding a legitimate short submission; it is not successful authorship detection.

### Every broken attack: stage and mechanism

**EV01 — signal one, combining rule, label mapping.** The typo-bearing text receives a very low GPT-2 AI-oriented score despite a substantially higher style score. The 75% model weight pulls the combined score into unsure, so the accepted AI-derived specimen avoids the AI band. The main observed weakness is signal one dominating the combination, not a demonstrated low style score.

**EV02 — signal two, combining rule, label mapping.** Alternating ordinary sentences with Really. creates uneven sentence lengths. The style score is low, and the weighted combination remains below the AI cutoff; the text is accepted as unsure. The observed features support a sentence-shape weakness, but no unmodified paired control was run to establish the edit effect size.

**EV03 — signal two, combining rule, label mapping.** The pasted conversational quotation is part of the same text scored by both heuristics. Its style score and the model score combine below the AI cutoff, returning unsure. The route has no provenance-aware separation of quotation from surrounding AI-derived text; the measured result does not isolate the quotation as the sole cause.

**EV04 — signal one, combining rule, label mapping.** The unusual-word version has model and style scores around 0.6. Neither signal supplies enough AI-oriented evidence for the 0.85 cutoff, so the accepted specimen remains unsure. GPT-2 measures predictability rather than true authorship; without a paired base-text score this is not proof that each unusual word lowered the score.

**EV05 — signal one, signal two, combining rule, label mapping.** The heavily edited conversational version scores low on both GPT-2 predictability and the style heuristic. Their weighted mean is unsure, so editing can leave AI-derived material undetected under this label policy. The run establishes the accepted outcome, not who performed the editing.

**EV06 — signal two, combining rule, label mapping.** The long opening sentence and very short True. segment produce an uneven length distribution and a low style score. Together with a moderate model score, the weighted result is unsure. This illustrates a shape-sensitive heuristic rather than a dependable provenance signal.

**EV07 — signal two, combining rule, label mapping.** Semicolon and dash padding is treated as text by the heuristic. The sentence splitter primarily uses . ! ?, while punctuation density separately affects style; the resulting moderate style and model scores combine into unsure. This is a detected failure to classify the submitted AI-derived text, not evidence that punctuation commands were executed.

**EV09 — signal one, signal two, combining rule, label mapping.** The human-like opening and AI-derived continuation are scored as a single passage. A moderate model score and lower style score combine into unsure. The service cannot localize mixed provenance; this response avoids the AI band without establishing that the entire passage was human-written.

The set contains variants without paired original controls. The scores and
features explain the returned outcome; they do not establish that a particular
typo or edit alone caused a score change.

### Worst attack outcome

EV01 is the accepted AI-derived typo-bearing text closest to the human band.
Its model score is 0.1635, style score 0.601724, and combined score 0.273056:
the dominant predictability signal pulls the result toward human despite the
higher style signal. It receives unsure, not human. Three candidate explanations
considered were model sensitivity to unusual tokens, stylometry treating edits
as human variation, and the wide label mapping; the measured style score and
75% model weight identify the dominant signal/combination as the clearest
explanation. No causal claim about a single edit is made.

Exact staff input and actual response:

```json
{
  "request": {
    "text": "The importance of effective communication in the workplace cannot be overstated. Teams that communicate clearly are better poistioned to achieve their objectives and avoid costly misunderstandings. Three are several strategies organisations can adopt to improve thsi. First, establishing regular check-ins ensures that information flows cosnistently between team members. Second, documenting decisions provides a reefrence point that reduces ambiguity. Finally, encouraging an environment whree questions are welcomed helps surface issues early. Implementing thsee approaches can lead to meaningful improvements in team pefrormance and overall satisfaction.",
    "creator_id": "attacker_EV01"
  },
  "http_status": 200,
  "response": {
    "appeal": {
      "endpoint": "/appeal",
      "method": "POST",
      "required_fields": [
        "content_id",
        "reasoning"
      ]
    },
    "combined_score": 0.27305595535010607,
    "confidence": 0.27305595535010607,
    "content_id": "3d61fadc-6c61-4cd5-9e78-205f4f5ee9e3",
    "creator_id": "attacker_EV01",
    "guess": "unsure",
    "implementation_stage": "two_signals",
    "label": "Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review.",
    "model_score": 0.1635,
    "score_meaning": "Higher scores indicate more AI-associated patterns; this is not an authorship probability.",
    "status": "decided",
    "style_score": 0.6017238214004242,
    "timestamp": "2026-10-29T00:02:38+00:00"
  }
}
```


### Ten actual audit entries

All ten come from this attack run: seven missed evasions, the detected repetitive
evasion, the second-language-writing specimen, and one 429 rejection. Decision
events have all nine required fields; rejections intentionally have no invented
scores. The complete append-only file is [logs/audit.jsonl](logs/audit.jsonl).

```json
[
  {
    "timestamp": "2026-10-29T00:02:38+00:00",
    "content_id": "3d61fadc-6c61-4cd5-9e78-205f4f5ee9e3",
    "creator_id": "attacker_EV01",
    "guess": "unsure",
    "model_score": 0.1635,
    "style_score": 0.6017238214004242,
    "combined_score": 0.27305595535010607,
    "label": "Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review.",
    "status": "decided",
    "implementation_stage": "two_signals"
  },
  {
    "timestamp": "2026-10-29T00:02:38+00:00",
    "content_id": "9b01a94a-1b8b-4b49-bc46-dce71da112f7",
    "creator_id": "attacker_EV02",
    "guess": "unsure",
    "model_score": 0.5943,
    "style_score": 0.2760133404076395,
    "combined_score": 0.5147283351019099,
    "label": "Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review.",
    "status": "decided",
    "implementation_stage": "two_signals"
  },
  {
    "timestamp": "2026-10-29T00:02:38+00:00",
    "content_id": "e0bc784e-14ce-41d5-8d1f-4f528e32a321",
    "creator_id": "attacker_EV03",
    "guess": "unsure",
    "model_score": 0.6662,
    "style_score": 0.46495452839867524,
    "combined_score": 0.6158886320996688,
    "label": "Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review.",
    "status": "decided",
    "implementation_stage": "two_signals"
  },
  {
    "timestamp": "2026-10-29T00:02:38+00:00",
    "content_id": "b23e602f-364f-49e8-a313-c35ff91ec094",
    "creator_id": "attacker_EV04",
    "guess": "unsure",
    "model_score": 0.6114,
    "style_score": 0.5933373739654516,
    "combined_score": 0.6068843434913629,
    "label": "Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review.",
    "status": "decided",
    "implementation_stage": "two_signals"
  },
  {
    "timestamp": "2026-10-29T00:02:38+00:00",
    "content_id": "52187f28-5810-493d-ac0f-e5f048650117",
    "creator_id": "attacker_EV05",
    "guess": "unsure",
    "model_score": 0.3212,
    "style_score": 0.3816699528349812,
    "combined_score": 0.3363174882087453,
    "label": "Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review.",
    "status": "decided",
    "implementation_stage": "two_signals"
  },
  {
    "timestamp": "2026-10-29T00:02:38+00:00",
    "content_id": "dad0db6a-140a-42c7-943c-4a9ae559cca9",
    "creator_id": "attacker_EV06",
    "guess": "unsure",
    "model_score": 0.5727,
    "style_score": 0.22292805100182145,
    "combined_score": 0.48525701275045535,
    "label": "Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review.",
    "status": "decided",
    "implementation_stage": "two_signals"
  },
  {
    "timestamp": "2026-10-29T00:02:39+00:00",
    "content_id": "58e8b448-7534-46a2-bdc2-a34d30ce4168",
    "creator_id": "attacker_EV09",
    "guess": "unsure",
    "model_score": 0.7042,
    "style_score": 0.4558667385626049,
    "combined_score": 0.6421166846406512,
    "label": "Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review.",
    "status": "decided",
    "implementation_stage": "two_signals"
  },
  {
    "timestamp": "2026-10-29T00:02:39+00:00",
    "content_id": "87c0a42c-02f0-474f-9599-08a287e1c3a7",
    "creator_id": "attacker_EV10",
    "guess": "ai",
    "model_score": 0.9792,
    "style_score": 0.7108030704858759,
    "combined_score": 0.912100767621469,
    "label": "Our tools found patterns often associated with AI-generated writing. They can be wrong; this is not proof of how you wrote it. You can explain your process and request a review.",
    "status": "decided",
    "implementation_stage": "two_signals"
  },
  {
    "timestamp": "2026-10-29T00:02:39+00:00",
    "content_id": "cfe056e2-e77d-49e5-b4aa-fb450a8d9bd3",
    "creator_id": "attacker_FP03",
    "guess": "unsure",
    "model_score": 0.8051,
    "style_score": 0.5742326881977692,
    "combined_score": 0.7473831720494424,
    "label": "Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review.",
    "status": "decided",
    "implementation_stage": "two_signals"
  },
  {
    "timestamp": "2026-10-29T00:02:39+00:00",
    "creator_id": "attacker_flood",
    "event": "rejected",
    "status": "rejected",
    "reason": "rate_limited",
    "http_status": 429,
    "route": "/submit",
    "method": "POST",
    "limit": "10 per 1 minute"
  }
]
```


## Run Log and Verdicts

The original [five criteria](criteria.md) are unchanged from Unit 7 commit
`753217e`. Three complete trials use the same committed 20+20 corpus; no text was
replaced after scoring. It contains externally sourced human excerpts, not the
user's writing, plus disclosed Codex-authored counterparts matched by topic and
length. [Provenance and selection](examples/UNIT8_SOURCES.md) explains the six-work
convenience sample, historical-language confound and possible GPT-2 familiarity.

The evaluator invokes the real model 171 times per phase (57 per trial). Its
observer records call hashes while calling the original function unchanged.
Each trial restarts the actual service before appeals and again before reading
their persisted state. Input failures and appeals show no detector calls.
Restarts reset memory-only rate counters; each ordinary test uses a distinct
creator, and the limiter remains enabled. This is explicit test isolation,
not evidence of durable rate counters.

### Before — three trials

[Complete baseline evaluation](results/eval_2026-10-29_000332_612316_before.json)

| Criterion | Original target | Run 1 | Run 2 | Run 3 | Verdict |
|---|---|---|---|---|---|
| 1. Human false positives | ≤1/20 AI accusations | 1/20 flagged ai | 1/20 flagged ai | 1/20 flagged ai | MET |
| 2. Mean score separation | AI mean − human mean ≥0.20 | -0.077545 mean gap | -0.077545 mean gap | -0.077545 mean gap | MISSED |
| 3. Label coverage | 3 real labels + 1001 grid points | 3/3 labels; 1001/1001 grid | 3/3 labels; 1001/1001 grid | 3/3 labels; 1001/1001 grid | MET |
| 4. Persistent appeals | 10/10 persistent, exact, no rescoring | 10/10 persistent exact appeals | 10/10 persistent exact appeals | 10/10 persistent exact appeals | MET |
| 5. Bad input | 13 field/media + 4 byte assertions | 17/17 assertions | 17/17 assertions | 17/17 assertions | MET |


C1 is MET because each trial has exactly one false accusation out of 20, equal
to the allowed maximum—not because the detector is harmless. The accused item,
`human_16`, is a Constitution excerpt about bills and executive objections:
model 0.9112 + style 0.710726 produces 0.861082, crossing the 0.85 AI threshold.
This is the worst writer-facing result across the criterion corpus.

C2 is MISSED: the mean gap is **−0.077545**, far below +0.20 in every trial.
At **signal one**, human passages average 0.629810 versus AI 0.483850 (gap
−0.145960); **signal two** averages 0.493116 versus 0.597165 (gap +0.104049).
The **combining rule** gives 75% weight to the signal whose ordering is reversed
on this corpus. Predictability and familiar formal wording are not authorship.
The convenience sample cannot establish which training examples GPT-2 memorized.

C3 is MET before the change: all three labels occur on real texts, all 1,001
grid scores map correctly, invalid values are rejected, and 0.51 and 0.95 differ.
C4 is MET because all ten exact appeals retain original decisions through real
restarts in every trial; unknown IDs return 404 and no appeal reruns inference.
C5 is MET because all 13 original field/media assertions plus four body-limit
checks return their specified JSON errors without a model call or new decision.
Rejection log events are permitted by the original target.

### Actual JSON from one baseline trial

The following are selected recorded outputs, not hypothetical examples. Full
requests and all three trials are in the linked JSON.

**Criterion 1: `run_eval.py::corpus_metrics`.**

```json
{
  "criterion": 1,
  "passed": true,
  "metric": "1/20 flagged ai",
  "valid_20_human_responses": true,
  "false_positives": 1,
  "actual_response": {
    "method": "POST",
    "route": "/submit",
    "request": {
      "json": {
        "text": "Every Bill which shall have passed the House of Representatives and the Senate, shall, before it become a Law, be presented to the President of the United States; If he approve he shall sign it, but if not he shall return it, with his Objections to that House in which it shall have originated, who shall enter the Objections at large on their Journal, and proceed to reconsider it. If after such Reconsideration two thirds of that house shall agree to pass the Bill, it shall be sent, together with the Objections, to the other House, by which it shall likewise be reconsidered, and if approved by two thirds of that House, it shall become a law. But in all such Cases the Votes of both Houses shall be determined by Yeas and Nays, and the Names of the Persons voting for and against the Bill shall be entered on the Journal of each House respectively. If any Bill shall not be returned by the President within ten Days (Sundays excepted) after it shall have been presented to him, the Same shall be a Law, in like Manner as if he had signed it, unless the Congress by their Adjournment prevent its Return, in which case it shall not be a Law.",
        "creator_id": "eval-000332_612316-before-t1-human-15"
      }
    },
    "request_headers": {
      "Content-Type": "application/json"
    },
    "started_utc": "2026-10-29T00:03:36.414193+00:00",
    "http_status": 200,
    "response_content_type": "application/json",
    "response": {
      "appeal": {
        "endpoint": "/appeal",
        "method": "POST",
        "required_fields": [
          "content_id",
          "reasoning"
        ]
      },
      "combined_score": 0.861081594458242,
      "confidence": 0.861081594458242,
      "content_id": "51faf473-0cfa-4d16-8b61-e096d95468e6",
      "creator_id": "eval-000332_612316-before-t1-human-15",
      "guess": "ai",
      "implementation_stage": "two_signals",
      "label": "Our tools found patterns often associated with AI-generated writing. They can be wrong; this is not proof of how you wrote it. You can explain your process and request a review.",
      "model_score": 0.9112,
      "score_meaning": "Higher scores indicate more AI-associated patterns; this is not an authorship probability.",
      "status": "decided",
      "style_score": 0.7107263778329675,
      "timestamp": "2026-10-29T00:03:36+00:00"
    },
    "elapsed_seconds": 0.085332,
    "specimen_id": "human_16"
  }
}
```


**Criterion 2: `run_eval.py::corpus_metrics`.**

```json
{
  "criterion": 2,
  "passed": false,
  "metric": "-0.077545 mean gap",
  "human_mean": 0.5897239938492017,
  "ai_mean": 0.5121788232901416,
  "mean_gap": -0.07754517055906004,
  "comparison": "Decimal arithmetic on returned scores; no rounding before comparison",
  "human_response_reference": "criterion 1 of this same trial"
}
```


**Criterion 3: `run_eval.py::coverage`.**

```json
{
  "criterion": 3,
  "passed": true,
  "metric": "3/3 labels; 1001/1001 grid",
  "labels_observed": [
    "ai",
    "human",
    "unsure"
  ],
  "thresholds": {
    "human": 0.2,
    "ai": 0.85
  },
  "label_text": {
    "human": "This writing looks more consistent with human writing to our tools. This is an estimate, not proof of authorship. You can request a review if this label seems wrong.",
    "unsure": "Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review.",
    "ai": "Our tools found patterns often associated with AI-generated writing. They can be wrong; this is not proof of how you wrote it. You can explain your process and request a review."
  },
  "grid_failures": [],
  "scores_0_51_and_0_95_differ": true,
  "invalid_scores": [
    {
      "input": "NaN",
      "rejected": true
    },
    {
      "input": "positive infinity",
      "rejected": true
    },
    {
      "input": "negative infinity",
      "rejected": true
    },
    {
      "input": "below zero",
      "rejected": true
    },
    {
      "input": "above one",
      "rejected": true
    }
  ],
  "grid_producer": "run_eval.py::coverage -> scoring.py::score_to_label",
  "actual_response": {
    "method": "POST",
    "route": "/submit",
    "request": {
      "json": {
        "text": "Ineluctable modality of the visible: at least that if no more, thought through my eyes. Signatures of all things I am here to read, seaspawn and seawrack, the nearing tide, that rusty boot. Snotgreen, bluesilver, rust: coloured signs. Limits of the diaphane. But he adds: in bodies. Then he was aware of them bodies before of them coloured. How? By knocking his sconce against them, sure. Go easy. Bald he was and a millionaire, maestro di color che sanno. Limit of the diaphane in. Why in? Diaphane, adiaphane.\n\nIf you can put your five fingers through it it is a gate, if not a door. Shut your eyes and see.",
        "creator_id": "eval-000332_612316-before-t1-coverage-2"
      }
    },
    "request_headers": {
      "Content-Type": "application/json"
    },
    "started_utc": "2026-10-29T00:03:37.929174+00:00",
    "http_status": 200,
    "response_content_type": "application/json",
    "response": {
      "appeal": {
        "endpoint": "/appeal",
        "method": "POST",
        "required_fields": [
          "content_id",
          "reasoning"
        ]
      },
      "combined_score": 0.17341056920266548,
      "confidence": 0.17341056920266548,
      "content_id": "aa1af41e-6b60-4a67-8379-3960536a3447",
      "creator_id": "eval-000332_612316-before-t1-coverage-2",
      "guess": "human",
      "implementation_stage": "two_signals",
      "label": "This writing looks more consistent with human writing to our tools. This is an estimate, not proof of authorship. You can request a review if this label seems wrong.",
      "model_score": 0.1261,
      "score_meaning": "Higher scores indicate more AI-associated patterns; this is not an authorship probability.",
      "status": "decided",
      "style_score": 0.31534227681066196,
      "timestamp": "2026-10-29T00:03:37+00:00"
    },
    "elapsed_seconds": 0.055861,
    "specimen_id": "human_literary"
  }
}
```


**Criterion 4: `run_eval.py::Runner.appeals`.**

```json
{
  "criterion": 4,
  "passed": true,
  "metric": "10/10 persistent exact appeals",
  "successful_appeals": 10,
  "restart_before_appeals": true,
  "restart_after_appeals": true,
  "model_calls_before": 57,
  "model_calls_after": 57,
  "no_rescoring_observed": true,
  "unknown_no_appeal": true,
  "health_before_appeals": {
    "method": "GET",
    "route": "/health",
    "request": null,
    "request_headers": {},
    "started_utc": "2026-10-29T00:03:38.902308+00:00",
    "http_status": 200,
    "response_content_type": "application/json",
    "response": {
      "detector_loaded": false,
      "detector_model": "gpt2",
      "log_entries": 146,
      "ok": true,
      "rate_limiting": true
    },
    "elapsed_seconds": 0.002003
  },
  "actual_appeal_response": {
    "method": "POST",
    "route": "/appeal",
    "request": {
      "json": {
        "content_id": "d1c38f2f-7625-4e7c-9195-8c8de3b1c360",
        "reasoning": "  Synthetic evaluation appeal 1/1: please review the process notes.\nThis is a test, not a claim of human authorship.  "
      }
    },
    "request_headers": {
      "Content-Type": "application/json"
    },
    "started_utc": "2026-10-29T00:03:38.904368+00:00",
    "http_status": 200,
    "response_content_type": "application/json",
    "response": {
      "content_id": "d1c38f2f-7625-4e7c-9195-8c8de3b1c360",
      "message": "Your explanation has been recorded and this item is under review. The original estimate remains in the history; no new assessment was made.",
      "reasoning": "  Synthetic evaluation appeal 1/1: please review the process notes.\nThis is a test, not a claim of human authorship.  ",
      "status": "under_review"
    },
    "elapsed_seconds": 0.001852
  },
  "actual_read_after_restart": {
    "method": "GET",
    "route": "/content/d1c38f2f-7625-4e7c-9195-8c8de3b1c360",
    "request": null,
    "request_headers": {},
    "started_utc": "2026-10-29T00:03:39.136308+00:00",
    "http_status": 200,
    "response_content_type": "application/json",
    "response": {
      "appeals": [
        {
          "content_id": "d1c38f2f-7625-4e7c-9195-8c8de3b1c360",
          "creator_id": "eval-000332_612316-before-t1-appeal-0",
          "event": "appeal",
          "reasoning": "  Synthetic evaluation appeal 1/1: please review the process notes.\nThis is a test, not a claim of human authorship.  ",
          "status": "under_review",
          "timestamp": "2026-10-29T00:03:38+00:00"
        }
      ],
      "combined_score": 0.5589396836421172,
      "confidence": 0.5589396836421172,
      "content_id": "d1c38f2f-7625-4e7c-9195-8c8de3b1c360",
      "creator_id": "eval-000332_612316-before-t1-appeal-0",
      "guess": "unsure",
      "implementation_stage": "two_signals",
      "label": "Our tools cannot confidently tell how this writing was produced. This label is not an accusation. You can add context and request a review.",
      "model_score": 0.5855,
      "status": "under_review",
      "style_score": 0.479258734568469,
      "timestamp": "2026-10-29T00:03:38+00:00"
    },
    "elapsed_seconds": 0.002015
  }
}
```


**Criterion 5: `run_eval.py::Runner.bad_inputs`.**

```json
{
  "criterion": 5,
  "passed": true,
  "metric": "17/17 assertions",
  "actual_case": {
    "method": "POST",
    "route": "/submit",
    "request": {
      "raw_utf8": "hello"
    },
    "request_headers": {
      "Content-Type": "text/plain"
    },
    "started_utc": "2026-10-29T00:03:39.158132+00:00",
    "http_status": 415,
    "response_content_type": "application/json",
    "response": {
      "error": "json_required",
      "message": "Send application/json."
    },
    "elapsed_seconds": 0.001145,
    "case": "non_json",
    "expected_status": 415,
    "audit_events_added": [
      {
        "creator_id": "unknown",
        "event": "rejected",
        "http_status": 415,
        "method": "POST",
        "reason": "json_required",
        "route": "/submit",
        "status": "rejected",
        "timestamp": "2026-10-29T00:03:39+00:00"
      }
    ],
    "no_successful_event": true,
    "model_calls_before": 57,
    "model_calls_after": 57,
    "no_inference_observed": true,
    "passed": true
  }
}
```


## The Improvement

The diagnosis selects **one reweighting change**: model/style weights from
**0.75/0.25 to 0.50/0.50** in `config.py`. The detector, stylometry, disagreement
guard, thresholds, labels, validation, rate policy and criterion targets stay
fixed. Equal weights reduce the influence of the signal that reverses the
human/AI ordering in the baseline corpus. This is a diagnostic experiment on
the same data, not an independently validated new detector.

Before rerunning, the expected trade is explicit: `human_16` should drop below
the AI threshold, but EV10 may lose its AI label and Joyce may lose the only
human label in the calibration set. The original criterion will be marked
MISSED if label coverage is lost. No threshold adjustment will conceal that
regression.

The before evidence is complete and committed before this change. After measurements are pending.
