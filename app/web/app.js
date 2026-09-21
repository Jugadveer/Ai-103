/* ===================================================================
   Health Coach - client

   Plain JavaScript, no framework and no build step, so every line here
   can be read and explained. Organised as: routing, theme, rendering
   per page, conversation, voice, and PWA install.
   =================================================================== */

const $ = id => document.getElementById(id);

// A session can end while the page is still open: the cookie expires, or
// the account is signed out in another tab. Every data call goes through
// here, so one place notices and puts the sign-in screen back rather than
// letting the page quietly fill with blanks.
function watchForSignOut(response, path) {
  if (response.status === 401 && !path.startsWith('/api/auth/')) {
    showGate('Your session ended. Please sign in again.');
  }
  return response;
}

const api = {
  get: path => fetch(path)
    .then(r => watchForSignOut(r, path))
    .then(r => r.json()),
  post: (path, body) => fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  }).then(r => watchForSignOut(r, path)),
};

const state = { trace: [], progress: null, lastReply: '' };

function escapeHtml(value) {
  return String(value).replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function toast(message, kind) {
  const el = document.createElement('div');
  el.className = 'toast' + (kind ? ' is-' + kind : '');
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

/* ---------------- routing ---------------- */

const ROUTES = {
  today:    refreshToday,
  coach:    () => $('entry').focus(),
  trends:   refreshTrends,
  body:     refreshBody,
  review:   refreshReviewPage,
  progress: refreshProgress,
  report:   () => {},
  agents:   refreshAgents,
};

function route() {
  const name = (location.hash || '#today').slice(1);
  const target = ROUTES[name] ? name : 'today';

  document.querySelectorAll('.page').forEach(p =>
    p.classList.toggle('is-active', p.id === 'page-' + target));
  document.querySelectorAll('.nav-links a').forEach(a =>
    a.setAttribute('aria-current', a.dataset.route === target ? 'page' : 'false'));

  ROUTES[target]();
}

window.addEventListener('hashchange', route);

/* ---------------- theme ---------------- */

function currentTheme() {
  return document.documentElement.getAttribute('data-theme') || 'light';
}

function setTheme(mode) {
  document.documentElement.setAttribute('data-theme', mode);
  try { localStorage.setItem('hc-theme', mode); } catch (e) { /* private mode */ }
  $('theme-toggle').textContent = mode === 'dark' ? 'Light' : 'Dark';
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', mode === 'dark' ? '#101311' : '#fbfbfa');
  // Charts read CSS variables at draw time, so redraw them on a theme change.
  if (location.hash === '#trends') refreshTrends();
}

$('theme-toggle').addEventListener('click', () =>
  setTheme(currentTheme() === 'dark' ? 'light' : 'dark'));

/* ---------------- Today ---------------- */

function ringSvg(percent, done) {
  const r = 26, c = 2 * Math.PI * r;
  const offset = c * (1 - Math.min(1, percent / 100));
  return `<svg width="68" height="68" viewBox="0 0 68 68" aria-hidden="true">
    <circle class="track" cx="34" cy="34" r="${r}" fill="none" stroke-width="6"/>
    <circle class="fill" cx="34" cy="34" r="${r}" fill="none" stroke-width="6"
            stroke-linecap="butt" stroke-dasharray="${c.toFixed(1)}"
            stroke-dashoffset="${offset.toFixed(1)}"
            transform="rotate(-90 34 34)"/>
    <text class="pct" x="34" y="38" text-anchor="middle">${done ? '✓' : percent + '%'}</text>
  </svg>`;
}

async function refreshToday() {
  const [progress, dash] = await Promise.all([
    api.get('/api/progress'), api.get('/api/dashboard'),
  ]);
  state.progress = progress;

  $('rings').innerHTML = progress.goals.map(g => `
    <div class="ring${g.done ? ' is-done' : ''}">
      ${ringSvg(g.percent, g.done)}
      <div class="label">${escapeHtml(g.label)}</div>
      <div class="detail">${g.current} / ${g.target} ${escapeHtml(g.unit)}</div>
    </div>`).join('');

  renderReadouts(dash);
  refreshTodayInsights();
}

const READOUTS = [
  ['Sleep debt', d => d.sleep.debt_hours + 'h', d => d.sleep.debt_hours > 3,
   d => d.sleep.has_data],
  ['Avg sleep',  d => d.sleep.avg_hours + 'h', d => d.sleep.status === 'poor',
   d => d.sleep.has_data],
  ['Calories',   d => d.nutrition.calories_today, d => d.nutrition.status === 'low',
   d => d.nutrition.has_data],
  ['Week active', d => d.activity.minutes_week + ' min',
   d => d.activity.status === 'sedentary', d => d.activity.has_data],
  ['Mood',       d => d.mood.avg_score + '/10', d => d.mood.status === 'low',
   d => d.mood.has_data],
  ['BMI',        d => d.vitals.bmi, d => false, d => !!d.vitals.bmi],
  ['Heart rate', d => d.vitals.heart_rate + ' bpm',
   d => d.vitals.status === 'attention', d => !!d.vitals.heart_rate],
  ['Meds due',   d => d.medication.pending.length,
   d => d.medication.status === 'missed', d => d.medication.has_data],
];

function renderReadouts(d) {
  $('readouts').innerHTML = READOUTS.map(([label, value, low, has]) => {
    const present = has(d);
    const cls = !present ? ' is-empty' : (low(d) ? ' is-low' : '');
    return `<div class="readout${cls}">
      <div class="label">${escapeHtml(label)}</div>
      <div class="value">${present ? escapeHtml(value(d)) : 'no data'}</div>
    </div>`;
  }).join('');
}

async function refreshTodayInsights() {
  const r = await api.post('/api/chat', { message: 'show me the patterns' });
  const d = await r.json();
  const patterns = (d.data && d.data.patterns) || [];
  $('insight-count').textContent = patterns.length
    ? patterns.length + ' found' : '';
  $('today-insights').innerHTML = patterns.length
    ? patterns.map(p => `<p style="margin:0 0 9px;font-size:13.5px">
        ${escapeHtml(p.insight)}.
        <span class="num" style="font-size:11.5px;color:var(--ink-faint)">
          ${escapeHtml(p.evidence)}</span></p>`).join('')
    : '<p class="placeholder">Nothing stands out yet. A few more days of ' +
      'logging makes patterns easier to spot.</p>';
}

$('quick').addEventListener('click', async e => {
  const btn = e.target.closest('button');
  if (!btn) return;
  btn.disabled = true;
  const r = await api.post('/api/quicklog', {
    action: btn.dataset.action, value: Number(btn.dataset.value),
  });
  const d = await r.json();
  toast(d.ok ? 'Logged.' : d.message, d.ok ? '' : 'warn');
  btn.disabled = false;
  refreshToday();
});

/* ---------------- Trends ---------------- */

const CHARTS = [
  { key: 'sleep',    title: 'Sleep',     target: 7,    unit: 'h' },
  { key: 'water',    title: 'Water',     target: 8,    unit: '' },
  { key: 'steps',    title: 'Steps',     target: 8000, unit: '' },
  { key: 'active',   title: 'Movement',  target: 30,   unit: 'min' },
  { key: 'calories', title: 'Calories',  target: 2000, unit: '' },
  { key: 'mood',     title: 'Mood',      target: 7,    unit: '/10' },
];

function barChart(points, target) {
  const W = 300, H = 88, n = points.length;
  const slot = W / n, bw = Math.max(5, slot * 0.62);
  const values = points.map(p => p.value).filter(v => v !== null);
  const dataMax = Math.max(...values, 0);

  // Scale to the data, not to the target. If the target is far above what
  // was actually logged (800 steps against a target of 8000), including it
  // squashes every bar into a sliver and day-to-day variation becomes
  // unreadable. The header already states the target in words.
  const peak = (dataMax > 0 && target > dataMax * 2)
    ? dataMax * 1.25
    : Math.max(target, dataMax, 1) * 1.12;
  const y = v => H - (Math.min(v, peak) / peak) * H;
  const targetVisible = target <= peak;

  const bars = points.map((p, i) => {
    const x = i * slot + (slot - bw) / 2;
    if (p.value === null) {
      // A missing day is drawn as a faint stub, never as a zero bar,
      // so "did not log" is visibly different from "logged nothing".
      return `<rect class="gap" x="${x.toFixed(1)}" y="${H - 2}"
              width="${bw.toFixed(1)}" height="2"/>`;
    }
    const top = y(p.value);
    const below = p.value < target;
    return `<rect class="bar${below ? ' is-below' : ''}" x="${x.toFixed(1)}"
            y="${top.toFixed(1)}" width="${bw.toFixed(1)}"
            height="${(H - top).toFixed(1)}"><title>${p.day}: ${p.value}</title></rect>`;
  }).join('');

  const ty = y(target);
  const targetLine = targetVisible
    ? `<line class="target-line" x1="0" y1="${ty.toFixed(1)}" x2="${W}" y2="${ty.toFixed(1)}"/>`
    : '';
  return `<svg viewBox="0 0 ${W} ${H + 14}" preserveAspectRatio="none" role="img">
    <line class="grid-line" x1="0" y1="${H}" x2="${W}" y2="${H}"/>
    ${targetLine}
    ${bars}
    <text class="axis" x="0" y="${H + 11}">${points[0].day.slice(5)}</text>
    <text class="axis" x="${W}" y="${H + 11}" text-anchor="end">today</text>
  </svg>`;
}

async function refreshTrends() {
  const data = await api.get('/api/history?days=14');
  $('charts').innerHTML = CHARTS.map(c => {
    const s = data[c.key];
    const pts = s.points;
    const known = pts.map(p => p.value).filter(v => v !== null);
    const latest = pts[pts.length - 1].value;
    const avg = known.length
      ? Math.round((known.reduce((a, b) => a + b, 0) / known.length) * 10) / 10
      : null;
    return `<div class="chart">
      <header>
        <h3>${escapeHtml(c.title)}</h3>
        <span class="avg">${avg === null ? 'no data'
          : 'avg ' + avg + ' · target ' + c.target}</span>
        <span class="now">${latest === null ? '-' : latest + c.unit}</span>
      </header>
      ${barChart(pts, c.target)}
    </div>`;
  }).join('');
}

/* ---------------- Body ----------------
   Nothing on this page is measured by the app. Every figure is a number
   the user read off a scale, a cuff, or their phone. BMI is the one thing
   computed here, because it is arithmetic on two of those numbers. */

async function postVitals(payload, outId, onOk) {
  const out = $(outId);
  const d = await (await api.post('/api/vitals', payload)).json();
  if (!d.ok) {
    out.className = 'result is-error';
    out.textContent = d.errors[0] || 'That did not look right.';
    return null;
  }
  out.className = 'result';
  onOk(d.vitals, out);
  refreshBody();
  return d.vitals;
}

$('bmi-form').addEventListener('submit', async e => {
  e.preventDefault();
  const height = Number($('in-height').value) || null;
  const weight = Number($('in-weight').value) || null;
  if (!height && !weight) {
    $('bmi-out').className = 'result is-error';
    $('bmi-out').textContent = 'Enter a height, a weight, or both.';
    return;
  }
  await postVitals({ height_cm: height, weight_kg: weight }, 'bmi-out',
    (v, out) => {
      if (v.bmi) {
        out.innerHTML = '<div class="headline">' + v.bmi + '</div>'
          + '<div class="band">BMI, ' + escapeHtml(v.bmi_band) + '</div>'
          + '<div class="note">A population screening figure, not a '
          + 'diagnosis. It does not account for muscle, build or age.</div>';
      } else {
        out.textContent = 'Saved. Add your ' + v.missing_for_bmi
          + ' to get a BMI.';
      }
    });
});

$('reading-form').addEventListener('submit', async e => {
  e.preventDefault();
  const sys = Number($('in-sys').value) || null;
  const dia = Number($('in-dia').value) || null;
  const hr = Number($('in-hr').value) || null;
  const out = $('reading-out');
  if ((sys && !dia) || (dia && !sys)) {
    out.className = 'result is-error';
    out.textContent = 'Blood pressure needs both numbers.';
    return;
  }
  if (!sys && !hr) {
    out.className = 'result is-error';
    out.textContent = 'Enter a reading first.';
    return;
  }
  await postVitals({ systolic: sys, diastolic: dia, heart_rate: hr },
    'reading-out', (v, o) => {
      o.innerHTML = v.flags.length
        ? '<div class="band">' + escapeHtml(v.flags.join(' '))
          + ' Worth mentioning to a doctor.</div>'
        : '<div class="band">Saved. Those readings sit inside the usual '
          + 'reference ranges.</div>';
    });
});

$('activity-form').addEventListener('submit', async e => {
  e.preventDefault();
  const steps = Number($('in-steps').value) || 0;
  const active = Number($('in-active').value) || 0;
  if (!steps && !active) return;
  const notes = [];
  for (const pair of [['steps', steps], ['active', active]]) {
    if (!pair[1]) continue;
    const d = await (await api.post('/api/quicklog',
      { action: pair[0], value: pair[1] })).json();
    notes.push(d.ok ? pair[0] + ' recorded' : d.message);
  }
  $('activity-out').className = 'result';
  $('activity-out').textContent = notes.join('. ') + '.';
  $('in-steps').value = '';
  $('in-active').value = '';
  refreshBody();
});

async function refreshBody() {
  const d = await api.get('/api/dashboard');
  const v = d.vitals, a = d.activity;
  const rows = [
    ['Height', v.height_cm ? v.height_cm + ' cm' : null],
    ['Weight', v.weight_kg ? v.weight_kg + ' kg' : null],
    ['BMI', v.bmi],
    ['Blood pressure', v.blood_pressure],
    ['Heart rate', v.heart_rate ? v.heart_rate + ' bpm' : null],
    ['Steps today', a.steps_today || null],
    ['Active today', a.minutes_today ? a.minutes_today + ' min' : null],
  ];
  $('body-readouts').innerHTML = rows.map(row =>
    '<div class="readout' + (row[1] ? '' : ' is-empty') + '">'
    + '<div class="label">' + escapeHtml(row[0]) + '</div>'
    + '<div class="value">'
    + (row[1] ? escapeHtml(row[1]) : 'not entered') + '</div></div>'
  ).join('');
}

/* ---------------- Review ----------------
   The whole-picture pass. Energy needs are arithmetic on numbers the user
   supplied, so the working is shown rather than asserted. */

let reviewLoaded = false;

function refreshReviewPage() {
  if (!reviewLoaded) {
    $('review-out').innerHTML = '<p class="placeholder">Run the review and '
      + 'every agent will be consulted.</p>';
  }
}

function energyBand(e, findings) {
  if (!e) return '';
  const balance = findings.find(f => f.topic === 'Energy balance'
                                  || f.topic === 'Intake looks incomplete');
  let tone = 'is-ok', note = 'close to maintenance';
  if (balance && balance.topic === 'Intake looks incomplete') {
    tone = 'is-under'; note = 'looks part-logged';
  } else if (balance && /below/.test(balance.evidence)) {
    tone = 'is-under'; note = 'below maintenance';
  } else if (balance && /above/.test(balance.evidence)) {
    tone = 'is-over'; note = 'above maintenance';
  }
  return '<div class="energy-band">'
    + '<div class="cell"><div class="k">Resting rate</div>'
    + '<div class="v">' + e.resting + '</div>'
    + '<div class="sub">kcal per day at rest</div></div>'
    + '<div class="cell"><div class="k">Maintenance</div>'
    + '<div class="v ' + tone + '">' + e.maintenance + '</div>'
    + '<div class="sub">' + e.range_low + ' to ' + e.range_high
    + ' kcal, ' + note + '</div></div>'
    + '<div class="cell"><div class="k">Activity factor</div>'
    + '<div class="v">x' + e.activity_factor + '</div>'
    + '<div class="sub">' + escapeHtml(e.activity_label) + '</div></div>'
    + '</div>';
}

$('run-review').addEventListener('click', async e => {
  e.target.disabled = true;
  e.target.textContent = 'Consulting every agent';
  try {
    const d = await api.get('/api/assessment');
    state.trace = d.trace || [];
    reviewLoaded = true;
    const findings = (d.data && d.data.findings) || [];
    const energy = d.data && d.data.energy;

    $('energy-summary').innerHTML = energyBand(energy, findings);

    const flagWords = /incomplete|doctor|clinician|low|debt|below|missing/i;
    $('review-out').innerHTML = findings.map(f =>
      '<div class="finding' + (flagWords.test(f.topic) ? ' is-flag' : '') + '">'
      + '<h4>' + escapeHtml(f.topic) + '</h4>'
      + '<p>' + escapeHtml(f.text) + '</p>'
      + '<div class="evidence">' + escapeHtml(f.evidence) + '</div>'
      + '</div>').join('')
      + '<p class="disclaimer">Observations about what you logged, not a '
      + 'diagnosis. Energy figures come from a standard equation and are '
      + 'routinely out by ten percent. Anything medical belongs with a '
      + 'doctor.</p>';
  } catch (err) {
    $('review-out').innerHTML = '<p class="placeholder">Could not run the '
      + 'review. Is the server running?</p>';
  }
  e.target.disabled = false;
  e.target.textContent = 'Run it again';
});

/* ---------------- mood scale ----------------
   Mood cannot be sensed, so it is asked for, with worded anchors so a 4
   means roughly the same thing from one week to the next. */

const MOOD_WORDS = {
  1: 'At my worst', 2: 'Very low', 3: 'Low', 4: 'Below par', 5: 'Neutral',
  6: 'Reasonable', 7: 'Good', 8: 'Really good', 9: 'Excellent',
  10: 'At my best',
};

function renderMoodScale(picked) {
  $('mood-scale').innerHTML = Object.keys(MOOD_WORDS).map(n =>
    '<button type="button" data-score="' + n + '"'
    + (String(picked) === n ? ' class="is-picked"' : '') + '>'
    + '<span class="n">' + n + '</span>'
    + '<span class="word">' + MOOD_WORDS[n] + '</span></button>').join('');
}

$('mood-scale').addEventListener('click', async e => {
  const btn = e.target.closest('button');
  if (!btn) return;
  const score = Number(btn.dataset.score);
  const d = await (await api.post('/api/quicklog',
    { action: 'mood', value: score })).json();
  if (!d.ok) { toast(d.message, 'warn'); return; }
  renderMoodScale(score);
  toast('Logged ' + score + ' out of 10, ' + MOOD_WORDS[score].toLowerCase() + '.');
  refreshToday();
});

/* ---------------- profile ---------------- */

async function loadProfile() {
  const d = await api.get('/api/profile');
  const sel = $('in-activity');
  sel.innerHTML = Object.entries(d.activity_levels).map(pair =>
    '<option value="' + pair[0] + '">' + escapeHtml(pair[1]) + '</option>'
  ).join('');
  if (d.profile.age) $('in-age').value = d.profile.age;
  if (d.profile.sex) $('in-sex').value = d.profile.sex;
  if (d.profile.activity_level) sel.value = d.profile.activity_level;
}

$('profile-form').addEventListener('submit', async e => {
  e.preventDefault();
  const out = $('profile-out');
  const d = await (await api.post('/api/profile', {
    age: Number($('in-age').value) || null,
    sex: $('in-sex').value || null,
    activity_level: $('in-activity').value || null,
  })).json();
  out.className = d.ok ? 'result' : 'result is-error';
  out.textContent = d.ok
    ? 'Saved. The Review page can now estimate your energy needs.'
    : d.errors[0];
});

/* ---------------- Progress ---------------- */

async function refreshProgress() {
  const p = await api.get('/api/progress');
  state.progress = p;

  $('progress-stats').innerHTML = `
    <div class="stat"><div class="k">Current streak</div>
      <div class="v">${p.streak}</div>
      <div class="sub">${p.streak === 1 ? 'day' : 'days'} in a row</div></div>
    <div class="stat"><div class="k">Longest streak</div>
      <div class="v">${p.longest_streak}</div><div class="sub">days</div></div>
    <div class="stat"><div class="k">Rings today</div>
      <div class="v">${p.rings_closed}/${p.rings_total}</div>
      <div class="sub">goals closed</div></div>
    <div class="stat"><div class="k">Days logged</div>
      <div class="v">${p.days_logged}</div><div class="sub">all time</div></div>
    <div class="stat"><div class="k">Points</div>
      <div class="v">${p.points}</div><div class="sub">level ${p.level}</div></div>`;

  $('level-detail').textContent =
    `${p.points_into_level} / ${p.points_per_level} to level ${p.level + 1}`;
  $('level-fill').style.width =
    (100 * p.points_into_level / p.points_per_level) + '%';

  $('badge-count').textContent =
    `${p.unlocked.length} of ${p.unlocked.length + p.locked.length}`;
  const badge = (a, unlocked) => `
    <div class="badge ${unlocked ? 'is-unlocked' : 'is-locked'}">
      <div class="mark">${unlocked ? '✓' : '·'}</div>
      <div class="name">${escapeHtml(a.name)}</div>
      <div class="how">${escapeHtml(a.how)}</div>
    </div>`;
  $('badges').innerHTML = p.unlocked.map(a => badge(a, true)).join('')
                        + p.locked.map(a => badge(a, false)).join('');
}

/* ---------------- Report ---------------- */

function sparkline(points, target, width, height) {
  const values = points.map(p => p.value).filter(v => v !== null);
  if (!values.length) return '';
  const peak = Math.max(target, ...values) * 1.1;
  const slot = width / points.length;
  const bars = points.map((p, i) => {
    const x = i * slot + slot * 0.18;
    const w = slot * 0.64;
    if (p.value === null) {
      return `<rect class="spark-gap" x="${x.toFixed(1)}" y="${height - 1.5}"
              width="${w.toFixed(1)}" height="1.5"/>`;
    }
    const h = Math.max(1.5, (p.value / peak) * height);
    return `<rect class="spark${p.value < target ? ' is-low' : ''}"
            x="${x.toFixed(1)}" y="${(height - h).toFixed(1)}"
            width="${w.toFixed(1)}" height="${h.toFixed(1)}"/>`;
  }).join('');
  // A dashed rule at the target, so the bars are read against something
  // rather than just being tall or short.
  const ty = (height - (target / peak) * height).toFixed(1);
  const line = `<line class="spark-target" x1="0" y1="${ty}"
                x2="${width}" y2="${ty}"/>`;
  return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"
          class="sparkline" aria-hidden="true">${line}${bars}</svg>`;
}

const REPORT_CARDS = [
  { key: 'sleep',    label: 'Sleep', target: 7,
    value: d => d.sleep.has_data ? d.sleep.avg_hours + 'h' : null,
    note:  d => d.sleep.has_data
      ? 'nightly average, ' + d.sleep.debt_hours + 'h of debt built up' : '' },
  { key: 'water',    label: 'Water', target: 8,
    value: d => d.hydration.glasses_today + ' glasses',
    note:  () => 'today, against a target of 8' },
  { key: 'calories', label: 'Food', target: 2000,
    value: d => d.nutrition.calories_today + ' kcal',
    note:  d => d.nutrition.meals_today + (d.nutrition.meals_today === 1
      ? ' meal logged today' : ' meals logged today') },
  { key: 'steps',    label: 'Steps', target: 8000,
    value: d => d.activity.steps_today || 0,
    note:  d => d.activity.minutes_week + ' active minutes this week' },
  { key: 'mood',     label: 'Mood', target: 7,
    value: d => d.mood.has_data ? d.mood.avg_score + ' / 10' : null,
    note:  d => d.mood.has_data ? 'self-reported, trend ' + d.mood.trend : '' },
];

async function buildReport() {
  const btn = $('build-report');
  btn.disabled = true;
  btn.textContent = 'Building';

  const [dash, hist, chat] = await Promise.all([
    api.get('/api/dashboard'),
    api.get('/api/history?days=30'),
    api.post('/api/chat', { message: 'make a summary for my doctor' })
      .then(r => r.json()),
  ]);

  const today = new Date().toLocaleDateString('en-GB',
    { day: 'numeric', month: 'long', year: 'numeric' });

  const cards = REPORT_CARDS.map(c => {
    const value = c.value(dash);
    if (value === null) return '';
    const series = hist[c.key];
    return `<div class="rcard">
      <div class="rcard-label">${escapeHtml(c.label)}</div>
      <div class="rcard-value">${escapeHtml(value)}</div>
      <div class="rcard-note">${escapeHtml(c.note(dash))}</div>
      ${series ? sparkline(series.points, c.target, 140, 26) : ''}
      <div class="rcard-axis">last 30 days</div>
    </div>`;
  }).join('');

  const v = dash.vitals;
  const vitalBits = [
    v.weight_kg ? ['Weight', v.weight_kg + ' kg'] : null,
    v.bmi ? ['BMI', v.bmi + ', ' + v.bmi_band] : null,
    v.blood_pressure ? ['Blood pressure', v.blood_pressure + ' mmHg'] : null,
    v.heart_rate ? ['Resting heart rate', v.heart_rate + ' bpm'] : null,
  ].filter(Boolean);

  const energyLine = (chat.reply.match(/ENERGY\s+(.+)/) || [])[1];

  $('report-visual').innerHTML = `
    <div class="report-sheet">
      <div class="report-head">
        <div>
          <div class="report-title">Health summary</div>
          <div class="report-sub">Prepared ${escapeHtml(today)}</div>
        </div>
        <div class="report-stamp">Self-reported<br>Not a clinical record</div>
      </div>

      <div class="rcards">${cards}</div>

      ${vitalBits.length ? `<div class="report-section">
        <h4>Measurements you entered</h4>
        <div class="rmeta">${vitalBits.map(([k, val]) =>
          `<div><span>${escapeHtml(k)}</span><b>${escapeHtml(val)}</b></div>`
        ).join('')}</div>
      </div>` : ''}

      ${energyLine ? `<div class="report-section">
        <h4>Energy</h4>
        <p class="report-line">${escapeHtml(energyLine)}</p>
      </div>` : ''}

      ${dash.medication.has_data ? `<div class="report-section">
        <h4>Medication</h4>
        <p class="report-line">${escapeHtml(dash.medication.names.join(', '))},
          taken on ${dash.medication.adherence_week_pct}% of days this week.
          Adherence only. This app does not advise on medication.</p>
      </div>` : ''}

      ${renderSymptoms(chat.reply)}

      <div class="report-foot">
        Every figure here was entered by the patient. Nothing was measured by
        a device. Calorie and energy figures are estimates. No diagnosis is
        implied and no clinician has reviewed this.
      </div>
    </div>`;

  $('report-text').textContent = chat.reply;
  $('report-plain').hidden = false;
  $('copy-report').hidden = false;
  $('print-report').hidden = false;
  btn.disabled = false;
  btn.textContent = 'Rebuild';
}

function renderSymptoms(text) {
  const block = text.split('REPORTED SYMPTOMS')[1];
  if (!block) return '';
  const rows = block.split('\n')
    .map(l => l.trim())
    .filter(l => /^\d{4}-\d{2}-\d{2}/.test(l))
    .map(l => {
      const day = l.slice(0, 10);
      const note = l.slice(10).trim();
      const when = new Date(day).toLocaleDateString('en-GB',
        { day: 'numeric', month: 'short' });
      return `<li><span class="when">${escapeHtml(when)}</span>
              ${escapeHtml(note)}</li>`;
    });
  if (!rows.length) return '';
  return `<div class="report-section">
    <h4>What they reported feeling</h4>
    <ul class="symptom-list">${rows.join('')}</ul>
  </div>`;
}

$('build-report').addEventListener('click', buildReport);

$('copy-report').addEventListener('click', async e => {
  try {
    await navigator.clipboard.writeText($('report-text').textContent);
    e.target.textContent = 'Copied';
    setTimeout(() => { e.target.textContent = 'Copy as text'; }, 1800);
  } catch (err) { toast('Could not copy. Open the plain text version.', 'warn'); }
});

$('print-report').addEventListener('click', () => window.print());

/* ---------------- Agents ---------------- *//* ---------------- Agents ---------------- */

function brief(value) {
  if (Array.isArray(value)) {
    if (!value.length) return '[]';
    const first = String(value[0]);
    const head = first.length > 26 ? first.slice(0, 26) + '…' : first;
    return value.length > 1 ? `[${head} +${value.length - 1}]` : `[${head}]`;
  }
  const text = JSON.stringify(value);
  return text.length > 32 ? text.slice(0, 32) + '…' : text;
}

function renderTrace(hops) {
  $('tally').textContent = hops.length
    ? hops.length + (hops.length === 1 ? ' call' : ' calls') : 'idle';
  if (!hops.length) {
    $('trace').innerHTML = '<p class="placeholder is-quiet">No agent calls. ' +
      'The coach answered directly.</p>';
    return;
  }
  const root = hops[0].from;
  $('trace').innerHTML = hops.map((h, i) => {
    const facts = Object.entries(h.data)
      .filter(([k]) => !['has_data', 'role', 'holds_data'].includes(k))
      .slice(0, 3)
      .map(([k, v]) => `${escapeHtml(k)}=<b>${escapeHtml(brief(v))}</b>`)
      .join('  ');
    return `<div class="call${h.from !== root ? ' depth-1' : ''}"
                 style="animation-delay:${i * 50}ms">
      <div class="hop">${escapeHtml(h.from)}<span class="arrow">&rarr;</span>${escapeHtml(h.to)}</div>
      <div class="payload">${facts || escapeHtml(h.reason)}</div>
    </div>`;
  }).join('');
}

async function refreshAgents() {
  renderTrace(state.trace);
  const rows = await api.get('/api/agents');
  $('roster-count').textContent = rows.length + ' agents';
  $('agent-rows').innerHTML = rows.map(r =>
    `<tr><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.description)}</td></tr>`
  ).join('');
}

/* ---------------- conversation ---------------- */

function addTurn(speaker, text, variant, trace) {
  const el = document.createElement('div');
  el.className = 'turn' + (speaker === 'You' ? ' from-user' : '')
               + (variant ? ' ' + variant : '');
  el.innerHTML = '<div class="speaker"></div><div class="body"></div>';
  el.querySelector('.speaker').textContent = speaker;
  const body = el.querySelector('.body');
  body.textContent = text;
  if (text.startsWith('HEALTH SUMMARY')) body.classList.add('is-fixed');

  // How the answer was produced stays folded away: available when asked
  // for, not competing with the answer itself.
  if (trace && trace.length) {
    const d = document.createElement('details');
    d.innerHTML = `<summary>${trace.length} agent call${trace.length === 1 ? '' : 's'}</summary>`;
    const list = document.createElement('div');
    list.className = 'payload';
    list.style.marginTop = '6px';
    list.textContent = trace.map(h => `${h.from} → ${h.to}`).join('   ');
    d.appendChild(list);
    el.appendChild(d);
  }

  $('thread').appendChild(el);
  $('thread').scrollTop = $('thread').scrollHeight;
  return el;
}

function addPending() {
  const el = document.createElement('div');
  el.className = 'turn is-pending';
  el.innerHTML = '<div class="speaker">Coach</div>' +
                 '<div class="body"><span></span><span></span><span></span></div>';
  $('thread').appendChild(el);
  $('thread').scrollTop = $('thread').scrollHeight;
  return el;
}

async function send(text, opts) {
  const quiet = opts && opts.quiet;
  if (!text.trim()) return null;
  if (!quiet) { addTurn('You', text); $('entry').value = ''; $('send').disabled = true; }
  const pending = quiet ? null : addPending();

  try {
    const r = await api.post('/api/chat', { message: text });
    const d = await r.json();
    state.trace = d.trace || [];
    state.lastReply = d.reply;
    if (pending) pending.remove();
    if (!quiet) {
      const variant = d.data && d.data.blocked ? 'is-blocked'
                    : d.data && d.data.rejected ? 'is-rejected' : '';
      addTurn('Coach', d.reply, variant, d.trace);
    }
    speak(d.reply);
    return d;
  } catch (e) {
    if (pending) pending.remove();
    if (!quiet) addTurn('Coach', 'I could not reach the server.', 'is-rejected');
    return null;
  } finally {
    $('send').disabled = false;
  }
}

$('composer').addEventListener('submit', e => { e.preventDefault(); send($('entry').value); });
$('entry').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send($('entry').value); }
});

$('suggestions').addEventListener('click', async e => {
  const btn = e.target.closest('button');
  if (!btn) return;
  if (btn.dataset.seed) {
    btn.disabled = true;
    await api.post('/api/seed');
    addTurn('Coach', 'Loaded a week of logs: short sleep, low fluids, a falling '
                   + 'mood and one medication still pending.');
    btn.disabled = false;
    return;
  }
  send(btn.textContent);
});

/* ---------------- photo ----------------
   Azure OpenAI vision names what is on the plate. It proposes rather than
   logs, because vision can be confidently wrong. */

$('photo-btn').addEventListener('click', () => $('photo-input').click());

$('photo-input').addEventListener('change', async e => {
  const file = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!file) return;
  if (file.size > 6000000) {
    addTurn('Coach', 'That image is too large. Try a smaller photo.',
            'is-rejected');
    return;
  }

  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });

  location.hash = '#coach';
  const sent = addTurn('You', 'Sent a photo of my meal.');
  const img = document.createElement('img');
  img.className = 'shot';
  img.src = dataUrl;
  img.alt = 'The meal photo you sent';
  sent.querySelector('.body').appendChild(img);

  const pending = addPending();
  try {
    const d = await (await api.post('/api/photo', { image: dataUrl })).json();
    pending.remove();
    if (!d.ok) { addTurn('Coach', d.message, 'is-rejected'); return; }
    state.trace = d.trace || [];
    addTurn('Coach', d.reply, '', d.trace);
    speak(d.reply);
  } catch (err) {
    pending.remove();
    addTurn('Coach', 'I could not send that photo.', 'is-rejected');
  }
});

/* ---------------- voice ----------------
   Azure AI Speech supplies the reply audio when a key is configured. A 503
   means it is not, and the browser voice takes over so the page still talks.

   Note on scope: a web app cannot listen for a wake word in the background.
   Installing this as an app (see below) is what removes the "open the site
   first" step; speech still starts on a tap. */

let playing = null;

function browserSpeak(text) {
  if (!window.speechSynthesis) return;
  speechSynthesis.cancel();
  speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}

async function speak(text) {
  if (!text || text.length > 3000) return;
  if (playing) { playing.pause(); playing = null; }
  if (window.speechSynthesis) speechSynthesis.cancel();
  try {
    const r = await api.post('/api/speak', { text });
    if (!r.ok) { browserSpeak(text); return; }
    const url = URL.createObjectURL(await r.blob());
    playing = new Audio(url);
    playing.onended = () => URL.revokeObjectURL(url);
    await playing.play();
  } catch (e) { browserSpeak(text); }
}

/* ---------------- speech input ----------------
   Recorded here and transcribed by Azure AI Speech.

   The browser's own SpeechRecognition was the only path before. On
   desktop Chrome it needs to reach Google's servers, gives up quietly on
   the first hiccup, and the only signal was the button springing back to
   "Speak". That is indistinguishable from broken.

   So: capture raw audio with the Web Audio API, write a WAV by hand
   (MediaRecorder gives webm/opus, which Azure will not take), and post it.
   Every failure now says what went wrong. */

const MIC = { stream: null, ctx: null, node: null, chunks: [], on: false };
const SAMPLE_RATE = 16000;      // what Azure Speech expects

function setListening(on, label) {
  MIC.on = on;
  for (const id of ['mic-big', 'mic-inline']) {
    const el = $(id);
    if (!el) continue;
    el.classList.toggle('is-listening', on);
    el.textContent = label || (on ? 'Listening, tap to stop'
                                  : (id === 'mic-big' ? 'Tap to speak' : 'Speak'));
  }
}

function micHint(text, alsoToast) {
  const el = $('voice-hint');
  if (el) el.textContent = text || '';
  // The hint sits in the strip above the thread, which scrolls out of
  // view once a conversation gets going. Anyone who started voice from
  // the composer button would never see why it failed, which is the bug
  // this whole path exists to fix. So failures toast as well.
  if (text && alsoToast !== false) toast(text, 'warn');
}

function encodeWav(samples, rate) {
  // 16-bit mono PCM with a 44-byte header.
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const ascii = (offset, text) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };
  ascii(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  view.setUint32(16, 16, true);      // PCM header size
  view.setUint16(20, 1, true);       // format: PCM
  view.setUint16(22, 1, true);       // channels: mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);      // bits per sample
  ascii(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return new Blob([view], { type: 'audio/wav' });
}

async function startListening() {
  if (MIC.on) { await stopListening(); return; }
  micHint('');

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    micHint('This browser cannot reach a microphone. Type instead.');
    return;
  }

  try {
    MIC.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    micHint(err && err.name === 'NotAllowedError'
      ? 'Microphone permission was declined. Allow it in the address bar.'
      : 'No microphone available. Type instead.');
    return;
  }

  MIC.ctx = new (window.AudioContext || window.webkitAudioContext)(
    { sampleRate: SAMPLE_RATE });
  const source = MIC.ctx.createMediaStreamSource(MIC.stream);
  MIC.node = MIC.ctx.createScriptProcessor(4096, 1, 1);
  MIC.chunks = [];
  MIC.node.onaudioprocess = e => {
    MIC.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  };
  source.connect(MIC.node);
  MIC.node.connect(MIC.ctx.destination);

  setListening(true);
  micHint('Listening. Tap again when you have finished.', false);

  // A safety stop, so a forgotten recording does not run forever.
  MIC.timer = setTimeout(() => { if (MIC.on) stopListening(); }, 15000);
}

async function stopListening() {
  if (!MIC.on) return;
  clearTimeout(MIC.timer);
  setListening(false, 'Transcribing');
  micHint('');

  try { MIC.node.disconnect(); } catch (e) { /* already gone */ }
  try { MIC.stream.getTracks().forEach(t => t.stop()); } catch (e) { /* ditto */ }

  const total = MIC.chunks.reduce((n, c) => n + c.length, 0);
  const samples = new Float32Array(total);
  let at = 0;
  for (const chunk of MIC.chunks) { samples.set(chunk, at); at += chunk.length; }
  const rate = MIC.ctx.sampleRate;
  try { await MIC.ctx.close(); } catch (e) { /* already closed */ }
  MIC.chunks = [];

  if (total < rate * 0.4) {
    setListening(false);
    micHint('That was too short. Hold on a moment longer next time.');
    return;
  }

  try {
    const res = await fetch('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'audio/wav' },
      body: encodeWav(samples, rate),
    });
    const d = await res.json();
    setListening(false);

    if (!d.ok) {
      micHint(d.message || 'I could not transcribe that.');
      // Browser speech as a second chance where it exists.
      if (d.reason === 'speech_not_configured') browserListen();
      return;
    }

    $('heard').textContent = d.text;
    $('spoken').textContent = 'Thinking';
    const onVoicePage = location.hash === '#voice';
    const reply = await send(d.text, { quiet: onVoicePage });
    if (onVoicePage && reply) $('spoken').textContent = reply.reply;
  } catch (err) {
    setListening(false);
    micHint('Could not reach the server to transcribe that.');
  }
}

/* Fallback only: used when Azure Speech is not configured. */
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

function browserListen() {
  if (!Recognition) return;
  const rec = new Recognition();
  rec.lang = 'en-IN';
  rec.interimResults = false;
  rec.onresult = async e => {
    const said = e.results[0][0].transcript;
    $('heard').textContent = said;
    const onVoicePage = location.hash === '#voice';
    const reply = await send(said, { quiet: onVoicePage });
    if (onVoicePage && reply) $('spoken').textContent = reply.reply;
  };
  rec.onerror = e => micHint('Speech input failed: ' + (e.error || 'unknown') + '.');
  rec.onend = () => setListening(false);
  try { rec.start(); setListening(true); } catch (e) { setListening(false); }
}

for (const id of ['mic-big', 'mic-inline']) {
  const el = $(id);
  if (el) el.addEventListener('click', startListening);
}

/* ---------------- PWA install ---------------- */

let installPrompt = null;

window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  installPrompt = e;
  $('install').hidden = false;
});

$('install').addEventListener('click', async () => {
  if (!installPrompt) return;
  installPrompt.prompt();
  await installPrompt.userChoice;
  installPrompt = null;
  $('install').hidden = true;
});

window.addEventListener('appinstalled', () => {
  $('install').hidden = true;
  toast('Installed. Launch it from your home screen or dock.');
});

// The service worker exists so an installed app opens without a network.
// Two things it must not do.
//
// It must not run during development. A dev server plus a caching worker
// means every edit is a coin toss over whether the browser shows it, and
// the failure looks like the app being broken rather than stale: old
// script against new markup, with no error anywhere.
//
// And when it does update, the page holding the old assets has to know.
// A new worker calls skipWaiting and claims open pages, but those pages
// keep running whatever they already loaded until something reloads them.
// That is the state this app got into: new HTML, month-old script.
const ON_LOCALHOST = ['localhost', '127.0.0.1', '[::1]']
  .includes(location.hostname);

if ('serviceWorker' in navigator) {
  if (ON_LOCALHOST) {
    // Clear anything a previous visit left behind, then stay out of the way.
    navigator.serviceWorker.getRegistrations()
      .then(all => all.forEach(r => r.unregister()))
      .then(() => caches.keys())
      .then(keys => Promise.all(keys.map(k => caches.delete(k))))
      .catch(() => { /* nothing registered, nothing to undo */ });
  } else {
    let reloading = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (reloading) return;      // fires again on the reload itself
      reloading = true;
      location.reload();
    });
    navigator.serviceWorker.register('/sw.js')
      .catch(() => { /* offline shell is optional */ });
  }
}

async function warnIfSessionsAreUnstable() {
  // A signed-out-immediately loop is one of the least obvious things to
  // debug from the outside, so the screen where it happens says why.
  try {
    // One process on your own machine has one key, so sessions are
    // stable there whether or not SECRET_KEY is set. The warning is for
    // hosts that run several.
    if (ON_LOCALHOST) return;
    const h = await api.get('/api/health');
    if (h.sessions !== 'per_process') return;
    const note = document.createElement('div');
    note.className = 'gate-errors';
    note.textContent = 'This host has no SECRET_KEY set, so signing in may '
      + 'not stick. Set one in the environment.';
    $('auth-form').prepend(note);
  } catch (e) { /* the form still works, or nothing does */ }
}

function showEphemeralNotice() {
  if (document.getElementById('ephemeral')) return;
  const bar = document.createElement('div');
  bar.id = 'ephemeral';
  bar.className = 'notice';
  // Worth being specific now that there are accounts: it is not only
  // today's logging that goes, it is the account itself.
  bar.textContent = 'This host has no database attached, so accounts and '
    + 'anything you log here can disappear at any time. Set DATABASE_URL '
    + 'to keep them.';
  document.querySelector('.stage').prepend(bar);
}

/* ---------------- signing in ----------------
   One screen, two modes. Creating an account and signing in differ by two
   fields and one endpoint, so they share a form rather than living on
   separate pages that then have to be kept looking alike. */

let signingUp = false;

function showGate(message) {
  $('gate').hidden = false;
  $('app-nav').hidden = true;
  $('app-stage').hidden = true;
  if (message) showAuthErrors([message]);
}

function hideGate() {
  $('gate').hidden = true;
  $('app-nav').hidden = false;
  $('app-stage').hidden = false;
}

function showAuthErrors(list) {
  const box = $('auth-errors');
  if (!list || !list.length) { box.hidden = true; box.textContent = ''; return; }
  box.hidden = false;
  box.innerHTML = list.map(e => `<div>${escapeHtml(e)}</div>`).join('');
}

function setMode(wantSignup) {
  signingUp = wantSignup;
  showAuthErrors([]);
  $('tab-signin').classList.toggle('is-on', !wantSignup);
  $('tab-signup').classList.toggle('is-on', wantSignup);
  $('field-name').hidden = !wantSignup;
  $('field-sample').hidden = !wantSignup;
  $('auth-submit').textContent = wantSignup ? 'Create account' : 'Sign in';
  $('auth-password').setAttribute('autocomplete',
    wantSignup ? 'new-password' : 'current-password');
  $('switch-text').textContent = wantSignup
    ? 'Already have an account?' : 'New here?';
  $('switch-mode').textContent = wantSignup ? 'Sign in' : 'Create an account';
}

$('tab-signin').addEventListener('click', () => setMode(false));
$('tab-signup').addEventListener('click', () => setMode(true));
$('switch-mode').addEventListener('click', () => setMode(!signingUp));

$('auth-form').addEventListener('submit', async e => {
  e.preventDefault();
  const button = $('auth-submit');
  const wasLabel = button.textContent;
  button.disabled = true;
  button.textContent = signingUp ? 'Creating' : 'Signing in';
  showAuthErrors([]);

  const body = {
    email: $('auth-email').value.trim(),
    password: $('auth-password').value,
  };
  if (signingUp) {
    body.name = $('auth-name').value.trim();
    body.sample_data = $('auth-sample').checked;
  }

  try {
    const res = await api.post(
      signingUp ? '/api/auth/signup' : '/api/auth/login', body);
    const data = await res.json();
    if (!data.ok) {
      showAuthErrors(data.errors || ['That did not work. Try again.']);
      return;
    }
    $('auth-password').value = '';
    await startApp(data.user);
  } catch (err) {
    showAuthErrors(['Could not reach the server. Check your connection.']);
  } finally {
    button.disabled = false;
    button.textContent = wasLabel;
  }
});

$('signout').addEventListener('click', async () => {
  await api.post('/api/auth/logout');
  location.reload();
});

/* ---------------- boot ---------------- */

async function startApp(user) {
  hideGate();
  $('who').textContent = user.name || user.email;
  $('who').title = user.email;

  try {
    const h = await api.get('/api/health');
    const live = Object.entries(h.azure).filter(([, on]) => on).map(([k]) => k);
    $('svc').innerHTML = live.length
      ? '<b>&#9679;</b> Connected'
      : '<span class="dim">&#9679;</span> Working offline';
    $('svc').title = live.length
      ? 'Azure services in use: ' + live.join(', ')
      : 'No Azure services configured, using local rules';

    // Say so when the host cannot keep data. Silently losing what someone
    // logged is worse than letting them believe it was saved.
    if (h.storage === 'ephemeral') showEphemeralNotice();
  } catch (e) { $('svc').textContent = 'server unreachable'; }

  // An installed shortcut can open straight into the coach: /?voice=1
  if (new URLSearchParams(location.search).get('voice') === '1') {
    location.hash = '#coach';
  }
  renderMoodScale(null);
  loadProfile().catch(() => { /* profile is optional */ });
  route();
}

async function boot() {
  setTheme(currentTheme());
  setMode(false);
  try {
    const me = await api.get('/api/auth/me');
    if (me.user) { await startApp(me.user); return; }
  } catch (e) { /* offline: the sign-in screen is the honest fallback */ }
  showGate();
  $('auth-email').focus();
  warnIfSessionsAreUnstable();
}

boot();
