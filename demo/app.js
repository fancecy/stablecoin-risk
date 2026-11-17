'use strict';

const D = window.STUDY;
const $ = id => document.getElementById(id);
const fields = D.path_fields;

const labels = {
  no_intervention: 'No intervention',
  cash_buffer: 'Larger cash buffer',
  credit_line: 'Secured credit line',
  combined: 'Combined'
};
const strategyVar = {
  no_intervention: '--s-none',
  cash_buffer: '--s-cash',
  credit_line: '--s-credit',
  combined: '--s-combined'
};
const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const colorOf = s => cssVar(strategyVar[s]);

const DEFAULTS = { redemption: 20, freeze: 10, sale: 1, activation: 1 };
const CONTROLS = [
  { id: 'redemption', label: 'Share of coins redeemed', hint: 'Total requests as a share of initial liabilities', options: [10, 20, 30, 40, 50], fmt: v => v + '%' },
  { id: 'freeze', label: 'Days the bank cash is frozen', hint: '45 days runs past the 30-day horizon', options: [3, 10, 20, 30, 45], fmt: v => v + 'd' },
  { id: 'sale', label: 'Daily Treasury sales cap', hint: 'Share of original Treasury holdings sold per day', options: [0.1, 1, 3], fmt: v => v + '%' },
  { id: 'activation', label: 'Day the credit line opens', hint: 'Applies to the credit line and combined responses', options: [1, 3, 5, 10], fmt: v => 'Day ' + v }
];
const SECONDARY = {
  financing_debt: ['Debt', 'Debt left after the backlog clears', 'Credit principal plus accrued interest, USD billion'],
  free_cash: ['Cash', 'Cash the issuer can actually spend', 'Excludes balances frozen at the bank, USD billion'],
  net_reserve_coverage: ['Coverage', 'Net reserve coverage', 'Assets net of debt, as % of coins outstanding'],
  equity: ['Equity', 'Issuer equity', 'Reserves minus coins outstanding minus debt, USD billion']
};

const bn = x => (x / 1e9).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const bn3 = x => (x / 1e9).toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const bnCost = x => (x / 1e9).toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
const pct = x => (x == null ? '–' : (x * 100).toFixed(3) + '%');
const minus = s => String(s).replace(/^-/, '−');
const clearance = s =>
  s.recovery_status === 'never_backlogged' ? 'No backlog' : s.clearance_day == null ? 'Not within 30 days' : 'Day ' + s.clearance_day;
const longDate = iso =>
  new Date(iso + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });

let eventId = 'svb2023';
let focusId = 'combined';
let secondaryId = 'financing_debt';

/* ---------- segmented radio groups ---------- */

function segment(container, name, options, current, fmt, onChange) {
  container.innerHTML = options
    .map((v, i) => {
      const id = `${name}-${i}`;
      return `<input type="radio" name="${name}" id="${id}" value="${v}" ${String(v) === String(current) ? 'checked' : ''}><label for="${id}">${fmt(v)}</label>`;
    })
    .join('');
  container.onchange = e => onChange(e.target.value);
}

function buildControls() {
  for (const c of CONTROLS) {
    const box = $('ctl-' + c.id);
    box.innerHTML = `<span class="control-label" id="lbl-${c.id}">${c.label}</span><div class="seg" role="radiogroup" aria-labelledby="lbl-${c.id}" aria-describedby="hint-${c.id}"></div><span class="control-hint" id="hint-${c.id}">${c.hint}</span>`;
    segment(box.querySelector('.seg'), c.id, c.options, DEFAULTS[c.id], c.fmt, renderResults);
  }
  segment($('secondary-metric'), 'secondary', Object.keys(SECONDARY), secondaryId, k => SECONDARY[k][0], v => {
    secondaryId = v;
    renderResults();
  });
}

