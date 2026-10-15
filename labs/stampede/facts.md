# Fact sheet: cache stampede, measured

Every claim in the article maps to these IDs. Levels: established / simplified / contested. Measured rows come from `stampede_lab.py` → `results.json` (seed 2, run 2026-10-15); seed 1 in `runs/`. Paper: Vattani, Chierichetti, Lowenstein, *Optimal Probabilistic Cache Stampede Prevention*, PVLDB 8(8):886–897, 2015, <https://www.vldb.org/pvldb/vol8/p886-vattani.pdf>.

| ID | Claim | Level | Source |
|---|---|---|---|
| F1 | A cache stampede is when a frequently read item expires and many requests miss and regenerate it at the same time; concurrent recomputations slow each other down. | established | Paper, abstract and Sec. 1. Checked 2026-10-15. |
| F2 | Probabilistic early expiration: each request independently decides to regenerate before expiry, with a probability that grows as expiry approaches. | established | Paper, Sec. 1. Checked 2026-10-15. |
| F3 | XFetch (Fig. 3): recompute if `Time() − Δ·β·log(rand()) ≥ expiry`; Δ is the recompute time measured around `RecomputeValue()` and stored with the value; β defaults to 1. | established | Paper, Fig. 3 and Sec. 5. Checked 2026-10-15. |
| F4 | Stampede size: the number of regenerations within one recompute time of the first one. | established | Paper, Definition 3. Checked 2026-10-15. |
| F5 | For β = 1 (λ = 1), expected stampede size about e − 1/e ≈ 2.4 and early-expiration gap about log n recompute times, n = requests per recompute time; bounds for large n. Example: 10,000 requests per minute, 1-minute recompute: about 9.2 minutes early. | established | Paper, Theorem 7 and the example after it (Sec. 3). Checked 2026-10-15. |
| F6 | Measured, plain TTL, 1,000 reads/s, TTL 2 s: 98.4 recomputes per expiry on average (max 112), slowest read 11.1 s, p99 0.004 ms, p99.9 8.6 s, 0.82% of reads waited, database busy 82%. Seed 1: 95.3. | established | Lab. |
| F7 | Measured, lock: exactly 1 recompute per expiry at every rate and TTL; no read waited longer than 106 ms. At 1,000 reads/s, TTL 2 s, 4.8% of reads waited, median 52 ms. | established | Lab. |
| F8 | Measured, XFetch, TTL 10 s: mean stampede 1.92 / 2.33 / 1.85 at 10 / 100 / 1,000 reads/s; at 1,000 reads/s, 24 of 120,137 reads waited and p99.9 was 0.016 ms. Seed 1: 1.46–2.54. | established | Lab. |
| F9 | Measured, XFetch, 1,000 reads/s, TTL 2 s: the database's queue passed 1,000 recomputes at 36.6 s (seed 2) and 10.2 s (seed 1). Δ at the start of each stampede rose from 100 ms to 2,955 ms (seed 2) and 3,116 ms (seed 1). | established | Lab (`runaway_at_s`, `stampede_delta_ms`). |
| F10 | Δ·ln(n·Δ) equals the TTL at Δ ≈ 343 ms (TTL 2 s) and 1,383 ms (TTL 10 s), for n = 1,000 reads/s. | established | Arithmetic from F5's gap formula. |
| F11 | Measured XFetch early-expiration gap, TTL 10 s: 828 ms (100 reads/s) and 963 ms (1,000 reads/s) on average, against β·Δ·ln(n·Δ) = 230 and 461 ms with Δ = 100 ms. | established | Lab (`early_gap_mean_ms`, `predicted_gap_ms`). |
| F12 | Simulated: XFetch with TTL 2 s ran away in 20 of 20 one-hour runs at 1,000 reads/s and 17 of 20 at 100 reads/s; with TTL 10 s, 0 of 20 at both. | established | `stampede/sim.js`, seeds 1–20 (Node). |
| F13 | One-worker FIFO queues: waiting grows sharply as utilisation approaches 100%. | established | Our queueing article (`labs/queueing`). |

## Simplifications register
| # | Simplification | Why it is OK | On-screen caveat |
|---|---|---|---|
| S1 | One hot key, one "database" worker serving recomputes one at a time. A real database runs them in parallel. | Parallel recomputes still compete for the same CPU, disk and locks; one worker is the simplest system where overlapping recomputes slow each other down (F1). | "one worker" |
| S2 | Recompute time is a constant 100 ms of busy-waiting. | Makes the database's own cost exact; measured overrun ≤ 0.22 ms (p99) in 16 of 17 non-runaway cells of seed 2. | None |
| S3 | XFetch's recomputing read waits for the result, as in Fig. 3; no background refresh. | That's the algorithm as published. | "as published" |
| S4 | The runaway cells stop at 1,000 queued recomputes. | Otherwise one 60 s cell took 2,300–2,400 s. The numbers before the cutoff are kept. | "stopped at 1,000 queued recomputes" |
| S5 | The app was occasionally late handling a read (up to 159 ms in seed 2). | The simulation, without such delays, gives the same stampede sizes. | In the data notes |
