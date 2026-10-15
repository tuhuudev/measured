# Cache stampede, measured: every number in the article comes from one run of this script.
#   python labs/stampede/stampede_lab.py [seed]      (writes results.json next to this file; about 30 minutes)
# A real "database" in its own process on localhost recomputes one hot value; each recompute busy-waits 100 ms, one at
# a time, first come first served. An app reads that value through an in-process cache with a 2 s or 10 s TTL, at random
# (Poisson) times. Three ways to refresh the cache: plain TTL (every read that sees it expired recomputes), a lock
# (only the first one does, the others wait for it), and XFetch (probabilistic early expiration, Vattani et al. 2015).
import gc, json, math, multiprocessing, os, platform, random, socket, statistics, struct, sys, time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
RECOMPUTE_MS = 100.0
TTLS = [2.0, 10.0]
DURATION_S = {2.0: 60.0, 10.0: 120.0}   # about 30 and 12 expiries
RUNAWAY = 1000                          # recomputes waiting at the database: stop the cell instead of draining for an hour
BETA = 1.0
RATES = [10, 100, 1000]               # reads per second: 1, 10 and 100 reads per recompute time
STRATEGIES = ['plain', 'lock', 'xfetch']
SERVER_CPU, CLIENT_CPU = 2, 4         # logical CPUs on different physical cores of the lab machine (4 cores, 8 threads)
REQ, REP = struct.Struct('<IQ'), struct.Struct('<I')     # request: id, service in ns; reply: id
STATS, CANCEL = 0xFFFFFFFF, 0xFFFFFFFE
now_ns = time.perf_counter_ns

def dedicate(cpu):
    # Both sides busy-poll; give each its own core, high priority and no GC pauses (see labs/queueing).
    gc.disable()
    if sys.platform == 'win32':
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetCurrentProcess()
        k.SetPriorityClass(h, 0x80)              # HIGH_PRIORITY_CLASS
        k.SetProcessAffinityMask(h, 1 << cpu)
    elif hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, {cpu})

# ---- database process: one worker, FIFO, busy-waits each recompute ------------------------------------------------
def server_process(port_q):
    dedicate(SERVER_CPU)
    ls = socket.create_server(('127.0.0.1', 0))
    port_q.put(ls.getsockname()[1])
    conn, _ = ls.accept()
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    conn.setblocking(False)
    buf, queue, busy = b'', deque(), None
    overrun, busy_ns = [], 0
    while True:
        t = now_ns()
        if busy and t >= busy[1]:
            rid, deadline, started = busy
            conn.sendall(REP.pack(rid))
            t = now_ns()
            overrun.append(t - deadline); busy_ns += t - started
            busy = None
        try:
            data = conn.recv(65536)
        except BlockingIOError:
            data = None
        if data == b'':
            return
        if data:
            buf += data
            while len(buf) >= REQ.size:
                rid, svc = REQ.unpack_from(buf); buf = buf[REQ.size:]
                if rid == STATS:
                    conn.setblocking(True); conn.sendall((json.dumps({'overrun_ns': overrun, 'busy_ns': busy_ns}) + '\n').encode()); conn.setblocking(False)
                    overrun, busy_ns = [], 0
                    continue
                if rid == CANCEL:      # runaway: drop the waiting recomputes, finish the current one now, then acknowledge
                    queue.clear()
                    if busy:
                        conn.sendall(REP.pack(busy[0])); busy_ns += now_ns() - busy[2]; busy = None
                    conn.sendall(REP.pack(CANCEL))
                    continue
                queue.append((rid, svc))
        if busy is None and queue:
            rid, svc = queue.popleft()
            t = now_ns()
            busy = (rid, t + svc, t)

