# Acceptance criteria — Provenance Guard

These five criteria are authored with Codex AI assistance for the instructor
example, before implementation or any detector results. They are not represented
as unaided student work. Unit 7 implements and checks the service; Unit 8 evaluates
these same targets in three complete trials. A criterion is MET only if its
whole target holds in every trial, not just on average. Keep this original text;
record any later clarification underneath with a reason.

## 1. False positives: at most 1 of 20 known-human excerpts

In each trial, at most **1/20 (5%)** of a fixed set of 20 independently sourced,
known-human English excerpts may receive `guess="ai"`. At least ten must be
plain or conventional prose and at least five formal prose. Each is 80–220
words. Record author, work, source URL and provenance; freeze the set before its
first evaluation and use the same set in all three trials. Unsure is not a false
accusation. AI-generated imitations do not count as human evidence.

**Why this target:** a writing site's incorrect accusation can damage the
writer's trust. A five-percent maximum is demanding while acknowledging a small
sample; passing would not establish a population false-positive rate or justify
punishment without human review.

## 2. Score separation: at least a 0.20 mean gap

In every trial, the mean combined AI-oriented score of **20 recorded AI-generated
English excerpts minus the mean score of the 20 human excerpts in criterion 1
must be at least 0.20**. Match the 80–220-word length range and broad topics;
record the AI prompt/model/source and freeze both sets before evaluation. Do
not drop surprising examples or reclassify provenance using detector output.

**Why this target:** always answering unsure would avoid accusations but supply
little useful distinction. A 0.20 gap requires a meaningful continuous signal,
while the separate false-positive limit prevents a high mean from hiding harm
to individual human writers. This does not claim calibrated probabilities.

## 3. Label coverage: all 3 labels and all 1,001 score points

In each trial, actual text submissions through both real signals must produce
**at least one `human`, one `unsure`, and one `ai`** response; retain the texts,
sources and responses. Separately, **all 1,001 scores from 0 through 1 in steps
of 0.001** must map to exactly one documented label, including both boundary
values. Scores **0.51 and 0.95 must map to different labels**. Invalid scores
(NaN, infinity or outside 0–1) must be rejected. Stubbed/model-mocked responses
may test plumbing but cannot establish text-to-label reachability.

**Why this target:** a three-label contract is misleading if one label is only
present in documentation. The continuous score sweep checks boundaries; the
real submissions distinguish mathematical coverage from end-to-end reachability.

## 4. Appeals: 10 of 10 recorded and persistent

For **10 distinct existing submissions per trial**, a valid appeal must return
HTTP 200 and `status="under_review"`, preserve its exact nonempty reasoning,
append an appeal beside the unchanged original decision, and be returned as
under review by a fresh reader of the audit file. **10/10** must still resolve
that way after the service restarts. Appealing an unknown content ID must return
HTTP 404 and create no appeal. No appeal may call the detector again or silently
reverse the original guess.

**Why this target:** a writer needs a durable way to challenge an error, not an
acknowledgment that disappears with the process. Repeated append-only events keep
the decision and its challenge inspectable; an appeal is not automatic exoneration.

## 5. Bad input: all 12 cases fail safely

In each trial, all **12** cases below must return a JSON error with the specified
status, create no decision or appeal, and perform no model inference:

| Case | Expected HTTP status |
|---|---:|
| `/submit` with non-JSON Content-Type | 415 |
| `/submit` with malformed JSON and JSON Content-Type | 400 |
| `/submit` with a JSON array instead of an object | 400 |
| Missing `text` | 400 |
| Numeric `text` | 400 |
| Whitespace-only `text` | 400 |
| Text with fewer than 20 words | 400 |
| Text longer than 10,000 characters | 413 |
| Missing `creator_id` | 400 |
| Non-string `creator_id` | 400 |
| Blank or longer-than-100-character `creator_id` (test both) | 400 |
| `/appeal` with a known content ID but blank reasoning | 400 |

Also reject any request body exceeding **64 KiB** with JSON HTTP 413 before
parsing or model inference. A rejection event may be logged, but never masquerade
as a successful content decision. Treat each variant in the last creator row as
an additional assertion, not a reason to skip either.

**Why this target:** malformed requests should not become 500s, expensive model
work or phantom submissions. Explicit word, character and byte limits make the
contract reproducible and bound the local service's work.