function settings() {
  const v = id => +document.querySelector(`input[name="${id}"]:checked`).value;
  return { redemption: v('redemption'), freeze: v('freeze'), sale: v('sale'), activation: v('activation') };
}
const key = p => [p.redemption, p.freeze, p.sale, p.activation].join('|');
const selected = () => [...document.querySelectorAll('.check input:checked')].map(x => x.value);
const runs = () => D.grid[key(settings())].filter(r => selected().includes(r.summary.strategy));

/* ---------- chart ---------- */

const charts = {};

function chart(target, series, opts = {}) {
  charts[target] = [series, opts];
  const { xlabel = 'Simulation day', yfmt = (v, dp) => v.toFixed(dp), tipfmt = v => v.toFixed(3), eventLine = false, includeZero = true, baseline = 0, baselineLabel = '', xticks: forcedTicks, annotate } = opts;
  const box = $(target);
  const W = Math.max(300, Math.round(box.clientWidth));
  const H = box.classList.contains('chart-tall') ? Math.min(420, Math.max(260, W * 0.42)) : Math.min(300, Math.max(220, W * 0.36));
  const narrow = W < 520;
  const L = narrow ? 44 : 58, R = narrow ? 10 : 18, T = 18, B = 40;

  const pts = series.flatMap(s => s.points).filter(p => p[1] != null && Number.isFinite(p[1]));
  if (!pts.length) {
    box.innerHTML = '<p class="empty">No observations in this window.</p>';
    return;
  }
  const xmin = Math.min(...pts.map(p => p[0]));
  const xmax = Math.max(...pts.map(p => p[0]));
  let ymin = Math.min(...pts.map(p => p[1]));
  let ymax = Math.max(...pts.map(p => p[1]));
  if (includeZero) {
    ymin = Math.min(baseline, ymin);
    ymax = Math.max(baseline, ymax);
  }
  if (ymin === ymax) {
    ymax = ymin + 1;
    if (ymin !== 0) ymin -= 1;
  }
  const span = ymax - ymin;
  const raw = span / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
  const dp = Math.max(0, -Math.floor(Math.log10(step) + 1e-9) + (step / mag === 2.5 ? 1 : 0));
  const lo = includeZero && ymin === Math.min(baseline, ymin) && ymin === baseline ? ymin : ymin - span * 0.04;
  ymin = Math.floor(lo / step + 1e-9) * step;
  ymax = Math.ceil((ymax + span * 0.06) / step - 1e-9) * step;
  const yticks = [];
  for (let v = ymin; v <= ymax + step / 2; v += step) yticks.push(+v.toFixed(10));

  const x = v => L + ((v - xmin) / (xmax - xmin || 1)) * (W - L - R);
  const y = v => T + ((ymax - v) / (ymax - ymin)) * (H - T - B);

  let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">`;

  for (const v of yticks) {
    const py = y(v).toFixed(1);
    svg += `<line class="grid" x1="${L}" y1="${py}" x2="${W - R}" y2="${py}"/>`;
    svg += `<text class="tick" x="${L - 8}" y="${+py + 4}" text-anchor="end">${minus(yfmt(v, dp))}</text>`;
  }

  let xticks = forcedTicks || (eventLine ? [-14, -7, 0, 7, 14] : [1, 5, 10, 15, 20, 25, 30]);
  if (narrow && !forcedTicks && !eventLine) xticks = [1, 10, 20, 30];
  for (const v of xticks) {
    if (v < xmin || v > xmax) continue;
    svg += `<text class="tick" x="${x(v).toFixed(1)}" y="${H - B + 18}" text-anchor="middle">${eventLine && v > 0 ? '+' : ''}${minus(v)}</text>`;
  }
  svg += `<text class="axis-title" x="${W - R}" y="${H - 4}" text-anchor="end">${xlabel}</text>`;

  if (baseline >= ymin && baseline <= ymax) {
    const yb = y(baseline).toFixed(1);
    svg += `<line class="baseline" x1="${L}" y1="${yb}" x2="${W - R}" y2="${yb}"/>`;
    if (baselineLabel) svg += `<text class="baseline-label" x="${W - R}" y="${+yb - 6}" text-anchor="end">${baselineLabel}</text>`;
  }

  if (eventLine) {
    const x0 = x(0).toFixed(1);
    svg += `<line class="event-line" x1="${x0}" y1="${T}" x2="${x0}" y2="${H - B}"/>`;
    svg += `<text class="event-label" x="${+x0 + 6}" y="${T + 10}">Reference date</text>`;
  }

  for (const s of series) {
    let d = '', pen = false;
    for (const p of s.points) {
      if (p[1] == null || !Number.isFinite(p[1])) { pen = false; continue; }
      d += (pen ? 'L' : 'M') + x(p[0]).toFixed(1) + ',' + y(p[1]).toFixed(1);
      pen = true;
    }
    svg += `<path class="series ${s.strong ? 'series-strong' : ''}" d="${d}" stroke="${s.color}"/>`;
  }

  if (annotate) {
    const ax = x(annotate.x), ay = y(annotate.y);
    const right = ax < W * 0.62;
    svg += `<circle class="anno-dot" cx="${ax.toFixed(1)}" cy="${ay.toFixed(1)}" r="4.5" stroke="${annotate.color}"/>`;
    svg += `<text class="anno" x="${(ax + (right ? 12 : -12)).toFixed(1)}" y="${(ay + 4).toFixed(1)}" text-anchor="${right ? 'start' : 'end'}">${annotate.text}</text>`;
  }

  svg += `<line class="crosshair" x1="0" y1="${T}" x2="0" y2="${H - B}" visibility="hidden"/>`;
  svg += `<g class="hover-dots"></g></svg><div class="tip" hidden></div>`;
  box.innerHTML = svg;

  const el = box.querySelector('svg');
  const cross = box.querySelector('.crosshair');
  const dots = box.querySelector('.hover-dots');
  const tip = box.querySelector('.tip');
  const xs = [...new Set(pts.map(p => p[0]))].sort((a, b) => a - b);

  const hide = () => {
    cross.setAttribute('visibility', 'hidden');
    dots.innerHTML = '';
    tip.hidden = true;
  };
  el.addEventListener('pointermove', ev => {
    const r = el.getBoundingClientRect();
    const rx = ((ev.clientX - r.left) / r.width) * W;
    if (rx < L - 8 || rx > W - R + 8) return hide();
    const vx = xmin + ((rx - L) / (W - L - R)) * (xmax - xmin || 1);
    const near = xs.reduce((a, b) => (Math.abs(b - vx) < Math.abs(a - vx) ? b : a));
    const px = x(near);
    cross.setAttribute('x1', px);
    cross.setAttribute('x2', px);
    cross.setAttribute('visibility', 'visible');
    let dotSvg = '', rows = '';
    for (const s of series) {
      const p = s.points.find(q => q[0] === near);
      if (!p || p[1] == null || !Number.isFinite(p[1])) continue;
      dotSvg += `<circle cx="${px.toFixed(1)}" cy="${y(p[1]).toFixed(1)}" r="3.5" fill="${s.color}"/>`;
      rows += `<div class="tip-row"><span><i style="background:${s.color}"></i>${s.name}</span><b>${minus(tipfmt(p[1]))}</b></div>`;
    }
    dots.innerHTML = dotSvg;
    tip.innerHTML = `<div class="tip-title">${eventLine ? 'Day ' + (near > 0 ? '+' : '') + minus(near) : (opts.tipTitle || (d => 'Day ' + d))(near)}</div>${rows}`;
    tip.hidden = false;
    const left = (px / W) * r.width;
    tip.style.left = Math.min(r.width - tip.offsetWidth - 4, Math.max(4, left + (left > r.width / 2 ? -tip.offsetWidth - 14 : 14))) + 'px';
  });
  el.addEventListener('pointerleave', hide);
}

