# Pagination, measured: every number in the article comes from one run of this script.
#   python labs/pagination/pagination_lab.py     (writes results.json next to this file)
# Builds a 1,000,000-row SQLite table of synthetic posts in memory and pages through it newest first,
# 20 rows per page, with LIMIT/OFFSET and with a keyset (row value) cursor: time, VM work, and what goes wrong under writes.
import json, os, platform, sqlite3, statistics, sys, time

N, PAGE = 1_000_000, 20
PAGES = [1, 10, 100, 1_000, 10_000, N // PAGE]
HERE = os.path.dirname(os.path.abspath(__file__))
R = {'sqlite': sqlite3.sqlite_version, 'python': platform.python_version(),
     'machine': platform.processor() or platform.machine(), 'os': platform.platform(), 'rows': N, 'page_size': PAGE}

db = sqlite3.connect(':memory:')
db.execute('CREATE TABLE posts (id INTEGER PRIMARY KEY, created_at INTEGER, author TEXT, title TEXT)')
# Three posts share each timestamp, so created_at alone is not unique and the tie-breaker matters.
db.executemany('INSERT INTO posts (created_at, author, title) VALUES (?, ?, ?)',
               ((1_700_000_000 + i // 3, f'author{i % 5000}', f'Post number {i}') for i in range(N)))
db.execute('CREATE INDEX idx_created ON posts(created_at, id)')
db.commit()

COLS = 'id, created_at, author, title'
FIRST = f'SELECT {COLS} FROM posts ORDER BY created_at DESC, id DESC LIMIT {PAGE}'
OFFSET = f'SELECT {COLS} FROM posts ORDER BY created_at DESC, id DESC LIMIT {PAGE} OFFSET ?'
KEYSET = f'SELECT {COLS} FROM posts WHERE (created_at, id) < (?, ?) ORDER BY created_at DESC, id DESC LIMIT {PAGE}'
OFFSET_IDS = f'SELECT id FROM posts ORDER BY created_at DESC, id DESC LIMIT {PAGE} OFFSET ?'

def ms(sql, args=(), n=15):
    ts = []
    for _ in range(n):
        t = time.perf_counter(); db.execute(sql, args).fetchall(); ts.append((time.perf_counter() - t) * 1000)
    return round(statistics.median(ts), 4)
def plan(sql, args=()):
    return ' / '.join(r[3] for r in db.execute('EXPLAIN QUERY PLAN ' + sql, args).fetchall())
def vm_steps(sql, args=()):
    # The progress handler runs every 100 virtual machine instructions: a count of the work, not of rows.
    calls = [0]
    def tick():
        calls[0] += 1
        return 0
    db.set_progress_handler(tick, 100)
    db.execute(sql, args).fetchall()
    db.set_progress_handler(None, 100)
    return calls[0] * 100
def page_query(p, keyset):
    off = (p - 1) * PAGE
    if p == 1:
        return FIRST, ()
    if not keyset:
        return OFFSET, (off,)
    # Cursor = last row of the previous page, as the app would have it from the page it just showed (not timed).
    return KEYSET, db.execute(f'SELECT created_at, id FROM posts ORDER BY created_at DESC, id DESC LIMIT 1 OFFSET ?', (off - 1,)).fetchone()

R['plans'] = {'offset': plan(OFFSET, (1000,)), 'keyset': plan(KEYSET, (1_700_100_000, 300_000))}
R['pages'] = []
for p in PAGES:
    oq, ka = page_query(p, False), page_query(p, True)
    rows_o, rows_k = db.execute(*oq).fetchall(), db.execute(*ka).fetchall()
    assert rows_o == rows_k and len(rows_o) == PAGE, p
    deep = p >= 1_000
    R['pages'].append({'page': p, 'offset': (p - 1) * PAGE,
                       'offset_ms': ms(*oq, n=15 if deep else 101), 'keyset_ms': ms(*ka, n=101),
                       'offset_vm_steps': vm_steps(*oq), 'keyset_vm_steps': vm_steps(*ka)})
last = PAGES[-1]
R['last_page_ids_only_ms'] = ms(OFFSET_IDS, ((last - 1) * PAGE,))
R['last_page_ids_only_plan'] = plan(OFFSET_IDS, ((last - 1) * PAGE,))

# Showing "page X of Y" needs the total count.
R['count'] = {'plan': plan('SELECT count(*) FROM posts'), 'ms': ms('SELECT count(*) FROM posts')}

# Walking every page with keyset: with the (created_at, id) tie-breaker, and with created_at alone.
def walk(tiebreak):
    seen, cur = [], None
    while True:
        if cur is None:
            rows = db.execute(FIRST).fetchall()
        elif tiebreak:
            rows = db.execute(KEYSET, (cur[1], cur[0])).fetchall()
        else:
            rows = db.execute(f'SELECT {COLS} FROM posts WHERE created_at < ? ORDER BY created_at DESC, id DESC LIMIT {PAGE}', (cur[1],)).fetchall()
        if not rows:
            return seen
        seen += [r[0] for r in rows]; cur = rows[-1]
w_tie, w_no = walk(True), walk(False)
R['walk_all'] = {'with_tiebreak': {'rows_seen': len(w_tie), 'distinct': len(set(w_tie))},
                 'created_at_only': {'rows_seen': len(w_no), 'distinct': len(set(w_no)), 'missed': N - len(set(w_no))}}
assert len(w_tie) == len(set(w_tie)) == N

# Writes between page loads: read page 1, then 5 new posts arrive (or 5 posts on page 1 are deleted), then read pages 2 and 3.
def between_pages(change, undo):
    before = [r[0] for r in db.execute(f'SELECT id FROM posts ORDER BY created_at DESC, id DESC LIMIT {3 * PAGE}')]
    p1 = db.execute(FIRST).fetchall()
    change()
    off = [db.execute(OFFSET, (k * PAGE,)).fetchall() for k in (1, 2)]
    k2 = db.execute(KEYSET, (p1[-1][1], p1[-1][0])).fetchall()
    key = [k2, db.execute(KEYSET, (k2[-1][1], k2[-1][0])).fetchall()]
    undo()
    ids1 = {r[0] for r in p1}
    def score(pages):
        got = [r[0] for p in pages for r in p]
        # never_shown: rows that were on page 2 when page 1 was read but appear on neither page 2 nor page 3.
        return {'repeated_from_page_1': sum(i in ids1 for i in got),
                'never_shown': sum(i not in got for i in before[PAGE:2 * PAGE])}
    return {'offset': score(off), 'keyset': score(key)}
top = db.execute('SELECT max(created_at) FROM posts').fetchone()[0]
new_ids = []
def add5():
    for k in range(5):
        new_ids.append(db.execute('INSERT INTO posts (created_at, author, title) VALUES (?, ?, ?)', (top + 1 + k, 'new', 'new post')).lastrowid)
def undo_add():
    db.executemany('DELETE FROM posts WHERE id = ?', [(i,) for i in new_ids])
gone = []
def del5():
    gone[:] = db.execute(f'SELECT * FROM posts ORDER BY created_at DESC, id DESC LIMIT 5').fetchall()
    db.executemany('DELETE FROM posts WHERE id = ?', [(r[0],) for r in gone])
def undo_del():
    db.executemany('INSERT INTO posts (id, created_at, author, title) VALUES (?, ?, ?, ?)', gone)
R['writes_between_pages'] = {'insert_5_newer': between_pages(add5, undo_add), 'delete_5_on_page_1': between_pages(del5, undo_del)}
assert db.execute('SELECT count(*) FROM posts').fetchone()[0] == N

out = os.path.join(HERE, 'results.json')
with open(out, 'w') as fh:
    json.dump(R, fh, indent=1)
print(json.dumps(R, indent=1))
