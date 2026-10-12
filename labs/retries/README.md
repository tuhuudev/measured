# Lab: retries, backoff and jitter

- **What:** `retry_lab.py` starts a real asyncio TCP server in its own process on localhost. The server handles at most 20 requests at once (20 ms each) and answers "busy" immediately when full, like an HTTP 503. 200 clients send one request at the same moment and retry on "busy", at most 10 attempts each, with one of three policies:
  - **immediate:** retry at once;
  - **backoff:** capped exponential backoff, wait `min(1000 ms, 10 ms × 2^n)` after the n-th failure;
  - **jitter:** full jitter, wait `random(0, min(1000 ms, 10 ms × 2^n))`.
- Each policy runs 7 trials (random seeds 0–6). The lab records every request's arrival time at the server, how many clients gave up, and when the median and last client succeeded.
- **Real or synthetic:** the traffic pattern is synthetic (one burst); every count and time is a real measurement of this script.
- **Run:** `python labs/retries/retry_lab.py` → writes `results.json` (standard library only, a couple of minutes).

## Recorded run (2026-10-12, `results.json`)
Machine: AMD64 Family 23 Model 96 laptop, Windows 11, Python 3.12.10. Medians over 7 trials.

| Policy | Requests (min–max) | Clients that gave up | Median client | Last client |
|---|---|---|---|---|
| immediate | 1,512 (1,460–1,585) | 120 (max 120) | 41.2 ms | 74.5 ms |
| backoff | 1,063 (940–1,181) | 0 (max 5) | 189.4 ms | 3,307 ms |
| jitter | 901 (838–948) | 0 (max 0) | 95.1 ms | 459 ms |

Ideal with perfect scheduling: 200 / 20 × 20 ms = 200 ms. Three full runs that day (the other two are in [`runs/`](runs), same format) gave run medians for the last client of 2,379–3,330 ms (backoff) and 459–535 ms (jitter), and 100–120 clients giving up with immediate retries.

## Notes
- **Windows timer:** `asyncio.sleep` is rounded up to the ~15.6 ms timer tick by default (20 ms → ~32.6 ms). The lab calls `timeBeginPeriod(1)` for a 1 ms timer (20 ms → ~20.6 ms). An earlier version without it gave distorted waits and was discarded.
- **One client event loop:** all 200 clients share one Python event loop, which sends in batches a few ms apart. The noise affects every policy (it bunches jittered retries a little and breaks up some of backoff's waves); its net effect isn't measured. Timelines are bucketed at 50 ms.
- **Median client** is computed over clients that succeeded; with immediate retries most clients gave up.

The claims and their primary sources are in [`facts.md`](facts.md).
