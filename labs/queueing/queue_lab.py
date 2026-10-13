# Queues, measured: every number in the article comes from one run of this script.
#   python labs/queueing/queue_lab.py [seed]      (writes results.json next to this file; about 25 minutes)
# A real TCP server in its own process on localhost serves requests one at a time, first come first served. Each
# request says how long it takes to serve; the server busy-waits exactly that long. A client sends requests at random
# (Poisson) times at a chosen load and measures how long each one takes. Service times are either random
# (exponential, mean 10 ms) or constant (10 ms). Theory for comparison: M/M/1 and M/D/1 queues.
import gc, json, math, multiprocessing, os, platform, random, socket, statistics, struct, sys, time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE_MS = 10.0   # 1 ms was tried first: ~50 us of per-request overhead and occasional OS stalls of 5-10 ms distorted it near full load
LOADS = [0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95]
N, WARMUP = 3_000, 300
SERVER_CPU, CLIENT_CPU = 2, 4   # logical CPUs on different physical cores of the lab machine (4 cores, 8 threads)
REQ, REP = struct.Struct('<IQ'), struct.Struct('<I')     # request: id, service in ns; reply: id
STATS = 0xFFFFFFFF
now_ns = time.perf_counter_ns

def dedicate(cpu):
    # Both sides busy-poll. A first version without this saw the client stall for up to 46 ms (the OS scheduling something
    # else on its core), sending late requests in a burst. Give each process its own core, high priority, and no GC pauses.
    gc.disable()
    if sys.platform == 'win32':
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetCurrentProcess()
        k.SetPriorityClass(h, 0x80)              # HIGH_PRIORITY_CLASS
        k.SetProcessAffinityMask(h, 1 << cpu)
    elif hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, {cpu})

# ---- server process: one worker, FIFO, single thread polling a non-blocking socket ----------------------------------
def server_process(port_q):
    dedicate(SERVER_CPU)
    ls = socket.create_server(('127.0.0.1', 0))
    port_q.put(ls.getsockname()[1])
    conn, _ = ls.accept()
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    conn.setblocking(False)
    buf, queue, busy = b'', deque(), None
    def reset():
        return {'sojourn_ns': [], 'overrun_ns': [], 'service_ns': [], 'busy_ns': 0, 'area': 0, 'n': 0, 'last': None, 'first': None, 'end': None}
    st = reset()
    def step_n(t, d):   # time-average of the number of requests in the server (queued + in service)
        if st['last'] is not None:
            st['area'] += st['n'] * (t - st['last'])
        st['last'], st['n'] = t, st['n'] + d
    while True:
        t = now_ns()
        if busy and t >= busy[2]:
            rid, arrived, deadline, svc, started = busy
            conn.sendall(REP.pack(rid))
            t = now_ns()
            # Actual time the worker spent on this request: the requested service plus noticing the deadline and replying.
            st['sojourn_ns'].append(t - arrived); st['overrun_ns'].append(t - deadline)
            st['service_ns'].append(t - started); st['busy_ns'] += t - started
            step_n(t, -1); st['end'] = t
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
                    total = st['end'] - st['first']
                    out = {'sojourn_ns': st['sojourn_ns'], 'overrun_ns': st['overrun_ns'], 'service_ns': st['service_ns'],
                           'utilisation': st['busy_ns'] / total, 'mean_in_system': st['area'] / total,
                           'arrival_rate_per_ms': len(st['sojourn_ns']) / (total / 1e6)}
                    conn.setblocking(True); conn.sendall((json.dumps(out) + '\n').encode()); conn.setblocking(False)
                    st = reset()
                    continue
                ta = now_ns()
                if st['first'] is None:
                    st['first'] = ta
                step_n(ta, +1)
                queue.append((rid, ta, svc))
        if busy is None and queue:
            rid, arrived, svc = queue.popleft()
            t = now_ns()
            busy = (rid, arrived, t + svc, svc, t)

# ---- client: Poisson arrivals, single thread polling ------------------------------------------------------------
def send_all(sock, rfile, lam_per_ns, svcs, rng):
    # Send len(svcs) requests at Poisson times (rate lam_per_ns), collect replies, then fetch the server's view.
    n = len(svcs)
    t0, at = now_ns() + 5_000_000, []
    s = t0
    for _ in range(n):
        s += rng.expovariate(lam_per_ns); at.append(int(s))
    sent, got, lag = [0] * n, [0] * n, [0] * n
    i, done, buf = 0, 0, b''
    sock.setblocking(False)
    while done < n:
        t = now_ns()
        if i < n and t >= at[i]:
            sock.sendall(REQ.pack(i, svcs[i]))
            sent[i], lag[i] = t, t - at[i]
            i += 1
        try:
            data = sock.recv(65536)
        except BlockingIOError:
            data = b''
        if data:
            t = now_ns(); buf += data
            while len(buf) >= REP.size:
                (rid,), buf = REP.unpack_from(buf), buf[REP.size:]
                got[rid] = t; done += 1
    sock.setblocking(True)
    sock.sendall(REQ.pack(STATS, 0))
    return sent, got, lag, json.loads(rfile.readline())

