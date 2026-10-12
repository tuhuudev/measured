// Small dependency-free SVG charts: a log-scale dumbbell (slow plan vs fast plan) and a single-series bar chart.
window.Charts = (function () {
  const NS = 'http://www.w3.org/2000/svg';
  function el(name, attrs, parent) {
    const e = document.createElementNS(NS, name);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function fmt(ms) {
    if (ms >= 1000) return Math.round(ms).toLocaleString('en-US') + ' ms';
    if (ms >= 10) return (Math.round(ms * 10) / 10) + ' ms';
    if (ms >= 1) return (Math.round(ms * 100) / 100) + ' ms';
    return ms + ' ms';
  }
  function tip(box) {
    const t = box.querySelector('.tip');
    return {
      show(html, evt) {
        t.innerHTML = html;
        const r = box.getBoundingClientRect();
        const x = Math.min(evt.clientX - r.left + 12, r.width - t.offsetWidth - 4);
        t.style.left = Math.max(4, x) + 'px';
        t.style.top = (evt.clientY - r.top + 14) + 'px';
        t.style.opacity = 1;
      },
      hide() { t.style.opacity = 0; },
    };
  }
  function esc(s) { return String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }
  function hover(target, box, html) {
    const tt = tip(box);
    target.addEventListener('pointerenter', (e) => tt.show(html, e));
    target.addEventListener('pointermove', (e) => tt.show(html, e));
    target.addEventListener('pointerleave', () => tt.hide());
  }

  function dumbbell(box, rows) {
    const svg = box.querySelector('svg');
    const W = Math.max(320, box.clientWidth - 24), rowH = 54, top = 10, left = 72, right = 24, axisH = 28;
    const H = top + rows.length * rowH + axisH;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const lo = -3, hi = 3; // 0.001 ms .. 1000 ms
    const x = (v) => left + (Math.log10(v) - lo) / (hi - lo) * (W - left - right);
    for (let p = lo; p <= hi; p++) {
      el('line', { x1: x(10 ** p), x2: x(10 ** p), y1: top, y2: H - axisH + 4, class: 'grid' }, svg);
      if (W < 480 && (p - lo) % 2) continue; // narrow screens: label every other gridline
      const t = el('text', { x: x(10 ** p), y: H - 8, 'text-anchor': 'middle' }, svg);
      t.textContent = p < 0 ? (10 ** p).toFixed(-p) + ' ms' : (10 ** p).toLocaleString('en-US') + ' ms';
    }
    rows.forEach((r, i) => {
      const y = top + i * rowH + 36;
      const q = el('text', { x: 4, y: y - 16, class: 'lbl' }, svg);
      q.textContent = r.q;
      el('line', { x1: x(r.fast), x2: x(r.slow), y1: y, y2: y, stroke: 'var(--ink-3)', 'stroke-width': 2 }, svg);
      [['slow', 'var(--scan)', 'start', 8], ['fast', 'var(--search)', 'end', -8]].forEach(([k, color, anchor, dx]) => {
        el('circle', { cx: x(r[k]), cy: y, r: 6, fill: color, stroke: 'var(--surface)', 'stroke-width': 2 }, svg);
        const lab = el('text', { x: x(r[k]) + dx, y: y + 4, 'text-anchor': anchor }, svg);
        lab.textContent = fmt(r[k]);
        // keep the label inside the plot: flip it above the dot if it would run off either edge
        const bb = lab.getBBox();
        if (bb.x + bb.width > W - 2 || bb.x < 2) { lab.setAttribute('x', x(r[k])); lab.setAttribute('y', y - 10); lab.setAttribute('text-anchor', 'middle'); }
        const hit = el('circle', { cx: x(r[k]), cy: y, r: 16, fill: 'transparent' }, svg);
        hover(hit, box, `<b>${esc(r.q)}</b><br>${fmt(r[k])}<br>${esc(r[k + 'Plan'])}`);
      });
    });
  }

  // opts.note: text after the value in the tooltip; opts.fmt: value formatter; d.color: bar colour (default blue).
  function bars(box, data, opts = {}) {
    const svg = box.querySelector('svg');
    svg.textContent = '';
    const show = opts.fmt || ((v) => v.toLocaleString('en-US') + ' ms');
    const W = Math.max(270, box.clientWidth - 24), barH = 26, gap = 18, left = W < 400 ? 96 : W < 480 ? 120 : 150, right = W < 400 ? 72 : 90, top = 6;
    const H = top + data.length * (barH + gap);
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const max = Math.max(...data.map((d) => d.v));
    data.forEach((d, i) => {
      const y = top + i * (barH + gap);
      const w = Math.max(2, d.v / max * (W - left - right));
      const lab = el('text', { x: left - 10, y: y + barH / 2 + 4, 'text-anchor': 'end', class: 'lbl' }, svg);
      lab.textContent = d.label;
      // flat at the baseline, 4px rounded at the data end (a plain sliver when the bar is too short to round)
      const fill = d.color || 'var(--search)';
      if (w > 8) el('path', { d: `M${left} ${y}H${left + w - 4}a4 4 0 0 1 4 4v${barH - 8}a4 4 0 0 1 -4 4H${left}Z`, fill }, svg);
      else el('rect', { x: left, y, width: w, height: barH, fill }, svg);
      const v = el('text', { x: left + w + 8, y: y + barH / 2 + 4 }, svg);
      v.textContent = show(d.v);
      const hit = el('rect', { x: 0, y: y - gap / 2, width: W, height: barH + gap, fill: 'transparent' }, svg);
      hover(hit, box, `<b>${esc(d.label)}</b><br>${esc(show(d.v))}${opts.note ? ' ' + esc(opts.note) : ''}`);
    });
  }

  // Requests per time bucket. opts: bucketMs, untilMs, yMax (shared across small multiples), color, label (tooltip unit),
  // clipFirst (the first bucket may exceed yMax: it is drawn full height and labelled with its value).
  function timeline(box, values, opts) {
    const svg = box.querySelector('svg');
    svg.textContent = '';
    const W = Math.max(270, box.clientWidth - 24), H = 110, top = 8, bottom = 22, left = 4, right = 4;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const n = Math.ceil(opts.untilMs / opts.bucketMs);
    const bw = (W - left - right) / n, ph = H - top - bottom;
    el('line', { x1: left, x2: W - right, y1: top + ph, y2: top + ph, class: 'grid' }, svg);
    const step = opts.untilMs <= 1000 ? 250 : 1000;
    for (let t = 0; t <= opts.untilMs; t += step) {
      const x = left + (t / opts.bucketMs) * bw;
      const lab = el('text', { x: t === 0 ? left : Math.min(x, W - 22), y: H - 6, 'text-anchor': t === 0 ? 'start' : 'middle' }, svg);
      lab.textContent = t >= 1000 ? t / 1000 + ' s' : t + ' ms';
    }
    for (let i = 0; i < n; i++) {
      const v = values[i] || 0;
      if (!v) continue;
      const clipped = opts.clipFirst && i === 0 && v > opts.yMax;
      const h = clipped ? ph : Math.max(1, v / opts.yMax * ph);
      // 1px surface gap between adjacent columns
      el('rect', { x: left + i * bw, y: top + ph - h, width: Math.max(1, bw - 1), height: h, fill: opts.color }, svg);
      if (clipped) {
        el('rect', { x: left, y: top + 10, width: Math.max(1, bw - 1), height: 3, fill: 'var(--surface)' }, svg);  // break mark
        const t = el('text', { x: W - right, y: top + 12, 'text-anchor': 'end' }, svg);
        t.textContent = `first ${opts.bucketMs} ms: ${v.toLocaleString('en-US')} (off scale)`;
      }
      const hit = el('rect', { x: left + i * bw, y: top, width: Math.max(4, bw), height: ph, fill: 'transparent' }, svg);
      const t0 = i * opts.bucketMs;
      hover(hit, box, `${t0}–${t0 + opts.bucketMs} ms<br><b>${v}</b> ${esc(opts.label || 'requests')}`);
    }
  }

  return { dumbbell, bars, timeline };
})();
