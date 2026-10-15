# Lab: cache stampede

- **What:** `stampede_lab.py` starts a real "database" in its own process on localhost. It recomputes one hot value; each recompute busy-waits exactly 100 ms, one at a time, first come first served (so recomputes that arrive together queue, as in the [queueing lab](../queueing)).
- An app reads that value through an in-process cache at random (Poisson) times, 10, 100 or 1,000 reads per second (1, 10 and 100 reads per recompute time). The cache starts warm. Two TTLs: **2 s** (60 s per cell, about 30 expiries) and **10 s** (120 s per cell, about 12 expiries).
- Three ways to refresh:
  - **plain TTL:** every read that finds the value expired sends its own recompute and waits for it.
  - **lock (single-flight):** only the first such read recomputes; the others wait for that one result.
  - **XFetch, β = 1:** Fig. 3 of Vattani et al. (2015): a read recomputes (and waits for it) if `now − Δ·β·ln(rand) ≥ expiry`, where Δ is the last measured recompute time, stored with the value. Other reads keep getting the cached value.
- **Stampede size** is the paper's definition: the number of recomputes started within one recompute time (100 ms) of the first one.
- **Runaway cutoff:** if more than 1,000 recomputes are waiting at the database, the cell stops (`runaway_at_s`), the database drops its queue, and the reads waiting on those recomputes are counted as `unserved_reads`. Without it, one cell of an earlier version ran for 2,300 s instead of 60.
- Both processes busy-poll a non-blocking socket on their own CPU core at high priority, with Python's garbage collector off. The app is one thread; each read is a small state machine in its polling loop.
- **Real or synthetic:** the traffic and the "database" work are synthetic; every time is a real measurement of this script.
- **Run:** `python labs/stampede/stampede_lab.py [seed]` → writes `results.json` (standard library only, about 30 minutes). `python labs/stampede/stampede_lab.py <seed> <seconds>` is a smoke test that writes nothing. Don't run other heavy work on the machine meanwhile.

## Recorded run (2026-10-15, seed 2, `results.json`)
Machine: AMD Ryzen 3 PRO 4350G (4 cores, 8 threads), Windows 11, Python 3.12.10, Balanced power plan. Database on logical CPU 2, app on CPU 4.

TTL 2 s, 60 s per cell:

| Strategy | Reads/s | Recomputes | Stampede mean (max) | Reads that waited | p99 read | p99.9 read | Slowest read | Database busy |
|---|---|---|---|---|---|---|---|---|
| plain | 10 | 45 | 1.73 (4) | 7.2% | 205 ms | 334 ms | 334 ms | 7.7% |
| plain | 100 | 213 | 11.2 (15) | 3.6% | 830 ms | 1,305 ms | 1,409 ms | 35.7% |
| plain | 1,000 | 492 | 98.4 (112) | 0.82% | 0.004 ms | 8,630 ms | 11,115 ms | 82.3% |
| lock | 10 | 27 | 1 (1) | 9.9% | 100 ms | 106 ms | 106 ms | 4.7% |
| lock | 100 | 28 | 1 (1) | 5.4% | 85.0 ms | 100 ms | 101 ms | 4.8% |
| lock | 1,000 | 28 | 1 (1) | 4.8% | 81.0 ms | 99.9 ms | 100 ms | 4.8% |
| XFetch | 10 | 52 | 1.68 (5) | 9.2% | 259 ms | 415 ms | 415 ms | 8.9% |
| XFetch | 100 | 66 | 1.83 (7) | 1.1% | 100 ms | 304 ms | 603 ms | 11.2% |
| XFetch | 1,000 | **runaway at 36.6 s:** 1,093 | 17.3 (102) | 0.26% | 0.015 ms | 573 ms | 3,056 ms | 25.7% |

TTL 10 s, 120 s per cell:

| Strategy | Reads/s | Recomputes | Stampede mean (max) | Reads that waited | p99 read | p99.9 read | Slowest read | Database busy |
|---|---|---|---|---|---|---|---|---|
| plain | 10 | 25 | 2.27 (3) | 2.1% | 177 ms | 254 ms | 284 ms | 2.2% |
| plain | 100 | 115 | 11.5 (18) | 0.95% | 0.033 ms | 1,221 ms | 1,710 ms | 9.7% |
| plain | 1,000 | 594 | 84.9 (117) | 0.50% | 0.002 ms | 7,844 ms | 11,712 ms | 49.6% |
| lock | 10 | 11 | 1 (1) | 2.1% | 74.1 ms | 100 ms | 100 ms | 1.0% |
| lock | 100 | 11 | 1 (1) | 0.95% | 0.009 ms | 96.3 ms | 100 ms | 1.0% |
| lock | 1,000 | 11 | 1 (1) | 0.90% | 0.003 ms | 89.1 ms | 100 ms | 1.0% |
| XFetch | 10 | 23 | 1.92 (5) | 1.9% | 100 ms | 385 ms | 441 ms | 2.0% |
| XFetch | 100 | 28 | 2.33 (8) | 0.23% | 0.013 ms | 169 ms | 702 ms | 2.4% |
| XFetch | 1,000 | 24 | 1.85 (7) | 0.02% | 0.011 ms | 0.016 ms | 603 ms | 2.1% |

