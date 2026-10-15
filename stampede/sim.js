// Simulation of the stampede lab: one hot value behind a cache with a TTL, Poisson reads, and a database that
// recomputes the value one request at a time (FIFO), each recompute taking `recomputeMs`. Strategies: 'plain' (every
// read that sees the value expired recomputes), 'lock' (only the first does, the others wait for it) and 'xfetch'
// (Vattani et al. 2015, Fig. 3: recompute if now - delta * beta * ln(rand) >= expiry). No network, no overhead.
// Like the lab, it stops when more than `runaway` recomputes are waiting at the database.
// Seeded, so the same inputs always give the same result. Runs in Node for testing too.
(function (root) {
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const expo = (rnd, mean) => -Math.log(1 - rnd()) * mean;
  const pct = (sorted, p) => sorted[Math.min(sorted.length - 1, Math.floor(p / 100 * sorted.length))];

  function simulate({ strategy = 'plain', rate = 1000, beta = 1, recomputeMs = 100, ttlMs = 2000, durationMs = 600000, runaway = 1000, seed = 1 }) {
    const rnd = mulberry32(seed);
    // The cache starts warm: a value computed at time 0, as in the lab.
    let delta = recomputeMs, expiry = ttlMs, dbFree = 0;
    const pending = [];          // [sent, done] of recomputes not yet written to the cache, in done order (FIFO database)
    const lat = [], starts = [];
    let waited = 0, maxWait = 0, runawayAt = null;
    const mean = 1000 / rate;
    for (let t = expo(rnd, mean); t < durationMs; t += expo(rnd, mean)) {
      while (pending.length && pending[0][1] <= t) {   // cache writes that happened before this read
        const [sent, done] = pending.shift();
        delta = done - sent; expiry = done + ttlMs;
      }
      if (pending.length > runaway) { runawayAt = t; break; }
      const stale = strategy === 'xfetch'
        ? t - delta * beta * Math.log(1 - rnd()) >= expiry
        : t >= expiry;
      let l = 0;
      if (stale) {
        if (strategy === 'lock' && pending.length) {
          l = pending[0][1] - t;
        } else {
          const done = Math.max(t, dbFree) + recomputeMs;
          dbFree = done; pending.push([t, done]); starts.push(t);
          l = done - t;
        }
        waited++; maxWait = Math.max(maxWait, l);
      }
      lat.push(l);
    }
    // Stampede size as in the paper: recomputes started within one recompute time of the first one.
    const sizes = [];
    let z = -Infinity;
    for (const s of starts) {
      if (s >= z + recomputeMs) { z = s; sizes.push(0); }
      sizes[sizes.length - 1]++;
    }
    const sorted = Float64Array.from(lat).sort();
    return {
      runawayAt, deltaAtEnd: delta,
      reads: lat.length, recomputes: starts.length, recomputesPerMin: starts.length / ((runawayAt ?? durationMs) / 60000),
      stampedeMean: sizes.length ? sizes.reduce((a, b) => a + b, 0) / sizes.length : 0, stampedeMax: sizes.length ? Math.max(...sizes) : 0,
      waitedShare: waited / lat.length, maxWait,
      p99: pct(sorted, 99), p999: pct(sorted, 99.9), mean: lat.reduce((a, b) => a + b, 0) / lat.length,
    };
  }

  const api = { simulate };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.StampedeSim = api;
})(this);
