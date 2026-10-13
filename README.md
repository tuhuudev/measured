# Measured

Developer concepts with numbers you can reproduce: **https://tuhuudev.github.io/measured/**

Every article has:
- a **lab** in `labs/<topic>/` that produces every number in the article (standard library only where possible),
- the **raw results** it produced (`results.json`) and the machine it ran on,
- a **primary source** (official docs, specs, RFCs) for every claim that isn't a measurement,
- where possible, something you can **try in the page**.

| Article | Lab |
|---|---|
| [Database indexes, measured](https://tuhuudev.github.io/measured/indexes/) | [`labs/indexes`](labs/indexes) (`python labs/indexes/index_lab.py`) |
| [The N+1 query problem, measured](https://tuhuudev.github.io/measured/n-plus-one/) | [`labs/n-plus-one`](labs/n-plus-one) (`python labs/n-plus-one/n1_lab.py`) |
| [Retries, measured: why backoff needs jitter](https://tuhuudev.github.io/measured/retries/) | [`labs/retries`](labs/retries) (`python labs/retries/retry_lab.py`) |
| [Pagination, measured: OFFSET vs keyset](https://tuhuudev.github.io/measured/pagination/) | [`labs/pagination`](labs/pagination) (`python labs/pagination/pagination_lab.py`) |
| [Batching writes, measured: one transaction vs one per row](https://tuhuudev.github.io/measured/batching/) | [`labs/batching`](labs/batching) (`python labs/batching/batching_lab.py`) |
| [Queues, measured: why latency explodes near full load](https://tuhuudev.github.io/measured/queueing/) | [`labs/queueing`](labs/queueing) (`python labs/queueing/queue_lab.py`) |

The site is plain static HTML with no build step. To preview it, run `python -m http.server` in the repo root and open http://localhost:8000/.

Found an error? Open an issue. Corrections are logged in [`CORRECTIONS.md`](CORRECTIONS.md).

Licence: code MIT ([LICENSE](LICENSE)), article text CC BY 4.0.
