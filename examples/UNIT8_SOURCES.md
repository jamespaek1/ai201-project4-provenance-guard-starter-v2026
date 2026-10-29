# Unit 8 criterion corpus: provenance and selection

[unit8_corpus.json](unit8_corpus.json) contains the fixed **20 human + 20
AI-generated** specimens for the original acceptance criteria 1 and 2. It was
selected on **2026-10-28 before any scores from this corpus were generated or inspected**.
Commit the corpus before its first evaluation and retain exactly these texts
for every before/after trial. This is the project's own criterion corpus, not
staff's independent attack set and not an estimate of population accuracy.

None of these texts was written by the user. The human side contains attributed
historical excerpts; the AI side was composed by Codex for this instructor
example. No student-authored writing or independent human review is claimed.

## Fixed human selection rule

Six sources and their body-start anchors were chosen before scoring. For each
source, split the text after that anchor on blank lines, collapse whitespace
within each paragraph to one space, and select the **first N complete paragraphs
containing 80–220 words** under `stylometry.words`. Do not skip an eligible
paragraph because of its wording or presumed score. The rule selects three
paragraphs from each of the first four works and four from each of the last two.

This yields **12 plain or conventional** passages and **8 formal** passages.
“Conventional” includes memoir, travel narrative and straightforward fictional
narration; it does not mean contemporary informal English. Historical legal
provisions and political arguments constitute the formal group. No source is
used in the seven Unit 7 calibration fixtures.

| Human IDs | Author and work | Original date | Group | Body anchor | Count |
|---|---|---|---|---|---:|
| 01–03 | Benjamin Franklin, *The Autobiography of Benjamin Franklin* | Composed 1771–1790; this edition 1909 | Conventional memoir | `Dear Son:` | 3 |
| 04–06 | Charles Darwin, *The Voyage of the Beagle* | 1839 | Conventional travel narrative | `After having been twice driven back` | 3 |
| 07–09 | Anna Sewell, *Black Beauty* | 1877 | Plain narrative/dialogue | `The first place that I can well remember` | 3 |
| 10–12 | Daniel Defoe, *The Life and Adventures of Robinson Crusoe* | 1719 | Conventional fictional narrative | `I was born in the year 1632` | 3 |
| 13–16 | United States Constitutional Convention, *The United States Constitution* | 1787 | Formal legal prose | `We the People` | 4 |
| 17–20 | Thomas Paine, *Common Sense* | 1776 | Formal political argument | `Some writers have so confounded` | 4 |

The source catalogs and full transcriptions were checked on 2026-10-28. Each
catalog identifies the work and marks it public domain in the USA. The corpus
quotes the historical texts, not the catalogs' modern summaries.

- Franklin: [catalog and author record](https://www.gutenberg.org/ebooks/148),
  [source transcription](https://www.gutenberg.org/cache/epub/148/pg148.txt).
- Darwin: [catalog and author record](https://www.gutenberg.org/ebooks/944),
  [source transcription](https://www.gutenberg.org/cache/epub/944/pg944.txt).
- Sewell: [catalog and author record](https://www.gutenberg.org/ebooks/271),
  [source transcription](https://www.gutenberg.org/cache/epub/271/pg271.txt).
- Defoe: [catalog and author record](https://www.gutenberg.org/ebooks/521),
  [source transcription](https://www.gutenberg.org/cache/epub/521/pg521.txt).
- United States Constitution: [catalog and attribution](https://www.gutenberg.org/ebooks/5),
  [source transcription](https://www.gutenberg.org/cache/epub/5/pg5.txt).
- Paine: [catalog and author record](https://www.gutenberg.org/ebooks/147),
  [source transcription](https://www.gutenberg.org/cache/epub/147/pg147.txt).

Project Gutenberg's [reuse terms](https://www.gutenberg.org/policy/license.html)
remain available with the source editions. Only whitespace is normalized here:
spelling, punctuation, capitalization, historical wording and inline footnote
markers are preserved. The JSON records the source-file SHA-256, anchor,
zero-based paragraph index after that anchor, qualifying-paragraph rank,
word count, and exact excerpt SHA-256. These fields allow selection to be
checked even if a source transcription changes later.

## AI composition and matching

Codex composed one original paragraph for each matched broad topic. The record
for every AI specimen includes its exact composition instruction in `prompt`,
the corresponding human ID, date, source, word count and SHA-256. These are
instructions followed while drafting in this task, not a claim that an external
chat/API was invoked or that a separate provider transcript exists. The model
record is **“Codex, model identifier not exposed.”** No more specific model name
is invented.

The instructions ask for the same broad topic and prose register, approximately
the paired source's length, without quotation, named-author imitation, or
optimization for a detector. Narratives are fictional; government passages are
hypothetical explanations or charter-style examples, not current legal advice.
No detector or style signal was called during composition or selection. Only
word-count, provenance, uniqueness and file-integrity checks were performed.
Every AI paragraph is within **10%** of its paired human passage's word count.

| Pair | Broad topic | Human words | AI words |
|---|---|---:|---:|
| 01 | Preserving family history | 177 | 174 |
| 02 | Memoir and past choices | 124 | 125 |
| 03 | Autobiography and vanity | 180 | 174 |
| 04 | Coastal surveying voyage | 172 | 168 |
| 05 | Visiting an old town | 163 | 160 |
| 06 | A traveler's meal and church visit | 115 | 114 |
| 07 | Meadow and pond | 91 | 93 |
| 08 | Manners and care around horses | 127 | 127 |
| 09 | Daily care for working horses | 139 | 137 |
| 10 | Family origins and surname | 105 | 106 |
| 11 | Travel against family advice | 122 | 125 |
| 12 | A parent's emotional warning | 89 | 89 |
| 13 | Population-based representation | 166 | 164 |
| 14 | Staggered legislative terms | 113 | 113 |
| 15 | Legislative compensation and debate | 82 | 82 |
| 16 | Bills and executive objections | 212 | 201 |
| 17 | Government's purpose and costs | 194 | 189 |
| 18 | Community cooperation | 217 | 208 |
| 19 | Why communities need rules | 105 | 107 |
| 20 | Institutional simplicity | 113 | 110 |

All 40 texts have distinct SHA-256 hashes. Each is in the specified 80–220-word
range using the service's tokenizer. Exact human text is extracted from the
recorded source, rather than reconstructed or paraphrased by AI.

## What this corpus can and cannot establish

“Independently sourced” here means the human texts were obtained from external,
attributed human works rather than generated as supposed human examples. There
are **20 distinct excerpts from six works**, not 20 statistically independent
authors. The repeated authors and genres reduce the breadth of the test. These
are a transparent convenience sample selected by a fixed positional rule, not a
random sample of real users' submissions.

Older English, genre, editorial punctuation and the contrast with contemporary
AI prose are possible confounders even with topic and length matching. Public
Gutenberg texts may also be familiar to GPT-2 through its training data, so they
are not a guaranteed training-disjoint holdout. An observed mean gap would not
prove the model detects authorship, and a low false-positive count would not
establish a population false-positive rate. Preserve surprising results and
report these limits instead of replacing specimens after seeing scores.
