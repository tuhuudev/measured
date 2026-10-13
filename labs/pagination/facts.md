# Fact sheet: pagination, measured

Every claim in the article maps to these IDs. Levels: established / simplified / contested. Measured rows come from `pagination_lab.py` → `results.json` (run 2026-10-13).

| ID | Claim | Level | Source |
|---|---|---|---|
| F1 | With `LIMIT x OFFSET y`, SQLite computes the query as `LIMIT x+y` and discards the first y rows, so OFFSET takes time proportional to the offset value. | established | [SQLite: Row values §3.1, Scrolling window queries](https://www.sqlite.org/rowvalue.html) ("OFFSET requires time proportional to the offset value. What really happens with "LIMIT x OFFSET y" is that SQLite computes the query as "LIMIT x+y" and discards the first y values without returning them to the application."). Checked 2026-10-13. |
| F2 | In PostgreSQL too, rows skipped by OFFSET still have to be computed, so a large OFFSET might be inefficient. | established | [PostgreSQL: LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html) ("The rows skipped by an OFFSET clause still have to be computed inside the server; therefore a large OFFSET might be inefficient."). Checked 2026-10-13. |
| F3 | Paging needs an `ORDER BY` that puts rows in a unique order; without it, different LIMIT/OFFSET values can give inconsistent results. | established | [PostgreSQL: LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html) ("it is important to use an ORDER BY clause that constrains the result rows into a unique order. Otherwise you will get an unpredictable subset of the query's rows."). Checked 2026-10-13. |
| F4 | The keyset alternative remembers the last row shown and asks for the rows after it with a row value comparison, e.g. `WHERE (lastname, firstname) > (?1, ?2)`; with an appropriate index this is much more efficient than OFFSET. | established | [SQLite: Row values §3.1](https://www.sqlite.org/rowvalue.html) ("A more efficient approach is to remember the last entry currently displayed and then use a row value comparison in the WHERE clause … assuming there is an appropriate index, it does so very efficiently — much more efficiently than OFFSET."). Checked 2026-10-13. |
| F5 | Row values were added in SQLite 3.15.0 (2016-10-14). | established | [SQLite: Row values §4](https://www.sqlite.org/rowvalue.html). Checked 2026-10-13. |
| F6 | `(a, b) < (x, y)` compares left to right, stopping at the first unequal pair; if that pair contains a NULL the result is unknown (NULL). | established | [PostgreSQL: Row constructor comparison §9.25.5](https://www.postgresql.org/docs/current/functions-comparisons.html) ("the row elements are compared left-to-right, stopping as soon as an unequal or null pair of elements is found. If either of this pair of elements is null, the result of the row comparison is unknown (null)"). Checked 2026-10-13. |
| F7 | In a SQLite plan, `SCAN` is a full pass (over the table, or over an index in index order) and `SEARCH` visits only a subset of rows. | established | [SQLite: EXPLAIN QUERY PLAN](https://www.sqlite.org/eqp.html). Checked 2026-10-08 (indexes article F7/F8). |
| F8 | Measured, 1,000,000 rows, 20 per page, index on `(created_at, id)`: OFFSET took 0.0213 ms on page 1, 0.541 ms on page 1,000, 5.44 ms on page 10,000 and 26.8 ms on the last page (50,000); keyset took 0.021–0.023 ms on every page. Plans: OFFSET `SCAN posts USING INDEX idx_created`, keyset `SEARCH posts USING INDEX idx_created (created_at<?)`. | established | Lab and `results.json`. Three runs: last page OFFSET 26.8–27.3 ms, keyset 0.022 ms. |
| F9 | Measured: VM instructions for OFFSET grew with the page (200 → 3,000,100, about 3 per skipped row); keyset stayed at 300 on every page after the first. | established | Lab (`offset_vm_steps`, `keyset_vm_steps`; progress handler every 100 instructions). |
| F10 | Measured: OFFSET on the last page selecting only `id` (a covering index scan, no table reads) still took 11.1 ms. | established | Lab (`last_page_ids_only_ms`). |
| F11 | Measured: walking every page with keyset on `created_at` alone (three posts share each timestamp) returned 952,380 of 1,000,000 rows (47,620 never returned); with `(created_at, id)` it returned all 1,000,000, each once. | established | Lab (`walk_all`). |
| F12 | Measured: if 5 newer posts arrive after page 1 is read, OFFSET's page 2 repeats 5 rows of page 1; if 5 posts on page 1 are deleted, 5 rows are never shown. Keyset had no repeats and no misses in both cases. | established | Lab (`writes_between_pages`). |
| F13 | Measured: `SELECT count(*)` on this table took 0.18 ms (`SCAN posts USING COVERING INDEX idx_created`). | established | Lab (`count`); three runs 0.18–0.20 ms. Not generalised to other databases. |

## Simplifications register
| # | Simplification | Why it is OK | On-screen caveat |
|---|---|---|---|
| S1 | Timings come from an in-memory SQLite database on one laptop; no disk, no network. | The growth with the page number is the point. | "SQLite in memory · 1M rows · one laptop" |
| S2 | PostgreSQL's OFFSET cost is stated from its docs (F2), not measured. | Labelled as such. | None |
| S3 | Keyset is shown for "next page" only; "previous page" (flip the comparison and the order) is mentioned, not measured. | Same mechanism. | None |
| S4 | Sort columns are assumed NOT NULL; NULLs need extra handling (F6). | Stated in a caveat. | None |
