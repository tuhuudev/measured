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

  function bars(box, data) {
    const svg = box.querySelector('svg');
    const W = Math.max(320, box.clientWidth - 24), barH = 26, gap = 18, left = W < 480 ? 120 : 150, right = 70, top = 6;
    const H = top + data.length * (barH + gap);
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const max = Math.max(...data.map((d) => d.v));
    data.forEach((d, i) => {
      const y = top + i * (barH + gap);
      const w = d.v / max * (W - left - right);
      const lab = el('text', { x: left - 10, y: y + barH / 2 + 4, 'text-anchor': 'end', class: 'lbl' }, svg);
      lab.textContent = d.label;
      // flat at the baseline, 4px rounded at the data end
      el('path', { d: `M${left} ${y}H${left + w - 4}a4 4 0 0 1 4 4v${barH - 8}a4 4 0 0 1 -4 4H${left}Z`, fill: 'var(--search)' }, svg);
      const v = el('text', { x: left + w + 8, y: y + barH / 2 + 4 }, svg);
      v.textContent = d.v.toLocaleString('en-US') + ' ms';
      const hit = el('rect', { x: 0, y: y - gap / 2, width: W, height: barH + gap, fill: 'transparent' }, svg);
      hover(hit, box, `<b>${esc(d.label)}</b><br>${d.v.toLocaleString('en-US')} ms for 200,000 inserts`);
    });
  }

  return { dumbbell, bars };
})();
