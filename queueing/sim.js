// Simulation of the queueing lab: one FIFO server, Poisson arrivals at `load`, service times exponential or constant
// with mean `serviceMs`. Uses Lindley's recursion (each request starts when it arrives or when the previous one
// finishes, whichever is later). Seeded, so the same inputs always give the same result. Runs in Node for testing too.
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

  // Returns mean/p50/p99 time in system (ms) over `requests`, plus the mean of each consecutive `window` of requests.
  function simulate({ load, serviceMs = 10, dist = 'exponential', requests = 200000, window = 3000, seed = 1 }) {
    const rnd = mulberry32(seed);
    const times = new Float64Array(requests);
    let arrive = 0, done = 0;
    for (let i = 0; i < requests; i++) {
      arrive += expo(rnd, serviceMs / load);
      const s = dist === 'exponential' ? expo(rnd, serviceMs) : serviceMs;
      done = Math.max(arrive, done) + s;
      times[i] = done - arrive;
    }
    const windows = [];
    for (let w = 0; w + window <= requests; w += window) {
      let sum = 0;
      for (let i = w; i < w + window; i++) sum += times[i];
      windows.push(sum / window);
    }
    let sum = 0;
    for (let i = 0; i < requests; i++) sum += times[i];
    const sorted = Float64Array.from(times).sort();
    return { mean: sum / requests, p50: pct(sorted, 50), p99: pct(sorted, 99), windowMin: Math.min(...windows), windowMax: Math.max(...windows), windows: windows.length };
  }

  // Textbook mean time in system: M/M/1 T = S / (1 - rho); M/D/1 T = S + rho S / (2 (1 - rho)).
  function theoryMean(load, serviceMs, dist) {
    return dist === 'exponential' ? serviceMs / (1 - load) : serviceMs + load * serviceMs / (2 * (1 - load));
  }

  const api = { simulate, theoryMean };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.QueueSim = api;
})(this);
