// Discrete-event simulation of the retry lab: a server with `capacity` slots, `serviceMs` per request, that answers
// "busy" at once when full; `clients` clients all send at t = 0 and retry on "busy" with one of three policies.
// Seeded, so the same inputs always give the same result. Used by the page; runs in Node for testing too.
(function (root) {
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Min-heap of events ordered by time, then kind (slots free up before new arrivals), then insertion order.
  const KIND = { finish: 0, arrive: 1, reply: 2, send: 3 };
  function Heap() { this.a = []; this.seq = 0; }
  Heap.prototype.less = function (x, y) { return x.t !== y.t ? x.t < y.t : x.k !== y.k ? x.k < y.k : x.s < y.s; };
  Heap.prototype.push = function (t, kind, c, ok) {
    const a = this.a; a.push({ t, k: KIND[kind], kind, c, ok, s: this.seq++ });
    let i = a.length - 1;
    while (i > 0) { const p = (i - 1) >> 1; if (!this.less(a[i], a[p])) break; [a[i], a[p]] = [a[p], a[i]]; i = p; }
  };
  Heap.prototype.pop = function () {
    const a = this.a, top = a[0], last = a.pop();
    if (a.length) {
      a[0] = last; let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1; let m = i;
        if (l < a.length && this.less(a[l], a[m])) m = l;
        if (r < a.length && this.less(a[r], a[m])) m = r;
        if (m === i) break; [a[i], a[m]] = [a[m], a[i]]; i = m;
      }
    }
    return top;
  };

  function simulate(o) {
    const rnd = mulberry32(o.seed || 1);
    const half = o.rttMs / 2;
    const attempts = new Array(o.clients).fill(0);
    const arrivals = [], successes = [];
    let inFlight = 0, failed = 0;
    const h = new Heap();
    for (let c = 0; c < o.clients; c++) h.push(0, 'send', c);
    while (h.a.length) {
      const e = h.pop();
      if (e.kind === 'send') h.push(e.t + half, 'arrive', e.c);
      else if (e.kind === 'arrive') {
        arrivals.push(e.t);
        if (inFlight < o.capacity) { inFlight++; h.push(e.t + o.serviceMs, 'finish', e.c); }
        else h.push(e.t + half, 'reply', e.c, false);
      } else if (e.kind === 'finish') { inFlight--; h.push(e.t + half, 'reply', e.c, true); }
      else if (e.ok) successes.push(e.t);
      else {
        const n = attempts[e.c]++;              // n-th failure, from 0
        if (n + 1 >= o.maxAttempts) { failed++; continue; }
        const ceiling = Math.min(o.capMs, o.baseMs * Math.pow(2, n));
        const wait = o.policy === 'immediate' ? 0 : o.policy === 'backoff' ? ceiling : rnd() * ceiling;
        h.push(e.t + wait, 'send', e.c);
      }
    }
    successes.sort((x, y) => x - y);
    return {
      requests: arrivals.length,
      failed,
      lastSuccessMs: successes.length ? successes[successes.length - 1] : null,
      medianSuccessMs: successes.length ? successes[Math.floor((successes.length - 1) / 2)] : null,
      arrivals,
    };
  }

  const api = { simulate };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.RetrySim = api;
})(this);
