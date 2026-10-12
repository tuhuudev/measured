# Lab: the N+1 query problem

- **What:** `n1_lab.py` builds a SQLite database of 10,000 authors with 10 posts each (100,000 posts, index on `posts.author_id`). It loads the first N authors (N = 10, 100, 1,000) and all their posts three ways and checks they load identical rows:
  - **N+1:** one query for the authors, then one query per author for their posts (1 + N queries);
  - **JOIN:** one query joining authors to posts;
  - **IN:** two queries, authors, then `posts WHERE author_id IN (…)`.
- Each strategy is timed twice:
  - **in-process:** Python calls SQLite directly, so a query is a function call;
  - **over TCP on localhost:** a tiny JSON-over-TCP server (standard library `socketserver`) runs the same SQL, so every query is one real network round trip. It is not a PostgreSQL or MySQL server; it only adds the round trip.
- It also times the N+1 loop for 100 authors **without** the `posts.author_id` index, and records both query plans.
- **Real or synthetic:** the rows are synthetic; every timing, plan and count is a real measurement of this script.
- **Run:** `python labs/n-plus-one/n1_lab.py` → prints and writes `results.json` (standard library only, about a minute).

## Recorded run (2026-10-12, `results.json`)
Machine: AMD64 Family 23 Model 96 laptop, Windows 11, Python 3.12.10, SQLite 3.49.1. Medians of 51 runs (21 for N = 1,000; 5 for the no-index loop).

| N | Strategy | Queries | In-process | Over TCP (localhost) |
|---|---|---|---|---|
| 10 | N+1 | 11 | 0.67 ms | 2.75 ms |
| 10 | JOIN | 1 | 0.19 ms | 0.50 ms |
| 10 | IN | 2 | 0.22 ms | 0.94 ms |
| 100 | N+1 | 101 | 5.81 ms | 25.8 ms |
| 100 | JOIN | 1 | 1.27 ms | 2.81 ms |
| 100 | IN | 2 | 1.10 ms | 2.66 ms |
| 1,000 | N+1 | 1,001 | 60.4 ms | 266 ms |
| 1,000 | JOIN | 1 | 14.4 ms | 29.5 ms |
| 1,000 | IN | 2 | 12.2 ms | 24.5 ms |

- Bare `SELECT 1` round trip over the localhost TCP server: 0.114 ms (median of 2,001).
- N+1 for 100 authors **without** the index: 602 ms, plan `SCAN posts` per query (with the index: `SEARCH posts USING INDEX idx_posts_author (author_id=?)`).
- Run-to-run variation: individual medians moved by up to about 40% between runs (mostly the sub-millisecond and TCP figures); the order of the strategies and the size of the N+1 gap held.

The claims and their primary sources are in [`facts.md`](facts.md).
