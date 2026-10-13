# Fact sheet: queues, measured

Every claim in the article maps to these IDs. Levels: established / simplified / contested. Measured rows come from `queue_lab.py` → `results.json` (seed 2, run 2026-10-13); seed 3 in `runs/`.

| ID | Claim | Level | Source |
|---|---|---|---|
| F1 | M/M/1 means Poisson arrivals and exponential service times; M/D/1 Poisson arrivals and constant service times; M/G/1 Poisson arrivals and any service-time distribution, one server. | established | [MIT OCW 16.36, Lecture 20 (Modiano), slides 2 and 15](https://ocw.mit.edu/courses/16-36-communication-systems-engineering-spring-2009/resources/mit16_36s09_lec20/). Checked 2026-10-13. |
| F2 | Utilisation ρ = λ/μ = λ·E[service]. For M/M/1, mean time in system T = 1/(μ − λ), i.e. S/(1 − ρ) with S = 1/μ; it includes queueing delay plus service time. | established | MIT 16.36 Lecture 20, slides 4–5 ("T = 1/(μ−λ)"; "T includes the queueing delay plus the service time"). Checked 2026-10-13. |
| F3 | Pollaczek–Khinchine: for M/G/1 the mean wait in queue is W = λE[X²] / (2(1 − ρ)), and T = E[X] + W. With constant service this gives half the M/M/1 wait: ρ/(2μ(1−ρ)) vs ρ/(μ(1−ρ)). | established | MIT 16.36 Lecture 20, slides 16–18. Checked 2026-10-13. |
| F4 | Little's law: the average number in the system equals arrival rate × average time in the system, N = λT. | established | MIT 16.36 Lecture 20, slide 5 ("Little's formula (N=λT ⇒ T = N/λ)") and slide 16. Checked 2026-10-13. |
| F5 | Measured, exponential service with a 10 ms mean: mean time 21.6 ms and p99 109 ms at 50% target load (50.8% measured); 127 ms and 554 ms at 90% (91.1% measured). Seed 3: p99 100 ms and 568 ms. | established | Lab, `results.json`, `runs/seed3.json`. |
| F6 | Measured, constant 10 ms service at 90%: mean 54.9 ms (textbook 55.0) vs 127 ms with exponential service (textbook 100). | established | Lab. |
| F7 | Measured: the real server's mean was within 0.9–2.2% of an ideal FIFO replay of the same requests up to 80% load, 2.8–5.4% at 90%, 4.3–12.1% at 95%; its per-request overrun was at most 0.12 ms at p99. | established | Lab (`replay_mean_ms`, `service_overrun_p99_ms`), seeds 2 and 3. |
| F8 | Measured: mean number of requests in the server 1.12 at 50% and 12.0 at 90% (exponential), equal to λ × W. | established | Lab (`mean_in_system`, `little_lambda_w`). |
| F9 | Simulated: at 90% load with exponential service, consecutive windows of 3,000 requests had mean times from 56 to 438 ms, while the 200,000-request mean was 102 ms (textbook 100). | established | `queueing/sim.js`, seed 1 (run in Node and in the page). |
| F10 | Retries send extra requests, which adds load. | established | Our retries article: 200 clients sent 901–1,512 requests (`labs/retries/results.json`). |

## Simplifications register
| # | Simplification | Why it is OK | On-screen caveat |
|---|---|---|---|
| S1 | One server, FIFO, infinite queue, no timeouts. Real services have several workers, queue limits and clients that give up. | The single-server queue is the simplest system that shows the shape. | "one worker" |
| S2 | Load is set by the client; utilisation is measured. 3,000 requests per load step is a short window, so high-load numbers vary a lot between runs (F9). | Shown with three runs and the simulation. | "3,000 requests per load" |
| S3 | The server busy-waits on a dedicated core at high priority; time includes localhost round trip and Python overhead (~0.1 ms). | Makes service times precise; the replay shows the real server's own cost (F7). | None |
| S4 | Theory quoted for the mean only; p99 is compared to the replay, not to a formula. | The lecture source covers means. | None |
