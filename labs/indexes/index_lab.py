# Database indexes, measured: every number in the article comes from one run of this script.
#   python labs/indexes/index_lab.py [workdir]     (writes results.json next to this file)
# Builds a 1,000,000-row SQLite table of synthetic users in memory, measures lookups and query plans
# there, then copies it to a file to read the real shape of the email index from the pages, its size, and write cost.
import json, os, platform, sqlite3, statistics, struct, sys, tempfile, time

N = 1_000_000
HERE = os.path.dirname(os.path.abspath(__file__))
work = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
path = os.path.join(work, 'lab.db')
if os.path.exists(path):
    os.remove(path)
R = {'sqlite': sqlite3.sqlite_version, 'python': platform.python_version(),
     'machine': platform.processor() or platform.machine(), 'os': platform.platform(), 'rows': N}

def rows(n, start=0):
    for i in range(start, start + n):
        yield (f'user{i}@example.com', f'name{i}', f'last{i % 1000}', f'first{i % 997}')

db = sqlite3.connect(':memory:')
db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT, last_name TEXT, first_name TEXT)')
db.executemany('INSERT INTO users (email, name, last_name, first_name) VALUES (?, ?, ?, ?)', rows(N))
db.commit()

def ms(sql, args=(), n=15):
    ts = []
    for _ in range(n):
        t = time.perf_counter(); db.execute(sql, args).fetchall(); ts.append((time.perf_counter() - t) * 1000)
    return round(statistics.median(ts), 4)
def plan(sql, args=()):
    return ' / '.join(r[3] for r in db.execute('EXPLAIN QUERY PLAN ' + sql, args).fetchall())

EQ = ('SELECT id FROM users WHERE email = ?', ('user777777@example.com',))
ORDER = 'SELECT email FROM users ORDER BY email LIMIT 10'
R['no_index'] = {'eq_plan': plan(*EQ), 'eq_ms': ms(*EQ), 'order_plan': plan(ORDER), 'order_ms': ms(ORDER, n=5)}
pages_before = db.execute('PRAGMA page_count').fetchone()[0]

t = time.perf_counter(); db.execute('CREATE INDEX idx_email ON users(email)'); db.commit()
R['create_index_ms'] = round((time.perf_counter() - t) * 1000)
R['with_index'] = {
    'eq_plan': plan(*EQ), 'eq_ms': ms(*EQ, n=201),
    'order_plan': plan(ORDER), 'order_ms': ms(ORDER, n=51),
    'range_plan': plan("SELECT count(*) FROM users WHERE email BETWEEN 'user5' AND 'user6'"),
    'suffix_like_plan': plan('SELECT id FROM users WHERE email LIKE ?', ('%777@example.com',)),
    'other_column_plan': plan('SELECT id FROM users WHERE name = ?', ('name777777',)),
    'other_column_ms': ms('SELECT id FROM users WHERE name = ?', ('name777777',)),
    'function_plan': plan('SELECT id FROM users WHERE lower(email) = ?', ('user777777@example.com',)),
    'function_ms': ms('SELECT id FROM users WHERE lower(email) = ?', ('user777777@example.com',)),
}
db.execute('CREATE INDEX idx_lower_email ON users(lower(email))')
R['expression_index'] = {'function_plan': plan('SELECT id FROM users WHERE lower(email) = ?', ('user777777@example.com',)),
                         'function_ms': ms('SELECT id FROM users WHERE lower(email) = ?', ('user777777@example.com',), n=201)}
db.execute('DROP INDEX idx_lower_email'); db.commit()

# Composite index: which column order can it seek on?
db.execute('CREATE INDEX idx_last_first ON users(last_name, first_name)'); db.commit()
CQ = {'last': ('SELECT id FROM users WHERE last_name = ?', ('last777',)),
      'last_first': ('SELECT id FROM users WHERE last_name = ? AND first_name = ?', ('last777', 'first123')),
      'first_only': ('SELECT id FROM users WHERE first_name = ?', ('first123',))}
R['composite'] = {k: {'plan': plan(*q), 'ms': ms(*q)} for k, q in CQ.items()}
# Skip scan (sqlite.org/optoverview.html section 6) is only considered after ANALYZE has measured duplicates.
db.execute('ANALYZE')
R['composite']['first_only_after_analyze'] = {'plan': plan(*CQ['first_only']), 'ms': ms(*CQ['first_only'])}
db.execute('DROP TABLE sqlite_stat1')
db.execute('DROP INDEX idx_last_first'); db.execute('VACUUM'); db.commit()
R['size'] = {'db_bytes_without_index': pages_before * 4096, 'db_bytes_with_index': db.execute('PRAGMA page_count').fetchone()[0] * 4096}
assert db.execute('PRAGMA page_size').fetchone()[0] == 4096

# Shape of idx_email, read from the file: walk the b-tree pages (SQLite file format, section 1.6).
file_db = sqlite3.connect(path); db.backup(file_db); file_db.close(); db.close()
with open(path, 'rb') as fh:
    data = fh.read()
page_size = struct.unpack('>H', data[16:18])[0] or 65536
db = sqlite3.connect(path)
root = db.execute("SELECT rootpage FROM sqlite_master WHERE name = 'idx_email'").fetchone()[0]
def page(no):
    off = (no - 1) * page_size
    return data[off:off + page_size], (100 if no == 1 else 0)
levels, frontier, leaf_cells, inner_cells = 0, [root], 0, 0
while frontier:
    levels += 1
    nxt = []
    for no in frontier:
        p, h = page(no)
        kind, ncell = p[h], struct.unpack('>H', p[h + 3:h + 5])[0]
        if kind == 0x02:   # interior index page: a left child per cell plus the right-most pointer
            ptrs = [struct.unpack('>H', p[h + 12 + 2 * i:h + 14 + 2 * i])[0] for i in range(ncell)]
            nxt += [struct.unpack('>I', p[c:c + 4])[0] for c in ptrs] + [struct.unpack('>I', p[h + 8:h + 12])[0]]
            inner_cells += ncell  # SQLite index b-trees keep keys in interior cells too
        elif kind == 0x0A:  # leaf index page
            leaf_cells += ncell
    if all(page(no)[0][page(no)[1]] == 0x0A for no in frontier):
        R['index_shape'] = {'page_size': page_size, 'levels': levels, 'leaf_pages': len(frontier),
                            'leaf_entries': leaf_cells, 'interior_entries': inner_cells, 'entries_per_leaf': round(leaf_cells / len(frontier), 1)}
        break
    frontier = nxt
db.close()

# Write cost: insert 200,000 rows into fresh tables with 0, 1 and 3 secondary indexes.
def insert_cost(nidx, n=200_000, runs=3):
    ts = []
    for _ in range(runs):
        d = sqlite3.connect(':memory:')
        d.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT, last_name TEXT, first_name TEXT)')
        for col in ['email', 'name', 'last_name'][:nidx]:
            d.execute(f'CREATE INDEX idx_{col} ON users({col})')
        t = time.perf_counter()
        d.executemany('INSERT INTO users (email, name, last_name, first_name) VALUES (?, ?, ?, ?)', rows(n))
        d.commit(); ts.append((time.perf_counter() - t) * 1000); d.close()
    return round(statistics.median(ts))
R['insert_200k_ms'] = {str(k): insert_cost(k) for k in (0, 1, 3)}

out = os.path.join(HERE, 'results.json')
with open(out, 'w') as fh:
    json.dump(R, fh, indent=1)
print(json.dumps(R, indent=1))