let resizeTimer;
let lastWidth = window.innerWidth;
window.addEventListener('resize', () => {
  if (window.innerWidth === lastWidth) return;
  lastWidth = window.innerWidth;
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => Object.entries(charts).forEach(([t, [s, o]]) => chart(t, s, o)), 120);
});

/* ---------- history ---------- */

function worst(ev) {
  let w = null;
  for (const p of ev.points) {
    const v = p[ev.coin];
    if (v != null && (w == null || v < w.price)) w = { price: v, day: p.day, date: p.date };
  }
  return w;
}

function renderTimeline() {
  $('events').innerHTML = D.events
    .map(ev => {
      const w = worst(ev);
      const dev = ((w.price - 1) * 100).toFixed(1);
      const on = ev.id === eventId;
      return `<li><button type="button" class="event ${on ? 'is-on' : ''}" data-event="${ev.id}" aria-pressed="${on}">
        <span class="event-year">${ev.date.slice(0, 4)}</span>
        <span class="event-name">${ev.name}</span>
        <span class="event-dev"><span class="coin" style="--swatch:var(--${ev.coin.toLowerCase()})">${ev.coin}</span> lowest close ${minus(dev)}%</span>
        ${ev.can_simulate ? '<span class="event-flag">Stress test available</span>' : ''}
      </button></li>`;
    })
    .join('');
}

