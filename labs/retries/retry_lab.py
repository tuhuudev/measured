# Retries, measured: every number in the article comes from one run of this script.
#   python labs/retries/retry_lab.py        (writes results.json next to this file; standard library only)
# A real asyncio TCP server, in its own process on localhost, serves at most CAPACITY requests at once (each takes
# SERVICE_MS) and answers "busy" straight away when it is full, like an HTTP 503. CLIENTS clients all send one
# request at the same moment (a thundering herd) and retry on "busy", up to MAX_ATTEMPTS attempts, with one of
# three policies:
#   immediate   - retry at once;
#   backoff     - capped exponential backoff: wait min(CAP, BASE * 2**n) after the n-th failure (n from 0);
#   jitter      - "full jitter": wait random(0, min(CAP, BASE * 2**n))   (AWS Architecture Blog).
import asyncio, json, multiprocessing, os, platform, random, statistics, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENTS, CAPACITY, SERVICE_MS = 200, 20, 20
BASE_MS, CAP_MS, MAX_ATTEMPTS = 10, 1000, 10
TRIALS, BUCKET_MS = 7, 50   # 50 ms buckets: the Python client loop batches sends within a few ms
POLICIES = ['immediate', 'backoff', 'jitter']

def fine_timer(on):
    # Windows rounds sleeps up to its ~15.6 ms timer tick by default (a 20 ms sleep took ~32 ms), which bunches
    # waits together. Ask for a 1 ms timer while the lab runs.
    if sys.platform == 'win32':
        import ctypes
        (ctypes.windll.winmm.timeBeginPeriod if on else ctypes.windll.winmm.timeEndPeriod)(1)

def loop_policy():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ---- server process -------------------------------------------------------------------------------------------
def server_process(port_q):
    fine_timer(True); loop_policy()
    arrivals = []          # wall-clock time of every request (time.time(), comparable across processes)
    in_flight = 0

    async def handle(reader, writer):
        nonlocal in_flight
        while line := await reader.readline():
            if line == b'stats\n':               # control message from the lab after a trial
                writer.write((json.dumps(arrivals) + '\n').encode()); await writer.drain()
                continue
            arrivals.append(time.time())
            if in_flight >= CAPACITY:
                writer.write(b'busy\n')
            else:
                in_flight += 1
                await asyncio.sleep(SERVICE_MS / 1000)
                in_flight -= 1
                writer.write(b'ok\n')
            await writer.drain()
        writer.close()

    async def main():
        server = await asyncio.start_server(handle, '127.0.0.1', 0, backlog=CLIENTS + 10)
        port_q.put(server.sockets[0].getsockname()[1])
        await server.serve_forever()
    asyncio.run(main())

# ---- clients (this process) -----------------------------------------------------------------------------------
def wait_ms(policy, n, rng):
    if policy == 'immediate':
        return 0
    ceiling = min(CAP_MS, BASE_MS * 2 ** n)
    return ceiling if policy == 'backoff' else rng.uniform(0, ceiling)

async def trial(policy, seed, port):
    rng = random.Random(seed)
    conns = [await asyncio.open_connection('127.0.0.1', port) for _ in range(CLIENTS)]
    start = asyncio.Event()
    t0 = None

    async def client(reader, writer):
        await start.wait()
        for n in range(MAX_ATTEMPTS):
            writer.write(b'req\n'); await writer.drain()
            if (await reader.readline()) == b'ok\n':
                return (time.time() - t0) * 1000
            if n + 1 < MAX_ATTEMPTS:
                await asyncio.sleep(wait_ms(policy, n, rng) / 1000)
        return None

    tasks = [asyncio.create_task(client(r, w)) for r, w in conns]
    await asyncio.sleep(0.05)              # let every client reach start.wait()
    t0 = time.time()
    start.set()
    done = await asyncio.gather(*tasks)
    r, w = conns[0]
    w.write(b'stats\n'); await w.drain()
    arrivals = [(a - t0) * 1000 for a in json.loads(await r.readline())]
    for _, w in conns:
        w.close()

    ok = [t for t in done if t is not None]
    return {
        'requests': len(arrivals),
        'succeeded': len(ok),
        'failed': CLIENTS - len(ok),
        'rejected': len(arrivals) - len(ok),
        'last_success_ms': round(max(ok), 1) if ok else None,
        'median_success_ms': round(statistics.median(ok), 1) if ok else None,
        'arrivals': arrivals,
    }

def run_trial(policy, seed):
    port_q = multiprocessing.Queue()
    proc = multiprocessing.Process(target=server_process, args=(port_q,), daemon=True)
    proc.start()
    try:
        return asyncio.run(trial(policy, seed, port_q.get(timeout=30)))
    finally:
        proc.terminate(); proc.join()

def histogram(arrivals, until_ms):
    buckets = [0] * (int(until_ms // BUCKET_MS) + 1)
    for a in arrivals:
        if 0 <= a < until_ms:
            buckets[int(a // BUCKET_MS)] += 1
    return buckets

def main():
    R = {'python': platform.python_version(), 'machine': platform.processor() or platform.machine(),
         'os': platform.platform(), 'clients': CLIENTS, 'capacity': CAPACITY, 'service_ms': SERVICE_MS,
         'base_ms': BASE_MS, 'cap_ms': CAP_MS, 'max_attempts': MAX_ATTEMPTS, 'trials': TRIALS,
         'bucket_ms': BUCKET_MS, 'ideal_ms': CLIENTS / CAPACITY * SERVICE_MS, 'policies': {}}
    for policy in POLICIES:
        runs = [run_trial(policy, seed) for seed in range(TRIALS)]
        mid = sorted(runs, key=lambda r: r['requests'])[TRIALS // 2]   # the median trial, by request count
        def med(k):
            vals = [r[k] for r in runs if r[k] is not None]
            return statistics.median(vals) if vals else None
        R['policies'][policy] = {
            'requests_median': med('requests'), 'requests_min': min(r['requests'] for r in runs), 'requests_max': max(r['requests'] for r in runs),
            'failed_median': med('failed'), 'failed_max': max(r['failed'] for r in runs),
            'rejected_median': med('rejected'),
            'last_success_ms_median': med('last_success_ms'),
            'median_success_ms_median': med('median_success_ms'),
            'timeline_trial': {k: v for k, v in mid.items() if k != 'arrivals'},
            'timeline': histogram(mid['arrivals'], 4000),
        }
        print(policy, {k: v for k, v in R['policies'][policy].items() if k not in ('timeline', 'timeline_trial')}, file=sys.stderr)
    with open(os.path.join(HERE, 'results.json'), 'w') as fh:
        json.dump(R, fh, indent=1)

if __name__ == '__main__':
    fine_timer(True); loop_policy()
    try:
        main()
    finally:
        fine_timer(False)
