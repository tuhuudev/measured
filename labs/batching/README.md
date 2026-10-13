# Lab: batching writes into transactions

- **What:** `batching_lab.py` inserts 10,000 rows (`events(id, ts, payload)`, about 110 bytes of text each) into a SQLite database **file**, committing after every 1, 10, 100, 1,000 or all 10,000 rows, in three modes:
  - `journal_mode=DELETE`, `synchronous=FULL` (SQLite's default: rollback journal, wait for the disk on every commit);
  - `journal_mode=WAL`, `synchronous=FULL`;
  - `journal_mode=WAL`, `synchronous=NORMAL` (no sync on commit; a power loss can roll back recent commits).
- Every batch is an explicit `BEGIN` … `COMMIT` on a connection with `isolation_level=None`, so the number of commits is exactly 10,000 / batch size. Each cell is the median of 3 trials on a fresh file.
- It also measures Python's **default** connection (implicit transactions): a loop of `execute()` with one `commit()` at the end, the same loop with `commit()` after every row, and `executemany()` with one commit.
- From each mode's batch-1 and batch-10,000 times it derives a two-point model, `total ≈ commits × per_commit + rows × per_row`, and records how far it is off for the batch sizes in between.
- **Real or synthetic:** the rows are **synthetic**; every timing is a **real measurement** of this script on a real disk.
- **Run:** `python labs/batching/batching_lab.py [workdir]` → prints and writes `results.json` (standard library only, about 3 minutes; the default mode with one commit per row takes about 25 s on its own, three times).

## Recorded run (2026-10-13, `results.json`)
Machine: AMD64 Family 23 Model 96 laptop, Windows 11, Python 3.12.10, SQLite 3.49.1. Database files on drive C:, an NVMe SSD (ADATA SX8100NP, read with `Get-PhysicalDisk`). Medians of 3 trials.

10,000 inserts, by rows per commit:

| Mode | 1 (10,000 commits) | 10 | 100 | 1,000 | 10,000 (1 commit) | per commit (model) |
|---|---|---|---|---|---|---|
| DELETE + FULL (default) | 25,168 ms | 2,166 ms | 240 ms | 44.8 ms | 23.6 ms | 2.51 ms |
| WAL + FULL | 3,389 ms | 316 ms | 54.9 ms | 27.2 ms | 22.9 ms | 0.337 ms |
| WAL + NORMAL | 249 ms | 58.1 ms | 26.9 ms | 22.0 ms | 21.2 ms | 0.0228 ms |

Per row, the model gives 0.0021–0.0023 ms in every mode.

Python's default connection (`isolation_level` is `''`, and `in_transaction` was already `True` after the first `INSERT`), DELETE + FULL:

| Code | Median |
|---|---|
| loop of `execute()`, one `commit()` at the end | 25.3 ms |
| same loop, `commit()` after every row | 23,500 ms |
| `executemany()`, one `commit()` | 18.8 ms |

## Spread
The lab was run three times in full that day; runs 2 and 3 are [`runs/run1.json`](runs/run1.json) and [`runs/run2.json`](runs/run2.json) (same format).
- DELETE + FULL, one commit per row: 25.2–26.6 s; one commit for all: 23.6–27.3 ms.
- WAL + FULL, one commit per row: 2.78–3.39 s. WAL + NORMAL, one commit per row: 247–252 ms.
- Python default loop with a commit per row: 23.5–28.3 s.
- Per-commit cost from the model: 2.51–2.66 ms (DELETE + FULL), 0.276–0.337 ms (WAL + FULL), 0.0225–0.0230 ms (WAL + NORMAL).
- Individual trials vary more than medians: in run 2, one DELETE + FULL trial at batch 100 took 1,120 ms against a median of 314 ms.
- The two-point model was within ±25% of the measured median for the batch sizes in between in all but one cell (WAL + FULL, batch 100, run 2: −40.6%).

## Notes
- Disk timings depend on the drive, its write cache, the file system and the OS. Expect different per-commit costs on another machine; the ratios between batch sizes are the point.
- Each trial starts from a new, empty file, so the time includes growing the file. No indexes besides the rowid.
- `synchronous=OFF` is not measured; SQLite's docs warn that it can corrupt the database on an OS crash or power loss.
- Timings include Python's call overhead.

The claims and their primary sources are in [`facts.md`](facts.md).
