# Lab: queues and load

- **What:** `queue_lab.py` starts a real TCP server in its own process on localhost. It serves one request at a time, first come first served. Each request says how long it takes; the server busy-waits exactly that long (so service times are precise, not rounded to the OS timer) and replies.
- A client sends 3,000 requests at random (Poisson) times at a target load of 10%, 30%, 50%, 70%, 80%, 90% and 95%, and measures each request's time from send to reply. The first 300 at each load are dropped as warm-up.
- Two kinds of service time, both with a 10 ms mean: **exponential** (random, like a mix of fast and slow requests) and **constant** (every request takes 10 ms).
- Server and client each busy-poll a non-blocking socket on their own CPU core at high priority, with Python's garbage collector off, and the lab records how late each send was and how long the server overran each service time.
- For each load it also computes:
  - **textbook** mean time in system at the target load: M/M/1 `S / (1 − ρ)`, M/D/1 `S + ρS / (2(1 − ρ))`;
  - **Pollaczek–Khinchine** mean with the *measured* arrival rate and *measured* service times (overhead included);
  - **replay**: an ideal FIFO server with no overhead, fed the same send times and the same service times. The gap between the real server and the replay is the real server's own cost; the gap between the replay and the textbook is chance.
  - **mean number in the server**, time-averaged, and λ × W from the same requests (Little's law).
- **Real or synthetic:** the traffic is synthetic; every time is a real measurement of this script.
- **Run:** `python labs/queueing/queue_lab.py [seed]` → writes `results.json` (standard library only, about 20 minutes, dominated by the 10% load: 3,000 requests 100 ms apart). Don't run other heavy work on the machine meanwhile (see seed 1 below).

## Recorded run (2026-10-13, seed 2, `results.json`)
Machine: AMD Ryzen 3 PRO 4350G (4 cores, 8 threads), Windows 11, Python 3.12.10, Balanced power plan. Server on logical CPU 2, client on CPU 4.

Exponential service (M/M/1), 10 ms mean:

| Target load | Measured utilisation | Mean | p50 | p99 | Textbook mean | Mean in server |
|---|---|---|---|---|---|---|
| 10% | 9.7% | 10.8 ms | 7.7 ms | 49.4 ms | 11.1 ms | 0.11 |
| 30% | 29.9% | 14.2 ms | 9.8 ms | 64.8 ms | 14.3 ms | 0.42 |
| 50% | 50.8% | 21.6 ms | 14.4 ms | 109 ms | 20.0 ms | 1.12 |
| 70% | 70.6% | 33.4 ms | 23.2 ms | 160 ms | 33.3 ms | 2.31 |
| 80% | 82.5% | 50.2 ms | 38.7 ms | 210 ms | 50.0 ms | 4.08 |
| 90% | 91.1% | 127 ms | 78.2 ms | 554 ms | 100 ms | 12.0 |
| 95% | 98.6% | 196 ms | 171 ms | 553 ms | 200 ms | 18.6 |

Constant service (M/D/1), 10 ms:

| Target load | Measured utilisation | Mean | p50 | p99 | Textbook mean |
|---|---|---|---|---|---|
| 10% | 10.2% | 10.7 ms | 10.1 ms | 20.0 ms | 10.6 ms |
| 30% | 30.1% | 12.3 ms | 10.1 ms | 30.9 ms | 12.1 ms |
| 50% | 49.4% | 14.8 ms | 10.2 ms | 44.5 ms | 15.0 ms |
| 70% | 70.1% | 21.2 ms | 17.2 ms | 62.1 ms | 21.7 ms |
| 80% | 81.5% | 34.9 ms | 25.9 ms | 129 ms | 30.0 ms |
| 90% | 90.7% | 54.9 ms | 44.1 ms | 209 ms | 55.0 ms |
| 95% | 94.0% | 94.9 ms | 69.3 ms | 307 ms | 105 ms |

Times are measured by the client, send to reply. "Measured utilisation" is the server's busy time divided by the elapsed time of that load step; it differs from the target because arrivals and service times are random and 3,000 requests is a short window.

- **Real server vs ideal replay:** the client-measured mean was 0.9–2.2% above the replay up to 80% load, 2.8–5.4% at 90% and 4.3–12.1% at 95% (seeds 2 and 3); p99 within 0.3–9.3%.
- **Server overhead:** the server overran the requested service time by at most 0.12 ms at p99 (about 1% of 10 ms). Client sends were at most 0.24 ms late (seeds 2 and 3).
- **Little's law:** the time-averaged number of requests in the server equalled λ × W to the third decimal at every load (e.g. 12.038 and 12.038 at 90%, exponential), as it must over a run that starts and ends empty.

## Other runs
- [`runs/seed3.json`](runs/seed3.json): same picture. Exponential at 90%: mean 131 ms, p99 568 ms; at 95% (measured utilisation 97.7%): mean 501 ms. Constant at 90%: 49.6 ms mean.
- [`runs/seed1-disturbed.json`](runs/seed1-disturbed.json): **not used.** While it ran, other work on the same laptop (a Node script, PDF reading) stalled the client for up to 96 ms at a time; its sends were late and bunched, and its p99 at low loads is inflated (constant service at 50%: 78 ms vs a 43 ms replay). Kept for transparency.
- Earlier versions with a 1 ms service time were discarded: about 40–80 µs of per-request overhead (4–8% of 1 ms) pushed a 90% target to 93–94% real utilisation, and occasional 5–10 ms OS stalls dominated. 10 ms makes both small.

## Notes
- High-load results from 3,000 requests vary a lot from run to run, because waiting times near full load are strongly correlated. The in-page simulation shows how much: windows of 3,000 requests at 90% load gave means from 56 to 438 ms around a 100 ms average.
- Busy-waiting uses a whole core on each side; this is a lab setup, not how a server should wait.
- Times include the localhost round trip and Python overhead (about 0.1 ms).

The claims and their primary sources are in [`facts.md`](facts.md).