function renderHistory() {
  const e = D.events.find(ev => ev.id === eventId);
  renderTimeline();
  $('event-title').textContent = `${e.name}, ${longDate(e.date)}`;
  const w = worst(e);
  const coinColor = cssVar('--' + e.coin.toLowerCase());
  chart(
    'history-chart',
    ['USDT', 'USDC'].map(c => ({
      name: c,
      color: cssVar('--' + c.toLowerCase()),
      strong: c === e.coin,
      points: e.points.map(p => [p.day, p[c] == null ? null : p[c]])
    })),
    {
      eventLine: true,
      xlabel: 'Days from reference date',
      baseline: 1,
      baselineLabel: 'Peg $1.00',
      yfmt: (v, dp) => '$' + v.toFixed(Math.max(2, dp)),
      tipfmt: v => '$' + v.toFixed(4),
      annotate: { x: w.day, y: w.price, color: coinColor, text: `${e.coin} $${w.price.toFixed(4)}` }
    }
  );

  $('simulation').hidden = !e.can_simulate;
  $('history-only').hidden = e.can_simulate;
  $('evidence-title').textContent = e.can_simulate ? 'USDC reserves, 28 February 2023' : 'Market prices only';
  $('evidence-body').innerHTML = e.can_simulate
    ? `<dl class="reserve">
        <div><dt>Reserve assets</dt><dd>${bn3(D.balance.reserve_total)}</dd></div>
        <div><dt>USDC outstanding</dt><dd>${bn3(D.balance.stablecoin_liabilities)}</dd></div>
        <div><dt>Net cash in model</dt><dd>${bn3(D.balance.cash)}</dd></div>
        <div><dt>Treasuries (look-through)</dt><dd>${bn3(D.balance.treasury)}</dd></div>
      </dl>
      <p class="unit">USD billion</p>
      <p>The attestation was signed on 30 March 2023, after the shock, so it serves as a look-back baseline rather than information anyone had beforehand. Net cash includes settlement adjustments assumed cleared before the shock.</p>`
    : `<p>These are daily closes only, so intraday lows do not appear.</p>
       <p>No verified reserve snapshot or bank-encumbrance data exists for this episode, and the 2023 USDC reserves are not reused here.</p>
       <p>Not every episode broke the 1% depeg threshold on a daily close.</p>`;
}

/* ---------- results ---------- */

