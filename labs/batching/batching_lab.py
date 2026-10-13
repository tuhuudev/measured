# Batching writes, measured: every number in the article comes from one run of this script.
#   python labs/batching/batching_lab.py [workdir]     (writes results.json next to this file; about 3 minutes)
# Inserts 10,000 rows into a SQLite database FILE with one commit per row, per 10, 100, 1,000 rows, or one commit
# for all, in three journal/synchronous modes. Unlike the other labs this one touches the disk, so the drive matters.
import json, os, platform, sqlite3, statistics, sys, tempfile, time

N, TRIALS = 10_000, 3
BATCHES = [1, 10, 100, 1_000, 10_000]
MODES = [('DELETE', 'FULL'), ('WAL', 'FULL'), ('WAL', 'NORMAL')]   # the first is SQLite's default
HERE = os.path.dirname(os.path.abspath(__file__))
work = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
R = {'sqlite': sqlite3.sqlite_version, 'python': platform.python_version(),
     'machine': platform.processor() or platform.machine(), 'os': platform.platform(), 'rows': N, 'trials': TRIALS,
     'workdir_drive': os.path.splitdrive(os.path.abspath(work))[0] or '/'}
ROW = lambda i: (1_700_000_000 + i, f'event {i} ' + 'x' * 100)

def fresh(name, journal=None, sync=None, **kw):
    path = os.path.join(work, name)
    for suffix in ('', '-journal', '-wal', '-shm'):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)
    db = sqlite3.connect(path, **kw)
    if journal:
        got = db.execute(f'PRAGMA journal_mode={journal}').fetchone()[0]
        assert got.upper() == journal, got
        db.execute(f'PRAGMA synchronous={sync}')
    db.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, ts INTEGER, payload TEXT)')
    db.commit()
    return db

def batched(journal, sync, batch):
    # isolation_level=None: Python opens no transactions of its own, so each BEGIN ... COMMIT below is exactly one commit.
    db = fresh('lab.db', journal, sync, isolation_level=None)
    t = time.perf_counter()
    for start in range(0, N, batch):
        db.execute('BEGIN')   # explicit even for batch 1, so every batch size issues the same statements per commit
        for i in range(start, start + batch):
            db.execute('INSERT INTO events (ts, payload) VALUES (?, ?)', ROW(i))
        db.execute('COMMIT')
    ms = (time.perf_counter() - t) * 1000
    assert db.execute('SELECT count(*) FROM events').fetchone()[0] == N
    db.close()
    return ms

R['modes'] = []
for journal, sync in MODES:
    runs = {b: [batched(journal, sync, b) for _ in range(TRIALS)] for b in BATCHES}
    rows = [{'batch': b, 'commits': N // b, 'ms': round(statistics.median(v), 1), 'min_ms': round(min(v), 1), 'max_ms': round(max(v), 1)}
            for b, v in runs.items()]
    # Two-point model  total = commits * per_commit + N * per_row, from batch 1 (N commits) and batch N (1 commit);
    # the batch sizes in between check how well it predicts.
    t1, tn = rows[0]['ms'], rows[-1]['ms']
    per_commit = (t1 - tn) / (N - 1)
    per_row = (tn - per_commit) / N
    for r in rows:
        r['model_ms'] = round(r['commits'] * per_commit + N * per_row, 1)
        r['model_error_pct'] = round((r['model_ms'] - r['ms']) / r['ms'] * 100, 1)
    R['modes'].append({'journal_mode': journal, 'synchronous': sync, 'batches': rows,
                       'fit': {'per_commit_ms': round(per_commit, 4), 'per_row_ms': round(per_row, 5)}})
    print(journal, sync, [(r['batch'], r['ms'], r['min_ms'], r['max_ms'], r['model_error_pct']) for r in rows], R['modes'][-1]['fit'], flush=True)

# Python's default connection (legacy transaction control): the first INSERT implicitly opens a transaction,
# so a loop of execute() calls followed by one commit() is a single transaction.
def default_loop(commit_each):
    db = fresh('lab.db')   # default journal_mode=DELETE, synchronous=FULL
    implicit = None
    t = time.perf_counter()
    for i in range(N):
        db.execute('INSERT INTO events (ts, payload) VALUES (?, ?)', ROW(i))
        if implicit is None:
            implicit = db.in_transaction
        if commit_each:
            db.commit()
    db.commit()
    ms = (time.perf_counter() - t) * 1000
    db.close()
    return ms, implicit
loop = [default_loop(False) for _ in range(TRIALS)]
each = [default_loop(True) for _ in range(TRIALS)]
def many():
    db = fresh('lab.db')
    t = time.perf_counter()
    db.executemany('INSERT INTO events (ts, payload) VALUES (?, ?)', (ROW(i) for i in range(N)))
    db.commit()
    ms = (time.perf_counter() - t) * 1000
    db.close()
    return ms
R['python_default'] = {
    'isolation_level': sqlite3.connect(':memory:').isolation_level,
    'in_transaction_after_first_insert': loop[0][1],
    'loop_one_commit_ms': round(statistics.median(m for m, _ in loop), 1),
    'loop_commit_each_ms': round(statistics.median(m for m, _ in each), 1),
    'executemany_one_commit_ms': round(statistics.median(many() for _ in range(TRIALS)), 1),
}
print(R['python_default'])

out = os.path.join(HERE, 'results.json')
with open(out, 'w') as fh:
    json.dump(R, fh, indent=1)
print(json.dumps(R, indent=1))
