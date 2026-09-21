/* ===================================================================
   Health Coach - client

   Plain JavaScript, no framework and no build step, so every line here
   can be read and explained. Organised as: routing, theme, rendering
   per page, conversation, voice, and PWA install.
   =================================================================== */

const $ = id => document.getElementById(id);
const api = {
  get: path => fetch(path).then(r => r.json()),
  post: (path, body) => fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  }),
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
  voice:    () => {},
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
        <span class="mono" style="font-size:11px;color:var(--ink-faint)">
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

$('build-report').addEventListener('click', async e => {
  e.target.disabled = true;
  e.target.textContent = 'Building';
  const r = await api.post('/api/chat', { message: 'make a summary for my doctor' });
  const d = await r.json();
  state.trace = d.trace || [];
  $('report-out').innerHTML =
    `<div class="turn"><div class="speaker"></div>
       <div class="body is-fixed">${escapeHtml(d.reply)}</div></div>`;
  e.target.disabled = false;
  e.target.textContent = 'Rebuild summary';
});

/* ---------------- Agents ---------------- */

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

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recogniser = null, listening = false;

function setListening(on) {
  listening = on;
  $('mic-big').classList.toggle('is-listening', on);
  $('mic-big').textContent = on ? 'Listening' : 'Tap to speak';
  $('mic-inline').classList.toggle('is-listening', on);
  $('mic-inline').textContent = on ? 'Listening' : 'Speak';
}

function startListening() {
  if (!recogniser || listening) return;
  try { recogniser.start(); setListening(true); } catch (e) { setListening(false); }
}

if (Recognition) {
  recogniser = new Recognition();
  recogniser.lang = 'en-IN';
  recogniser.interimResults = false;

  recogniser.onresult = async e => {
    const said = e.results[0][0].transcript;
    $('heard').textContent = said;
    $('spoken').textContent = 'Thinking';
    const onVoicePage = location.hash === '#voice';
    const d = await send(said, { quiet: onVoicePage });
    if (onVoicePage && d) $('spoken').textContent = d.reply;
  };
  recogniser.onerror = e => {
    setListening(false);
    $('voice-hint').textContent = e.error === 'not-allowed'
      ? 'Microphone permission was declined.' : '';
  };
  recogniser.onend = () => setListening(false);

  $('mic-big').addEventListener('click', startListening);
  $('mic-inline').addEventListener('click', startListening);
} else {
  $('mic-big').disabled = true;
  $('mic-inline').disabled = true;
  $('voice-hint').textContent =
    'This browser does not support speech recognition. Chrome or Edge does.';
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

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => { /* offline shell is optional */ });
}

function showEphemeralNotice() {
  if (document.getElementById('ephemeral')) return;
  const bar = document.createElement('div');
  bar.id = 'ephemeral';
  bar.className = 'notice';
  bar.textContent = 'Preview deployment: this host does not keep data '
    + 'between visits, so anything you log here may disappear. Run it '
    + 'locally for real use.';
  document.querySelector('.stage').prepend(bar);
}

/* ---------------- boot ---------------- */

async function boot() {
  setTheme(currentTheme());

  try {
    const h = await api.get('/api/health');
    const live = Object.entries(h.azure).filter(([, on]) => on).map(([k]) => k);
    $('svc').innerHTML = live.length
      ? 'azure <b>' + live.join(' ') + '</b>'
      : 'offline mode';

    // Say so when the host cannot keep data. Silently losing what someone
    // logged is worse than telling them it is a preview.
    if (h.storage === 'ephemeral') showEphemeralNotice();
  } catch (e) { $('svc').textContent = 'server unreachable'; }

  // An installed shortcut can open straight into voice: /?voice=1
  if (new URLSearchParams(location.search).get('voice') === '1') {
    location.hash = '#voice';
  }
  renderMoodScale(null);
  loadProfile().catch(() => { /* profile is optional */ });
  route();
}

boot();