# ---- app: Poisson reads through an in-process cache, single thread polling -----------------------------------------
def trial(sock, rfile, strategy, rate, ttl_s, duration_s, rng):
    svc, ttl = int(RECOMPUTE_MS * 1e6), int(ttl_s * 1e9)
    sock.setblocking(False)
    buf = b''
    def wait_reply():
        nonlocal buf
        while True:
            try:
                data = sock.recv(65536)
            except BlockingIOError:
                data = b''
            buf += data
            if len(buf) >= REP.size:
                (rid,), buf = REP.unpack_from(buf), buf[REP.size:]
                return rid
    # Warm the cache with one recompute, so the run starts with a fresh value, like a service that has been up a while.
    t0 = now_ns(); sock.sendall(REQ.pack(0, svc)); wait_reply(); t = now_ns()
    delta, expiry = t - t0, t + ttl            # XFetch stores the measured recompute time with the value
    start = t + 5_000_000
    at, s = [], float(start)
    while s < start + duration_s * 1e9:
        s += rng.expovariate(rate / 1e9); at.append(int(s))
    at.pop()
    n = len(at)
    began, lat, lag = [0] * n, [0] * n, [0] * n
    waited = [False] * n
    inflight = {}                              # recompute id -> [sent_ns, reads waiting for it]
    rc_starts, rc_gap, rc_delta, rc_times = [], [], [], []   # per recompute: sent at, how early (expiry - sent), the delta XFetch used, how long it took
    peak, nxt, i, done, runaway, cancelled = 0, 1, 0, 0, None, False
    def recompute(t, k):
        nonlocal nxt, peak
        sock.sendall(REQ.pack(nxt, svc))
        inflight[nxt] = [t, [k]]; nxt += 1
        rc_starts.append(t); rc_gap.append(expiry - t); rc_delta.append(delta)
        peak = max(peak, len(inflight))
    while done < n:
        t = now_ns()
        if runaway is None and len(inflight) > RUNAWAY:
            runaway = t; n = i; sock.sendall(REQ.pack(CANCEL, 0))   # no more reads; served reads so far still count
        if i < n and t >= at[i]:
            began[i], lag[i] = t, t - at[i]
            if strategy == 'xfetch':
                # Fig. 3 of the paper: recompute if Time() - delta * beta * log(rand()) >= expiry. 1 - random() is in (0, 1].
                stale = t - delta * BETA * math.log(1.0 - rng.random()) >= expiry
            else:
                stale = t >= expiry
            if not stale:
                lat[i] = now_ns() - t; done += 1
            elif strategy == 'lock' and inflight:
                next(iter(inflight.values()))[1].append(i)
                waited[i] = True
            else:
                recompute(t, i); waited[i] = True
            i += 1
        try:
            data = sock.recv(65536)
        except BlockingIOError:
            data = b''
        if data:
            buf += data
            while len(buf) >= REP.size:
                (rid,), buf = REP.unpack_from(buf), buf[REP.size:]
                t = now_ns()
                if rid == CANCEL:      # everything still in flight was dropped by the database: those reads were never served
                    for _, readers in inflight.values():
                        for k in readers:
                            lat[k] = None
                        done += len(readers)
                    inflight.clear(); cancelled = True
                    continue
                sent, readers = inflight.pop(rid)
                delta, expiry = t - sent, t + ttl  # cache write: new value, its recompute time, a fresh TTL
                rc_times.append(delta)
                for k in readers:
                    lat[k] = t - began[k]
                done += len(readers)
    sock.setblocking(True)
    sock.sendall(REQ.pack(STATS, 0))
    server = json.loads(rfile.readline())
    end = now_ns()

    # Stampede size as defined in the paper: recomputes started within one recompute time of the first one (Z, Z + 1).
    sizes, gaps, deltas, z = [], [], [], None
    for st, gap, d in zip(rc_starts, rc_gap, rc_delta):
        if z is None or st >= z + svc:
            z = st; sizes.append(0); gaps.append(gap); deltas.append(round(d / 1e6, 1))
        sizes[-1] += 1
    ms = lambda ns: ns / 1e6
    lat, waited, lag = lat[:n], waited[:n], lag[:n]
    unserved = sum(v is None for v in lat)
    L = sorted(ms(v) for v in lat if v is not None)
    W = sorted(ms(lat[k]) for k in range(n) if waited[k] and lat[k] is not None)
    pct = lambda xs, p: xs[min(len(xs) - 1, int(p / 100 * len(xs)))] if xs else None
    r4 = lambda v: None if v is None else round(v, 4)
    elapsed = (end - start) / 1e9
    ran_s = (runaway - start) / 1e9 if runaway else duration_s
    return {'strategy': strategy, 'rate_per_s': rate, 'ttl_s': ttl_s, 'reads': n, 'elapsed_s': round(elapsed, 3),
            # Runaway: more than RUNAWAY recomputes were waiting at the database; the cell was stopped at runaway_at_s.
            'runaway_at_s': None if runaway is None else round(ran_s, 3), 'unserved_reads': unserved,
            'recomputes': len(rc_starts), 'recomputes_per_min': round(len(rc_starts) / (ran_s / 60), 2),
            'stampedes': len(sizes), 'stampede_mean': round(statistics.fmean(sizes), 3), 'stampede_max': max(sizes),
            'stampede_sizes': sizes, 'stampede_delta_ms': deltas,   # delta = the last measured recompute time, when each stampede began
            # How early each stampede started, before the value would have expired (negative: after it had expired).
            'early_gap_mean_ms': round(ms(statistics.fmean(gaps)), 2), 'early_gap_min_ms': round(ms(min(gaps)), 2), 'early_gap_max_ms': round(ms(max(gaps)), 2),
            'predicted_gap_ms': round(RECOMPUTE_MS * BETA * math.log(rate * RECOMPUTE_MS / 1000), 2) if strategy == 'xfetch' else None,
            'peak_inflight': peak, 'db_busy_share': round(server['busy_ns'] / 1e9 / elapsed, 4),
            'recompute_time_mean_ms': round(ms(statistics.fmean(rc_times)), 3), 'recompute_time_max_ms': round(ms(max(rc_times)), 3),
            'waited_share': round(len(W) / (n - unserved), 5), 'waited_reads': len(W),
            'read_mean_ms': round(statistics.fmean(L), 4), 'read_p50_ms': r4(pct(L, 50)), 'read_p99_ms': r4(pct(L, 99)), 'read_p999_ms': r4(pct(L, 99.9)), 'read_max_ms': r4(L[-1]),
            'waited_p50_ms': r4(pct(W, 50)), 'waited_max_ms': r4(W[-1] if W else None),
            'read_lag_p99_ms': round(ms(sorted(lag)[int(0.99 * n)]), 4), 'read_lag_max_ms': round(ms(max(lag)), 4),
            'db_overrun_p99_ms': round(ms(sorted(server['overrun_ns'])[int(0.99 * len(server['overrun_ns']))]), 4)}