function renderResults() {
  const p = settings();
  const all = runs();
  const ids = all.map(r => r.summary.strategy);
  if (!ids.includes(focusId)) focusId = ids.includes('combined') ? 'combined' : ids[ids.length - 1];

  segment($('focus'), 'focus', ids, focusId, s => `<i style="background:var(${strategyVar[s]})"></i>${labels[s]}`, v => {
    focusId = v;
    renderResults();
  });

  const focus = all.find(r => r.summary.strategy === focusId).summary;
  $('scenario-caption').textContent = `${p.redemption}% redeemed, cash frozen ${p.freeze} days, sales capped at ${p.sale}% a day, credit from day ${p.activation}`;

  const metrics = [
    ['Peak backlog', bn(focus.peak_unpaid_redemptions), 'USD billion unpaid at the worst point', focus.peak_unpaid_redemptions > 0],
    ['Backlog cleared', clearance(focus), 'After the last scheduled request', focus.clearance_day == null && focus.recovery_status !== 'never_backlogged'],
    ['Economic cost', bnCost(focus.total_economic_cost), 'USD billion, including cost of holding cash', false],
    ['Debt on day 30', bn(focus.ending_financing_debt), 'USD billion, principal plus interest', false]
  ];
  $('metrics').innerHTML = metrics
    .map(([k, v, u, bad]) => `<div class="ledger-cell ${bad ? 'is-red' : ''} ${/^[\d.,-]+$/.test(v) ? '' : 'is-text'}"><dt>${k}</dt><dd><span class="figure">${minus(v)}</span><span class="unit">${u}</span></dd></div>`)
    .join('');

  const insolvent = all.filter(r => r.summary.solvency_warning).map(r => labels[r.summary.strategy]);
  $('risk-note').hidden = !insolvent.length;
  $('risk-note').innerHTML = `<p><strong>Solvency warning.</strong> Equity turns negative within 30 days for: ${insolvent.join(', ')}. Insolvency resolution is not modelled, so the paths after that point are accounting projections, not payments the issuer could actually make.</p>`;

  $('strategy-legend').innerHTML = ids.map(s => `<li style="--swatch:var(${strategyVar[s]})">${labels[s]}</li>`).join('');

  const series = field =>
    all.map(r => ({
      name: labels[r.summary.strategy],
      color: colorOf(r.summary.strategy),
      strong: r.summary.strategy === focusId,
      points: r.path.map(v => {
        const raw = v[fields.indexOf(field)];
        return [v[0], raw == null ? null : raw / (field === 'net_reserve_coverage' ? 0.01 : 1e9)];
      })
    }));

  chart('queue-chart', series('unpaid_redemptions'), { tipfmt: v => v.toFixed(3) + ' bn' });

  const [, title, sub] = SECONDARY[secondaryId];
  $('secondary-title').textContent = title;
  $('secondary-sub').textContent = sub;
  const isCov = secondaryId === 'net_reserve_coverage';
  chart('secondary-chart', series(secondaryId), {
    includeZero: !isCov,
    yfmt: (v, dp) => v.toFixed(dp) + (isCov ? '%' : ''),
    tipfmt: v => (isCov ? v.toFixed(3) + '%' : v.toFixed(3) + ' bn')
  });

  $('comparison').innerHTML = all
    .map(r => {
      const s = r.summary;
      return `<tr class="${s.strategy === focusId ? 'is-focus' : ''}">
        <th scope="row"><i style="background:var(${strategyVar[s.strategy]})"></i>${labels[s.strategy]}</th>
        <td>${clearance(s)}</td><td>${bn(s.peak_unpaid_redemptions)}</td><td>${bn(s.unpaid_dollar_days)}</td>
        <td>${bnCost(s.total_economic_cost)}</td><td>${bn(s.ending_financing_debt)}</td>
        <td class="${s.min_net_coverage < 1 ? 'red' : ''}">${pct(s.min_net_coverage)}</td></tr>`;
    })
    .join('');

  chart(
    'timing-chart',
    ['credit_line', 'combined'].map(s => ({
      name: labels[s],
      color: colorOf(s),
      strong: true,
      points: [1, 3, 5, 10].map(a => [a, D.grid[key({ ...p, activation: a })].find(r => r.summary.strategy === s).summary.peak_unpaid_redemptions / 1e9])
    })),
    { xlabel: 'Day the credit line opens', xticks: [1, 3, 5, 10], tipTitle: d => 'Credit from day ' + d, tipfmt: v => v.toFixed(3) + ' bn' }
  );

  $('boundaries').innerHTML = Object.keys(labels)
    .map(s => D.boundaries.find(b => b.blocked_days === p.freeze && Math.abs(b.daily_sale_percent - p.sale) < 1e-9 && b.strategy === s))
    .map(
      b => `<tr><th scope="row"><i style="background:var(${strategyVar[b.strategy]})"></i>${labels[b.strategy]}</th>
        <td>${b.first_tested_failure_percent == null ? 'None up to 80%' : `${b.previous_tested_clear_percent ?? 0}% and ${b.first_tested_failure_percent}%`}</td>
        <td class="${b.first_tested_negative_equity_percent == null ? '' : 'red'}">${b.first_tested_negative_equity_percent == null ? 'None up to 80%' : b.first_tested_negative_equity_percent + '%'}</td></tr>`
    )
    .join('');
}

