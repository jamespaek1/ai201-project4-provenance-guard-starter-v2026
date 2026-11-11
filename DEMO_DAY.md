# Unit 10 Demo Day · Provenance Guard

Three-minute presenter notes for the AI-assisted instructor example. Open the [acceptance criteria](criteria.md), [baseline run log](results/unit9/before/summary.json), and [final run log](results/unit9/after/summary.json) before presenting. Give your partner the [run instructions](RUNNING.md) for the independent test.

## 1. What I built · 0:00–0:45

*Show the running service. From the repository root, paste this in a second terminal and point to the returned `guess`, `content_id`, and `appeal` fields. If the service needs starting, follow the one-time setup in RUNNING.md and run `./start.sh`.*

```sh
curl -sS http://127.0.0.1:5057/submit \
  -H 'Content-Type: application/json' \
  -d '{"creator_id":"demo-day","text":"Our neighborhood volunteers will meet beside the library on Saturday morning. We plan to sort donated books, repair a few torn covers, and prepare boxes for the community center. Please bring comfortable shoes and a reusable water bottle. New volunteers can join an experienced partner before choosing a task."}' \
  | .venv/bin/python -m json.tool
```

“Imagine you’re the writer of this library announcement. Provenance Guard looks at how predictable the wording is to GPT-2 and how the sentences vary. Here’s what the writer sees when I send the passage. The estimate is ‘unsure.’ The response gives the writer an ID and a way to request a review. My capstone focused on the experience of using this service. How long does the first writer wait, and if it’s slow, can we tell where the time went?”

## 2. What standard I set · 0:45–1:15

*Read the two targets from criteria 1 and 4.*

“With the model files already downloaded, each fresh service process had 60 seconds to answer its health check. Once it said it was ready, every one of ten fixed submissions had to return HTTP 200 within two seconds, as measured by the client. That included the very first submission. I used the same ten passages in three trials. One slow request in any trial meant the latency criterion failed.”

## 3. What the test found · 1:15–2:15

*Show the baseline trial 1 entry. Point out the health response, then the first submission’s model-stage timing.* [Baseline trial 1](results/unit9/before/trial-1/report.json)

“In the first trial the health check answered in 0.36 seconds. From the writer’s side, that looked ready. But the first paragraph took 6.27 seconds to come back. The request log let me follow that one paragraph through the system. The model stage accounted for 6.271 of the 6.273 seconds. Writing the audit entry took less than a millisecond. The health response had another clue. It said the detector was still unloaded. The first writer’s request had triggered model loading. The other 29 submissions met the target. Even in that first trial, the average was only 0.66 seconds. If I had reported just that number, you would never have seen the wait the first writer experienced.”

## 4. What I changed · 2:15–3:00

*Open the final run log and point to the maximum request time for each trial.* [Final trials](results/unit9/after/summary.json)

“I moved model loading into worker startup so that a successful health check now means the model has loaded. Startup took between 1.53 and 2.63 seconds in the final trials. All 30 submissions then met the two-second target, and the same passages got the same scores and labels. The slowest response still took 1.929 seconds. That leaves only 71 milliseconds of margin on this laptop. The test covered short passages arriving one at a time. How long a writer waits behind another writer is still an open question.”

## Peer exchange

1. Swap run instructions. Give your partner [RUNNING.md](RUNNING.md) and receive their startup instructions. Each tester starts the other system independently. If five minutes pass, record the exact command, visible output, and where you stopped.
2. If it starts, spend about four minutes using it. Try the ordinary task first, then an unusual input of your choice. Record what you entered and what the system returned.
3. Take two minutes each to share three observations. Use the sheet below twice, once for the system you tested and once for your partner’s observations about Provenance Guard. When listening, write down their words and ask one clarifying question, such as “What did you expect to happen at that step?”

| Observation | Partner’s system | Provenance Guard |
|---|---|---|
| Started in ___ minutes, or stopped at this command and output | | |
| One thing that worked · input and observed result | | |
| One thing that surprised me · expectation and actual result | | |
| One thing I couldn’t figure out · exact step | | |
| Follow-up question and answer | | |

## Presenter’s rehearsal check · November 11, 2026

On the prepared local installation, `./start.sh` served the API on port 5057. The health check returned HTTP 200 with `ok=true` and `detector_loaded=true`. The live command above returned HTTP 200, `guess="unsure"`, and a combined score of 0.4142. Server handling took 1.230 seconds. A second request with an empty text field returned HTTP 400, `invalid_text`, and the message “text must be a nonempty string.” Its logged model-stage duration was zero.

The timing targets in the talk use the client measurements from Unit 9. The November 11 check exercised the demo commands on the presenter’s machine. The feedback table is for observations made during the in-class exchange. [CodePath Demo Day instructions](https://courses.codepath.org/courses/ai201/unit/10#!projects)