if __name__ == '__main__':
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    if len(sys.argv) > 2:                      # smoke test: python stampede_lab.py <seed> <seconds>, not written to disk
        DURATION_S = {ttl: max(float(sys.argv[2]), 2 * ttl) for ttl in TTLS}
    R = {'python': platform.python_version(), 'machine': platform.processor() or platform.machine(), 'os': platform.platform(),
         'cpus': os.cpu_count(), 'server_cpu': SERVER_CPU, 'client_cpu': CLIENT_CPU, 'seed': seed,
         'recompute_ms': RECOMPUTE_MS, 'beta': BETA, 'duration_s': {str(k): v for k, v in DURATION_S.items()}, 'runaway_limit': RUNAWAY, 'results': []}
    dedicate(CLIENT_CPU)
    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=server_process, args=(q,), daemon=True); p.start()
    sock = socket.create_connection(('127.0.0.1', q.get()))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    rfile = sock.makefile('rb')
    for ttl in TTLS:
        for strategy in STRATEGIES:
            for rate in RATES:
                r = trial(sock, rfile, strategy, rate, ttl, DURATION_S[ttl], random.Random(f'{seed}-{ttl}-{strategy}-{rate}'))
                R['results'].append(r)
                print(ttl, strategy, rate, {k: v for k, v in r.items() if k not in ('strategy', 'rate_per_s', 'ttl_s', 'stampede_sizes', 'stampede_delta_ms')}, flush=True)
    sock.close(); p.join(5)
    if len(sys.argv) <= 2:
        with open(os.path.join(HERE, 'results.json'), 'w') as fh:
            json.dump(R, fh, indent=1)