/* ---------- exports ---------- */

function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function csv(rows) {
  const cols = Object.keys(rows[0]);
  const cell = v => (v == null ? '' : `"${String(v).replaceAll('"', '""')}"`);
  return '﻿' + [cols.map(cell).join(','), ...rows.map(r => cols.map(c => cell(r[c])).join(','))].join('\r\n');
}

/* ---------- wiring ---------- */

$('events').addEventListener('click', e => {
  const b = e.target.closest('[data-event]');
  if (!b) return;
  eventId = b.dataset.event;
  renderHistory();
  if (!$('simulation').hidden) renderResults();
  document.querySelector(`[data-event="${eventId}"]`).focus();
});

$('back-svb').addEventListener('click', () => {
  eventId = 'svb2023';
  renderHistory();
  renderResults();
  $('simulation').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
});

document.querySelectorAll('.check input').forEach(e => e.addEventListener('change', renderResults));

$('reset').addEventListener('click', () => {
  for (const [id, v] of Object.entries(DEFAULTS)) {
    const r = document.querySelector(`input[name="${id}"][value="${v}"]`);
    if (r) r.checked = true;
  }
  document.querySelectorAll('.check input').forEach(e => (e.checked = true));
  focusId = 'combined';
  secondaryId = 'financing_debt';
  document.querySelector('input[name="secondary"][value="financing_debt"]').checked = true;
  renderResults();
});

$('export-results').addEventListener('click', () => download('intervention_results.csv', csv(runs().map(r => r.summary)), 'text/csv;charset=utf-8'));

$('export-paths').addEventListener('click', () =>
  download(
    'daily_paths.csv',
    csv(runs().flatMap(r => r.path.map(v => Object.fromEntries([['strategy', r.summary.strategy], ...fields.map((f, i) => [f, v[i]])])))),
    'text/csv;charset=utf-8'
  )
);

$('export-config').addEventListener('click', () =>
  download(
    'scenario_config.json',
    JSON.stringify(
      {
        event_id: eventId,
        configuration_key: key(settings()),
        selected_strategies: selected(),
        settings: settings(),
        balance: D.balance,
        policy: { ...D.policy, credit_activation_day: settings().activation },
        fixed_scenario: D.manifest.scenario_fixed,
        code_sha256: D.manifest.code_sha256,
        input_sha256: D.manifest.input_sha256,
        limits: D.manifest.limits
      },
      null,
      2
    ),
    'application/json'
  )
);

buildControls();
renderHistory();
renderResults();
if (document.fonts) document.fonts.ready.then(() => Object.entries(charts).forEach(([t, [s, o]]) => chart(t, s, o)));
