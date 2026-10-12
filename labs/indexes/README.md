# Lab: database indexes

- **What:** `index_lab.py` builds a SQLite table of 1,000,000 synthetic users (`user{i}@example.com`, `name{i}`, `last{i % 1000}`, `first{i % 997}`) in memory, measures lookups and query plans, copies the database to a file and walks the pages of `idx_email` to read the index's real shape (SQLite file format §1.6), then times 200,000 inserts with 0, 1 and 3 secondary indexes.
- **Real or synthetic:** the rows are **synthetic**; every timing, plan, page count and size is a **real measurement** of this script.
- **Run:** `python labs/indexes/index_lab.py [workdir]` → prints and writes `results.json` (standard library only).

## Recorded run (2026-10-08, `results.json`)
Machine: AMD64 Family 23 Model 96 laptop, Windows 11, Python 3.12.10, SQLite 3.49.1. Medians (15 runs; 201 for sub-millisecond lookups). Two earlier runs the same night agreed within a few percent.

| Measurement | Plan | Median |
|---|---|---|
| `WHERE email = ?`, no index | `SCAN users` | 64.2 ms |
| `WHERE email = ?`, index on email | `SEARCH users USING COVERING INDEX idx_email (email=?)` | 0.0031 ms |
| `ORDER BY email LIMIT 10`, no index | `SCAN users / USE TEMP B-TREE FOR ORDER BY` | 93.7 ms |
| `ORDER BY email LIMIT 10`, index | `SCAN users USING COVERING INDEX idx_email` (no temp b-tree; stops after 10) | 0.0052 ms |
| `email BETWEEN 'user5' AND 'user6'` | `SEARCH … (email>? AND email<?)` | — |
| `email LIKE '%777@example.com'` | `SCAN users USING COVERING INDEX idx_email` | — |
| `name = ?` (no index on name) | `SCAN users` | 69.3 ms |
| `lower(email) = ?`, index on email only | `SCAN users USING COVERING INDEX idx_email` | 196.9 ms |
| `lower(email) = ?`, index on `lower(email)` | `SEARCH … idx_lower_email (<expr>=?)` | 0.0031 ms |
| index `(last_name, first_name)`: `last_name = ? AND first_name = ?` | `SEARCH … (last_name=? AND first_name=?)` | 0.0038 ms |
| same index: `first_name = ?` only, no stats | `SCAN users USING COVERING INDEX idx_last_first` | 63.9 ms |
| same, after `ANALYZE` | `SEARCH … (ANY(last_name) AND first_name=?)` (skip-scan) | 2.55 ms |
| `CREATE INDEX idx_email` | — | 0.53 s |

Index shape (`idx_email`, read from the file): page size 4,096 bytes, **3 levels**, **7,519 leaf pages**, 992,482 entries in leaves + 7,518 in interior pages (= 1,000,000; SQLite index b-trees keep keys in interior cells too), about 132 entries per leaf page.

Size: database 59,129,856 bytes without the index, 90,193,920 bytes with it (+31.1 MB, +53%).

Write cost, 200,000 inserts into a fresh table: 0 indexes 374 ms, 1 index 551 ms, 3 indexes 1,015 ms.

Timings depend on the machine; the article labels them "SQLite in memory · 1M rows · one laptop". The claims and their primary sources are in [`facts.md`](facts.md).
