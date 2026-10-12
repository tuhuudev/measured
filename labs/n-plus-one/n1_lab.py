# The N+1 query problem, measured: every number in the article comes from one run of this script.
#   python labs/n-plus-one/n1_lab.py        (writes results.json next to this file; standard library only)
# Loads N authors and their posts three ways (N+1 queries, one JOIN, two queries with IN) and times each:
#   1. in-process: SQLite called directly, so a query costs a function call (sqlite.org/np1queryprob.html);
#   2. over TCP on localhost: a tiny server runs the same SQL, so every query costs one real round trip.
import json, os, platform, socket, socketserver, sqlite3, statistics, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
AUTHORS, POSTS_PER_AUTHOR = 10_000, 10
NS = [10, 100, 1000]
work = tempfile.mkdtemp()
path = os.path.join(work, 'n1.db')

def build(index=True):
    db = sqlite3.connect(path)
    db.executescript('DROP TABLE IF EXISTS posts; DROP TABLE IF EXISTS authors;'
                     'CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);'
                     'CREATE TABLE posts (id INTEGER PRIMARY KEY, author_id INTEGER, title TEXT);')
    db.executemany('INSERT INTO authors VALUES (?, ?)', ((i, f'author{i}') for i in range(1, AUTHORS + 1)))
    db.executemany('INSERT INTO posts (author_id, title) VALUES (?, ?)',
                   ((a, f'post{a}-{k}') for k in range(POSTS_PER_AUTHOR) for a in range(1, AUTHORS + 1)))
    if index:
        db.execute('CREATE INDEX idx_posts_author ON posts(author_id)')
    db.commit()
    return db

AUTHORS_SQL = 'SELECT id, name FROM authors ORDER BY id LIMIT ?'
POSTS_ONE_SQL = 'SELECT id, author_id, title FROM posts WHERE author_id = ?'
JOIN_SQL = ('SELECT a.id, a.name, p.id, p.author_id, p.title FROM (SELECT id, name FROM authors ORDER BY id LIMIT ?) a '
            'JOIN posts p ON p.author_id = a.id')

# Each strategy takes q(sql, params) -> rows and returns (number of queries, set of post ids loaded).
def n_plus_one(q, n):
    authors = q(AUTHORS_SQL, [n])
    posts = []
    for a in authors:
        posts += q(POSTS_ONE_SQL, [a[0]])
    return 1 + len(authors), {p[0] for p in posts}

def join(q, n):
    return 1, {r[2] for r in q(JOIN_SQL, [n])}

def in_batch(q, n):
    ids = [a[0] for a in q(AUTHORS_SQL, [n])]
    posts = q(f'SELECT id, author_id, title FROM posts WHERE author_id IN ({",".join("?" * len(ids))})', ids)
    return 2, {p[0] for p in posts}

STRATEGIES = {'n_plus_one': n_plus_one, 'join': join, 'in_batch': in_batch}

def measure(q, n, runs):
    out, expected = {}, None
    for name, fn in STRATEGIES.items():
        nq, ids = fn(q, n)  # warm-up, and check all three load the same posts
        expected = expected or ids
        assert ids == expected and len(ids) == n * POSTS_PER_AUTHOR, name
        ts = []
        for _ in range(runs):
            t = time.perf_counter(); fn(q, n); ts.append((time.perf_counter() - t) * 1000)
        out[name] = {'queries': nq, 'ms': round(statistics.median(ts), 3)}
    return out

R = {'sqlite': sqlite3.sqlite_version, 'python': platform.python_version(),
     'machine': platform.processor() or platform.machine(), 'os': platform.platform(),
     'authors': AUTHORS, 'posts': AUTHORS * POSTS_PER_AUTHOR, 'posts_per_author': POSTS_PER_AUTHOR}

# 1. In-process.
db = build()
inproc = lambda sql, params: db.execute(sql, params).fetchall()
R["in_process"] = {str(n): measure(inproc, n, runs=51 if n < 1000 else 21) for n in NS}

# Same N+1 loop without an index on posts.author_id: every per-author query scans all posts.
db.execute('DROP INDEX idx_posts_author')
nq, _ = n_plus_one(inproc, 100)
ts = []
for _ in range(5):
    t = time.perf_counter(); n_plus_one(inproc, 100); ts.append((time.perf_counter() - t) * 1000)
R['no_index_n_plus_one_100'] = {'queries': nq, 'ms': round(statistics.median(ts), 1),
                                'plan': ' / '.join(r[3] for r in db.execute('EXPLAIN QUERY PLAN ' + POSTS_ONE_SQL, [1]))}
db.execute('CREATE INDEX idx_posts_author ON posts(author_id)'); db.commit()
R['index_plan'] = ' / '.join(r[3] for r in db.execute('EXPLAIN QUERY PLAN ' + POSTS_ONE_SQL, [1]))
db.close()

# 2. Over TCP on localhost: one JSON line per query, one JSON line back. TCP_NODELAY on both ends so small
# messages are sent at once instead of waiting on Nagle's algorithm.
class Handler(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    def handle(self):
        conn = sqlite3.connect(path)
        for line in self.rfile:
            req = json.loads(line)
            rows = conn.execute(req['sql'], req['params']).fetchall()
            self.wfile.write((json.dumps(rows) + '\n').encode())
        conn.close()

server = socketserver.TCPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
sock = socket.create_connection(server.server_address)
sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
rf = sock.makefile('rb')
def remote(sql, params):
    sock.sendall((json.dumps({'sql': sql, 'params': params}) + '\n').encode())
    return json.loads(rf.readline())

ts = []
for _ in range(2001):
    t = time.perf_counter(); remote('SELECT 1', []); ts.append((time.perf_counter() - t) * 1000)
R['tcp_round_trip_ms'] = round(statistics.median(ts), 4)
R["over_tcp"] = {str(n): measure(remote, n, runs=51 if n < 1000 else 21) for n in NS}
rf.close(); sock.close()  # the makefile holds the socket open; close both so the server's handler returns
server.shutdown()

out = os.path.join(HERE, 'results.json')
with open(out, 'w') as fh:
    json.dump(R, fh, indent=1)
print(json.dumps(R, indent=1))