def trial(sock, rfile, load, dist, rng):
    mean_ns = SERVICE_MS * 1e6
    draw = lambda n: [int(rng.expovariate(1 / mean_ns)) if dist == 'exponential' else int(mean_ns) for _ in range(n)]
    svcs = draw(N)
    sent, got, lag, server = send_all(sock, rfile, load / mean_ns, svcs, rng)
    ms = lambda ns: ns / 1e6
    lat = sorted(ms(got[k] - sent[k]) for k in range(WARMUP, N))
    soj = sorted(ms(v) for v in server['sojourn_ns'][WARMUP:])
    pct = lambda xs, p: xs[min(len(xs) - 1, int(p / 100 * len(xs)))]
    S, rho = SERVICE_MS, server['utilisation']
    # Textbook theory: 10 ms mean service at exactly the target load.
    if dist == 'exponential':
        theory_mean, theory_p99 = S / (1 - load), math.log(100) * S / (1 - load)   # M/M/1: time in system ~ Exp(mu - lambda)
    else:
        theory_mean, theory_p99 = S + load * S / (2 * (1 - load)), None            # M/D/1
    # Pollaczek-Khinchine mean for M/G/1, W = E[S] + lam E[S^2] / (2 (1 - lam E[S])), with the measured arrival rate
    # and the measured (actual) service times, overhead included.
    act = [ms(v) for v in server['service_ns']]
    lam = server['arrival_rate_per_ms']
    es, es2 = statistics.fmean(act), statistics.fmean(x * x for x in act)
    pk_mean = es + lam * es2 / (2 * (1 - lam * es))
    # Replay: an ideal FIFO server (no overhead, no stalls) fed the same send times and the same requested service times.
    dep, rep = 0, []
    for k in range(N):
        dep = max(sent[k], dep) + svcs[k]
        if k >= WARMUP:
            rep.append(ms(dep - sent[k]))
    rep.sort()
    lags = sorted(ms(v) for v in lag)
    over = sorted(ms(v) for v in server['overrun_ns'])
    w_all = statistics.fmean(ms(v) for v in server['sojourn_ns'])
    return {'load': load, 'measured_utilisation': round(rho, 4),
            'server_mean_ms': round(statistics.fmean(soj), 4), 'server_p50_ms': round(pct(soj, 50), 4), 'server_p99_ms': round(pct(soj, 99), 4),
            'client_mean_ms': round(statistics.fmean(lat), 4), 'client_p50_ms': round(pct(lat, 50), 4), 'client_p99_ms': round(pct(lat, 99), 4),
            'theory_mean_ms': round(theory_mean, 4), 'theory_p99_ms': None if theory_p99 is None else round(theory_p99, 4),
            'actual_service_mean_ms': round(es, 4), 'requested_service_mean_ms': round(statistics.fmean(svcs) / 1e6, 4), 'pk_mean_ms': round(pk_mean, 4),
            'replay_mean_ms': round(statistics.fmean(rep), 4), 'replay_p50_ms': round(pct(rep, 50), 4), 'replay_p99_ms': round(pct(rep, 99), 4),
            'mean_in_system': round(server['mean_in_system'], 3),
            'little_lambda_w': round(server['arrival_rate_per_ms'] * w_all, 3),
            'send_lag_p99_ms': round(pct(lags, 99), 4), 'send_lag_max_ms': round(lags[-1], 4),
            'service_overrun_p99_ms': round(pct(over, 99), 4)}

if __name__ == '__main__':
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    R = {'python': platform.python_version(), 'machine': platform.processor() or platform.machine(), 'os': platform.platform(),
         'cpus': os.cpu_count(), 'server_cpu': SERVER_CPU, 'client_cpu': CLIENT_CPU, 'seed': seed, 'service_ms': SERVICE_MS, 'requests_per_load': N, 'warmup_dropped': WARMUP}
    dedicate(CLIENT_CPU)
    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=server_process, args=(q,), daemon=True); p.start()
    sock = socket.create_connection(('127.0.0.1', q.get()))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    rfile = sock.makefile('rb')
    for dist in ('exponential', 'constant'):
        rng = random.Random(f'{seed}-{dist}')
        R[dist] = []
        for load in LOADS:
            r = trial(sock, rfile, load, dist, rng)
            R[dist].append(r)
            print(dist, load, {k: r[k] for k in ('measured_utilisation', 'actual_service_mean_ms', 'client_mean_ms', 'replay_mean_ms', 'theory_mean_ms', 'pk_mean_ms', 'client_p99_ms', 'replay_p99_ms', 'theory_p99_ms', 'mean_in_system', 'little_lambda_w', 'send_lag_p99_ms', 'service_overrun_p99_ms')}, flush=True)
    sock.close(); p.join(5)
    out = os.path.join(HERE, 'results.json')
    with open(out, 'w') as fh:
        json.dump(R, fh, indent=1)