Read times are measured by the app from when it handled the read to when it had the value. A cache hit takes a few microseconds; a read that waited takes at least one recompute.

- **Plain TTL at 1,000 reads/s:** about 100 reads see the value expired before the first recompute returns, and each sends its own recompute. The database serves them one after another, so the last of them waits about 11 s. Fewer than 1% of reads wait, so p50 (0.0006 ms) and p99 (0.004 ms) show a cache hit while p99.9 is 8.6 s. With a 10 s TTL the slowest read waited 11.7 s.
- **Lock:** exactly one recompute per expiry at every rate. Every read that arrives during that recompute waits for it: 4.8% of reads at 1,000/s with TTL 2 s, median wait 52 ms, never more than one recompute.
- **XFetch, TTL 10 s:** stampedes of 1.85–2.33 on average at every rate (the paper's bound for β = 1 is e − 1/e ≈ 2.35 for large n), and the reads that waited are mostly the recomputing reads themselves (24 of 120,137 at 1,000/s). After overlaps Δ reached 603 ms (seed 2) and 708 ms (seed 1), then came back to 100 ms.
- **XFetch, TTL 2 s, 1,000 reads/s: runaway.** Δ is measured around the recompute, so it includes time spent queueing at the database. When two or three recomputes overlap, the next Δ is 200–400 ms instead of 100. A larger Δ makes the next refresh start earlier and gives more reads a chance to trigger, so more recomputes overlap, so Δ grows again. Once Δ·ln(n·Δ) is larger than the TTL (n = reads per ms; at 1,000 reads/s that is Δ ≈ 343 ms for a 2 s TTL, 1,383 ms for 10 s), reads trigger recomputes as soon as the value is written. Recorded `stampede_delta_ms`: seed 2 stayed between 100 and 337 ms for 25 expiries, then 447, 547, 636, 707, 352, 499, … and climbed to 2,955 ms; seed 1 reached 444 ms at its 4th expiry and climbed to 3,116 ms. The database's queue passed 1,000 at 36.6 s (seed 2) and 10.2 s (seed 1).
- **XFetch refreshed earlier than the paper's bound.** For large n, the paper bounds the expected early-expiration gap by about β·Δ·ln(n·Δ): 230 ms at 100 reads/s and 461 ms at 1,000 reads/s with Δ = 100 ms. Measured (TTL 10 s): 828 ms and 963 ms on average, because Δ after an overlap is larger than 100 ms.

## Other runs
- [`runs/seed1.json`](runs/seed1.json): same picture. Plain at 1,000 reads/s: stampede 95.3 (TTL 2 s) and 97.5 (TTL 10 s). Lock: 1 everywhere. XFetch at TTL 10 s: 1.46–2.54. XFetch at 1,000 reads/s with TTL 2 s: runaway at 10.2 s. Its database overran the 100 ms recompute by more than 1 ms (p99) in five cells, against one in seed 2, so seed 2 is the recorded run.
- An earlier version had a 2 s TTL only and no runaway cutoff. In both of its runs, XFetch at 1,000 reads/s queued over 22,000 recomputes and the 60 s cell took 2,300–2,400 s to drain. That's why the cutoff and the 10 s TTL exist.

## Simulation check
`stampede/sim.js` is the same model without the network or overhead (Node: `node -e "console.log(require('./stampede/sim.js').simulate({strategy:'xfetch', rate:1000, ttlMs:2000}))"`). Stampede means over five 200-expiry simulations agree with the lab: plain 2.03 / 10.8 / 101.7 at TTL 2 s, lock 1, XFetch 1.61–2.25 at TTL 10 s. In 20 simulated hours each, XFetch with TTL 2 s ran away 20 times out of 20 at 1,000 reads/s (after 6–129 s) and 17 out of 20 at 100 reads/s (after 137–3,461 s); with TTL 10 s, 0 out of 20 at both rates.

## Notes
- The app was occasionally late handling a read: p99 at most 27 ms in any cell, worst single delay 159 ms (seed 2; 177 ms in seed 1), probably the OS scheduling something else on its core. The simulation, which has no such delays, gives the same stampede sizes.
- In the runaway cells the database's p99 overrun was 78 ms (seed 2) and 55 ms (seed 1), while it was receiving thousands of requests; in all other seed-2 cells it was at most 3.7 ms, and at most 0.22 ms in 16 of them.
- One "database" worker. A real database runs recomputes in parallel, but they still compete for the same CPU, disk and locks, so overlapping recomputes slow each other down in a similar way.
- Busy-waiting uses a whole core on each side; this is a lab setup, not how a server should wait.

The claims and their primary sources are in [`facts.md`](facts.md).
