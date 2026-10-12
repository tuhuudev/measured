// In-browser SQLite (sql.js) playground: build a synthetic users table, toggle indexes, read the plan, time the query.
(function () {
  const root = document.getElementById('pg');
  if (!root) return;
  const $ = (sel) => root.querySelector(sel);
  const ROWS = Number(root.dataset.rows || 100000);
  const INDEXES = {
    idx_email: 'CREATE INDEX idx_email ON users(email)',
    idx_lower_email: 'CREATE INDEX idx_lower_email ON users(lower(email))',
    idx_last_first: 'CREATE INDEX idx_last_first ON users(last_name, first_name)',
  };
  const target = Math.floor(ROWS * 0.777);
  const PRESETS = [
    ['Find one email', `SELECT id FROM users WHERE email = 'user${target}@example.com'`],
    ['First 10 emails in order', 'SELECT email FROM users ORDER BY email LIMIT 10'],
    ['Range of emails', "SELECT count(*) FROM users WHERE email BETWEEN 'user5' AND 'user6'"],
    ['Email ends with…', "SELECT id FROM users WHERE email LIKE '%777@example.com'"],
    ['Lowercased email', `SELECT id FROM users WHERE lower(email) = 'user${target}@example.com'`],
    ['Last name + first name', "SELECT id FROM users WHERE last_name = 'last777' AND first_name = 'first123'"],
    ['First name only', "SELECT id FROM users WHERE first_name = 'first123'"],
    ['A column with no index', `SELECT id FROM users WHERE name = 'name${target}'`],
  ];
  let db = null;

  const status = (msg) => { $('.status').textContent = msg; };
  const select = $('#pg-preset');
  PRESETS.forEach(([label, sql], i) => select.add(new Option(label, String(i))));
  select.addEventListener('change', () => { $('#pg-sql').value = PRESETS[Number(select.value)][1]; });
  $('#pg-sql').value = PRESETS[0][1];

  function esc(s) { return s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }

  async function build() {
    $('#pg-build').disabled = true;
    status('Loading SQLite (about 650 KB, once)…');
    const SQL = await window.initSqlJs({ locateFile: (f) => 'https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/' + f });
    status(`Inserting ${ROWS.toLocaleString('en-US')} rows…`);
    await new Promise((r) => setTimeout(r, 20));
    const t = performance.now();
    db = new SQL.Database();
    db.run('CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT, last_name TEXT, first_name TEXT)');
    db.run('BEGIN');
    const ins = db.prepare('INSERT INTO users (email, name, last_name, first_name) VALUES (?, ?, ?, ?)');
    for (let i = 0; i < ROWS; i++) ins.run([`user${i}@example.com`, `name${i}`, `last${i % 1000}`, `first${i % 997}`]);
    ins.free();
    db.run('COMMIT');
    const sqliteVersion = db.exec('SELECT sqlite_version()')[0].values[0][0];
    status(`Ready: ${ROWS.toLocaleString('en-US')} rows in ${Math.round(performance.now() - t)} ms · SQLite ${sqliteVersion} in your browser`);
    root.querySelectorAll('input[type=checkbox], #pg-run, #pg-analyze').forEach((el) => { el.disabled = false; });
  }

  function toggle(e) {
    const name = e.target.value;
    const t = performance.now();
    db.run(e.target.checked ? INDEXES[name] : `DROP INDEX ${name}`);
    status(`${e.target.checked ? 'Created' : 'Dropped'} ${name} in ${Math.round(performance.now() - t)} ms`);
  }

  function analyze() {
    db.run('ANALYZE');
    status('ANALYZE done: the planner now has statistics about each index (sqlite_stat1). Re-run your query.');
  }

  // Wall-clock per query: repeat until about 60 ms have passed, so sub-millisecond queries are measurable despite timer rounding.
  function timeIt(sql) {
    db.exec(sql);
    let n = 0;
    const t0 = performance.now();
    let el = 0;
    while (el < 60 && n < 5000) { db.exec(sql); n++; el = performance.now() - t0; }
    return { ms: el / n, n };
  }

  function fmt(ms) {
    if (ms >= 10) return ms.toFixed(0) + ' ms';
    if (ms >= 1) return ms.toFixed(1) + ' ms';
    if (ms >= 0.01) return ms.toFixed(3) + ' ms';
    return (ms * 1000).toFixed(1) + ' µs';
  }

  function run() {
    const sql = $('#pg-sql').value.trim().replace(/;+\s*$/, '');
    const out = $('.out');
    try {
      const plan = db.exec('EXPLAIN QUERY PLAN ' + sql);
      const lines = plan.length ? plan[0].values.map((r) => String(r[3])) : [];
      const { ms, n } = timeIt(sql);
      const res = db.exec(sql);
      const count = res.length ? res[0].values.length : 0;
      out.innerHTML =
        lines.map((l) => {
          const kind = /^SEARCH/.test(l) ? 'search' : /^SCAN/.test(l) ? 'scan' : '';
          return `<div class="plan">${kind ? `<span class="tag ${kind}">${kind.toUpperCase()}</span>` : ''}${esc(l)}</div>`;
        }).join('') +
        `<div class="time">${fmt(ms)} <span class="status">per query · average of ${n} runs · ${count} row${count === 1 ? '' : 's'} returned</span></div>`;
    } catch (err) {
      out.innerHTML = `<div class="plan">Error: ${esc(String(err.message || err))}</div>`;
    }
  }

  $('#pg-build').addEventListener('click', () => build().catch((e) => status('Could not load SQLite: ' + e.message)));
  root.querySelectorAll('input[type=checkbox]').forEach((el) => el.addEventListener('change', toggle));
  $('#pg-run').addEventListener('click', run);
  $('#pg-analyze').addEventListener('click', analyze);
})();
