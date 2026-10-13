# Lab: pagination, OFFSET vs keyset

- **What:** `pagination_lab.py` builds a SQLite table of 1,000,000 synthetic posts in memory (`posts(id, created_at, author, title)`, three posts per `created_at` value) with an index on `(created_at, id)`, and pages through it newest first, 20 rows per page, two ways:
  - **OFFSET:** `ORDER BY created_at DESC, id DESC LIMIT 20 OFFSET ?`
  - **keyset:** `WHERE (created_at, id) < (?, ?) ORDER BY created_at DESC, id DESC LIMIT 20`, where `?, ?` is the last row of the previous page (a row value comparison, SQLite ≥ 3.15).
- For pages 1, 10, 100, 1,000, 10,000 and 50,000 (the last) it checks that both methods return the same 20 rows, then records the median time and the virtual machine (VM) instructions each query ran (counted with a progress handler every 100 instructions, so the counts are rounded to hundreds).
- It also walks all 50,000 pages with keyset, with and without the `id` tie-breaker, and reads pages 1–3 while 5 newer posts are inserted, or 5 posts on page 1 are deleted, after page 1 was read.
- **Real or synthetic:** the rows are **synthetic**; every timing, plan and count is a **real measurement** of this script.
- **Run:** `python labs/pagination/pagination_lab.py` → prints and writes `results.json` (standard library only, about 6 seconds).

## Recorded run (2026-10-13, `results.json`)
Machine: AMD64 Family 23 Model 96 laptop, Windows 11, Python 3.12.10, SQLite 3.49.1. Medians of 101 runs (15 for OFFSET from page 1,000 on).

Plans: OFFSET `SCAN posts USING INDEX idx_created`; keyset `SEARCH posts USING INDEX idx_created (created_at<?)`.

| Page | Rows skipped | OFFSET | keyset | OFFSET VM instructions | keyset VM instructions |
|---|---|---|---|---|---|
| 1 | 0 | 0.0213 ms | 0.0209 ms | 200 | 200 |
| 10 | 180 | 0.0260 ms | 0.0228 ms | 700 | 300 |
| 100 | 1,980 | 0.0745 ms | 0.0229 ms | 6,100 | 300 |
| 1,000 | 19,980 | 0.541 ms | 0.0231 ms | 60,200 | 300 |
| 10,000 | 199,980 | 5.44 ms | 0.0227 ms | 600,100 | 300 |
| 50,000 (last) | 999,980 | 26.8 ms | 0.0221 ms | 3,000,100 | 300 |

- Last page with OFFSET, selecting only `id` (`SCAN posts USING COVERING INDEX idx_created`, the table is not read): 11.1 ms.
- `SELECT count(*) FROM posts`: 0.18 ms (`SCAN posts USING COVERING INDEX idx_created`).
- Walking all pages with keyset on `(created_at, id)`: 1,000,000 rows, all distinct. On `created_at` alone (`WHERE created_at < ?`): 952,380 rows, **47,620 never returned**.
- Writes between page loads (pages 2 and 3 read after the change):

| Change after page 1 was read | OFFSET | keyset |
|---|---|---|
| 5 newer posts inserted | 5 rows of page 1 shown again on page 2 | none repeated |
| 5 posts on page 1 deleted | 5 rows never shown | none missed |

Three full runs that day agreed closely: last page with OFFSET 26.8–27.3 ms, keyset 0.022 ms in all three; the write and walk counts were identical. `count(*)` ranged 0.18–0.20 ms (0.60 ms in an earlier run of the same script).

## Notes
- Timings include Python's call and fetch overhead; its share was not measured separately.
- The cursor for page N (last row of page N−1) is looked up before timing, as an app would already have it from the page it just showed.
- `never_shown` counts rows that were on page 2 when page 1 was read and appear on neither page 2 nor page 3 afterwards. With inserts, OFFSET pushes 5 rows of the old page 2 onto page 3, so they are late but not lost.

The claims and their primary sources are in [`facts.md`](facts.md).
