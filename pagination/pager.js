// In-browser pagination demo (sql.js): the same posts table at 100,000 rows, paged with OFFSET and with a keyset cursor.
(function () {
  const root = document.getElementById('pager');
  if (!root) return;
  const $ = (sel) => root.querySelector(sel);
  const ROWS = Number(root.dataset.rows || 100000), PAGE = 20, LAST = ROWS / PAGE;
  const COLS = 'id, created_at, title';
  const ORDER = 'ORDER BY created_at DESC, id DESC';
  const FIRST = `SELECT ${COLS} FROM posts ${ORDER} LIMIT ${PAGE}`;
  const offsetSql = (p) => `SELECT ${COLS} FROM posts ${ORDER} LIMIT ${PAGE} OFFSET ${(p - 1) * PAGE}`;
  const keysetSql = (c) => `SELECT ${COLS} FROM posts WHERE (created_at, id) < (${c[0]}, ${c[1]}) ${ORDER} LIMIT ${PAGE}`;
  let db = null;

  const status = (msg) => { $('.status').textContent = msg; };
  const slider = $('#pager-page');
  const pageOf = () => Math.max(1, Math.round(10 ** (Number(slider.value) / 100 * Math.log10(LAST))));
  const rows = (sql) => { const r = db.exec(sql); return r.length ? r[0].values : []; };
  const fmt = (ms) => (ms >= 1 ? ms.toFixed(2) : ms.toFixed(3)) + ' ms';

  // Repeat until about 60 ms have passed, so sub-millisecond queries are measurable despite timer rounding.
  function timeIt(sql) {
    db.exec(sql);
    let n = 0, el = 0;
    const t0 = performance.now();
    while (el < 60 && n < 5000) { db.exec(sql); n++; el = performance.now() - t0; }
    return el / n;
  }
  // The cursor is the last row of the previous page; the app already has it, so it is looked up untimed.
  function cursor(p) { return rows(`SELECT created_at, id FROM posts ${ORDER} LIMIT 1 OFFSET ${(p - 1) * PAGE - 1}`)[0]; }

  async function build() {
    $('#pager-build').disabled = true;
    status('Loading SQLite (about 650 KB, once)…');
    const SQL = await window.initSqlJs({ locateFile: (f) => 'https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/' + f });
    status(`Inserting ${ROWS.toLocaleString('en-US')} posts…`);
    await new Promise((r) => setTimeout(r, 20));
    const t = performance.now();
    db = new SQL.Database();
    db.run('CREATE TABLE posts (id INTEGER PRIMARY KEY, created_at INTEGER, author TEXT, title TEXT)');
    db.run('BEGIN');
    const ins = db.prepare('INSERT INTO posts (created_at, author, title) VALUES (?, ?, ?)');
    for (let i = 0; i < ROWS; i++) ins.run([1700000000 + Math.floor(i / 3), `author${i % 5000}`, `Post number ${i}`]);
    ins.free();
    db.run('CREATE INDEX idx_created ON posts(created_at, id)');
    db.run('COMMIT');
    status(`Ready: ${ROWS.toLocaleString('en-US')} posts in ${Math.round(performance.now() - t)} ms · SQLite ${rows('SELECT sqlite_version()')[0][0]} in your browser`);
    root.querySelectorAll('input, #pager-writes').forEach((el) => { el.disabled = false; });
    measure();
  }

  function measure() {
    const p = pageOf();
    $('#pager-page-v').textContent = `page ${p.toLocaleString('en-US')} of ${LAST.toLocaleString('en-US')}`;
    if (!db) return;
    const o = offsetSql(p), k = p === 1 ? FIRST : keysetSql(cursor(p));
    const same = JSON.stringify(rows(o)) === JSON.stringify(rows(k));
    const to = timeIt(o), tk = timeIt(k);
    $('#pager-offset').textContent = fmt(to);
    $('#pager-keyset').textContent = fmt(tk);
    $('#pager-sql').textContent = `-- OFFSET: skips ${((p - 1) * PAGE).toLocaleString('en-US')} rows first\n${o}\n\n-- keyset: starts right after the last row of page ${p - 1 || '(none)'}\n${k}`;
    $('#pager-note').textContent = same ? 'Both queries returned the same 20 rows.' : 'The two queries returned different rows.';
  }

  // Read page 1, let 5 newer posts arrive, read page 2 both ways, then remove the 5 posts again.
  function writes() {
    const p1 = rows(FIRST), ids1 = new Set(p1.map((r) => r[0])), last = p1[p1.length - 1];
    const top = rows('SELECT max(created_at) FROM posts')[0][0];
    for (let k = 1; k <= 5; k++) db.run('INSERT INTO posts (created_at, author, title) VALUES (?, ?, ?)', [top + k, 'new', `New post ${k}`]);
    const viaOffset = rows(offsetSql(2)), viaKeyset = rows(keysetSql([last[1], last[0]]));
    db.run("DELETE FROM posts WHERE author = 'new'");
    const list = (box, page) => {
      box.textContent = '';
      page.slice(0, 8).forEach((r) => {
        const li = document.createElement('li');
        li.textContent = r[2] + (ids1.has(r[0]) ? '  ← already on page 1' : '');
        if (ids1.has(r[0])) li.style.color = 'var(--scan)';
        box.appendChild(li);
      });
      const more = document.createElement('li'); more.textContent = '…'; more.style.listStyle = 'none'; box.appendChild(more);
    };
    list($('#pager-w-offset'), viaOffset);
    list($('#pager-w-keyset'), viaKeyset);
    const rep = (page) => page.filter((r) => ids1.has(r[0])).length;
    $('#pager-w-note').textContent = `Page 1 ended at "${last[2]}". After 5 new posts: OFFSET's page 2 repeated ${rep(viaOffset)} rows, keyset's repeated ${rep(viaKeyset)}. The 5 new posts were then deleted again.`;
    $('#pager-w-out').hidden = false;
  }

  $('#pager-build').addEventListener('click', () => build().catch((e) => status('Could not load SQLite: ' + e.message)));
  slider.addEventListener('input', () => { $('#pager-page-v').textContent = `page ${pageOf().toLocaleString('en-US')} of ${LAST.toLocaleString('en-US')}`; });
  slider.addEventListener('change', measure);
  $('#pager-writes').addEventListener('click', writes);
  measure();
})();
