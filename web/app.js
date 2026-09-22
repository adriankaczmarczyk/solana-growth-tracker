'use strict';

const COLUMNS = [
  { key: 'rank', label: '#', cls: 'rank', sortable: false },
  { key: 'name', label: 'Protocol', cls: 'left', sortable: true },
  { key: 'momentum', label: 'Score', sortable: true },
  { key: 'trend', label: 'Trend', sortable: true, hideSm: true },
  { key: 'tvl', label: 'TVL', sortable: true },
  { key: 'tvl_change_7d', label: 'TVL 7d', sortable: true, hideSm: true },
  { key: 'tvl_change_30d', label: 'TVL 30d', sortable: true, hideSm: true },
  { key: 'volume_24h', label: 'Vol 24h', sortable: true },
  { key: 'volume_change_7d', label: 'Vol 7d/7d', sortable: true, hideSm: true },
  { key: 'fees_30d', label: 'Fees 30d', sortable: true, hideSm: true },
];

const state = {
  snapshot: null,
  protocols: [],
  sort: 'momentum',
  asc: false,
  search: '',
  category: '',
  includeSmall: false,
  days: 90,
  open: null,
};

// --- formatting ------------------------------------------------------------

function usd(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '–';
  const abs = Math.abs(value);
  const units = [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']];
  for (const [size, suffix] of units) {
    if (abs >= size) return '$' + (value / size).toFixed(digits) + suffix;
  }
  return '$' + value.toFixed(0);
}

function pct(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '<span class="muted">–</span>';
  const cls = value >= 0 ? 'up' : 'down';
  return `<span class="${cls}">${value >= 0 ? '+' : ''}${value.toFixed(1)}%</span>`;
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function volume24h(protocol) {
  const values = [protocol.volume_24h, protocol.aggregator_volume_24h].filter((v) => v != null);
  return values.length ? Math.max(...values) : null;
}

// --- charts ----------------------------------------------------------------

function areaChart(points, { width, height = 190, pad = 28, interactive = false }) {
  if (!points || points.length < 2) return '<div class="empty">No history available.</div>';

  const values = points.map((p) => p.tvl);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const innerW = width - pad * 2;
  const innerH = height - pad;

  const x = (i) => pad + (i / (points.length - 1)) * innerW;
  const y = (v) => pad / 2 + innerH - ((v - min) / span) * innerH;

  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.tvl).toFixed(1)}`).join('');
  const area = `${line}L${x(points.length - 1).toFixed(1)},${height}L${x(0).toFixed(1)},${height}Z`;
  const rising = values[values.length - 1] >= values[0];
  const stroke = rising ? '#14f195' : '#ff5c7c';
  const id = 'g' + Math.random().toString(36).slice(2, 8);

  const ticks = [max, min + span / 2, min].map((v, i) => {
    const ty = pad / 2 + (innerH / 2) * i;
    return `<text x="4" y="${(ty + 4).toFixed(1)}" fill="#8b90a4" font-size="10">${usd(v, 1)}</text>
            <line x1="${pad}" x2="${width - 4}" y1="${ty.toFixed(1)}" y2="${ty.toFixed(1)}" stroke="#242836" stroke-dasharray="3 4"/>`;
  }).join('');

  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" ${interactive ? 'class="interactive"' : ''}>
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${stroke}" stop-opacity=".35"/>
      <stop offset="100%" stop-color="${stroke}" stop-opacity="0"/>
    </linearGradient></defs>
    ${ticks}
    <path d="${area}" fill="url(#${id})"/>
    <path d="${line}" fill="none" stroke="${stroke}" stroke-width="2" stroke-linejoin="round"/>
  </svg>`;
}

function sliceHistory(history, days) {
  if (!days || !history.length) return history;
  const cutoff = history[history.length - 1].date - days * 86400;
  const window = history.filter((p) => p.date >= cutoff);
  return window.length > 1 ? window : history;
}

function renderChainChart() {
  const host = document.getElementById('chain-chart');
  const history = state.snapshot.chain.tvl_history || [];
  const points = sliceHistory(history, state.days);
  host.innerHTML = areaChart(points, { width: Math.max(host.clientWidth || 900, 320), interactive: true });
}

// --- KPIs ------------------------------------------------------------------

function renderKpis() {
  const chain = state.snapshot.chain;
  const cards = [
    { label: 'Chain TVL', value: usd(chain.tvl), delta: `7d ${pct(chain.tvl_change_7d)} · 30d ${pct(chain.tvl_change_30d)}` },
    { label: 'DEX volume 24h', value: usd(chain.dex_volume_24h), delta: `7d/7d ${pct(chain.dex_volume_change_7d)}` },
    { label: 'Aggregator volume 24h', value: usd(chain.aggregator_volume_24h), delta: `7d/7d ${pct(chain.aggregator_volume_change_7d)}` },
    { label: 'Fees 24h', value: usd(chain.fees_24h), delta: `30d ${usd(chain.fees_30d)}` },
    { label: 'Revenue 24h', value: usd(chain.revenue_24h), delta: `${state.snapshot.protocols.length} protocols tracked` },
  ];
  document.getElementById('kpis').innerHTML = cards.map((card) => `
    <div class="kpi">
      <div class="label">${card.label}</div>
      <div class="value">${card.value}</div>
      <div class="delta muted">${card.delta}</div>
    </div>`).join('');
}

// --- table -----------------------------------------------------------------

function renderHead() {
  document.getElementById('head').innerHTML = COLUMNS.map((col) => {
    const classes = [col.cls, col.hideSm ? 'hide-sm' : '', state.sort === col.key ? 'sorted' : '',
      state.sort === col.key && state.asc ? 'asc' : ''].filter(Boolean).join(' ');
    return `<th class="${classes}" data-key="${col.key}" data-sortable="${col.sortable}">${col.label}</th>`;
  }).join('');
}

function visibleProtocols() {
  const needle = state.search.trim().toLowerCase();
  return state.protocols.filter((p) => {
    if (!state.includeSmall && !p.established) return false;
    if (state.category && p.category !== state.category) return false;
    if (needle && !(p.name.toLowerCase().includes(needle) || (p.symbol || '').toLowerCase().includes(needle))) return false;
    if (state.sort === 'momentum' && p.momentum === null) return false;
    return true;
  });
}

function sorted(list) {
  const key = state.sort;
  const direction = state.asc ? 1 : -1;
  return list.slice().sort((a, b) => {
    let av = key === 'volume_24h' ? volume24h(a) : a[key];
    let bv = key === 'volume_24h' ? volume24h(b) : b[key];
    if (typeof av === 'string' || typeof bv === 'string') {
      return String(av ?? '').localeCompare(String(bv ?? '')) * direction;
    }
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    return (av - bv) * direction;
  });
}

function rowHtml(protocol, index) {
  const score = protocol.momentum;
  const scoreCell = score === null || score === undefined
    ? '<span class="muted">–</span>'
    : `<div class="score-cell"><span>${score.toFixed(1)}</span>
         <span class="score-bar"><i style="width:${Math.max(2, Math.min(100, score))}%"></i></span></div>`;
  const logo = protocol.logo
    ? `<img src="${escapeHtml(protocol.logo)}" alt="" loading="lazy" onerror="this.remove()">`
    : '';
  return `<tr data-slug="${escapeHtml(protocol.slug)}" class="${state.open === protocol.slug ? 'open' : ''}">
    <td class="rank">${index + 1}</td>
    <td class="left"><div class="name">${logo}<div>
      <div>${escapeHtml(protocol.name)}</div>
      <div class="cat">${escapeHtml(protocol.category)}</div>
    </div></div></td>
    <td>${scoreCell}</td>
    <td class="hide-sm"><span class="badge ${escapeHtml(protocol.trend)}">${escapeHtml(protocol.trend)}</span></td>
    <td>${usd(protocol.tvl)}</td>
    <td class="hide-sm">${pct(protocol.tvl_change_7d)}</td>
    <td class="hide-sm">${pct(protocol.tvl_change_30d)}</td>
    <td>${usd(volume24h(protocol))}</td>
    <td class="hide-sm">${pct(protocol.volume_change_7d)}</td>
    <td class="hide-sm">${usd(protocol.fees_30d)}</td>
  </tr>`;
}

function detailHtml(protocol) {
  const stats = [
    ['Volume 7d', usd(protocol.volume_7d)],
    ['Volume 30d', usd(protocol.volume_30d)],
    ['Fees 24h', usd(protocol.fees_24h)],
    ['Revenue 30d', usd(protocol.revenue_30d)],
    ['Market cap', usd(protocol.mcap)],
    ['TVL 90d', pct(protocol.tvl_change_90d)],
    ['Capital turnover', protocol.capital_turnover ? protocol.capital_turnover.toFixed(1) + 'x' : '–'],
    ['Vol 30d/30d', pct(protocol.volume_change_30d)],
  ];
  const link = protocol.url
    ? `<a href="${escapeHtml(protocol.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(protocol.url)}</a>`
    : '<span class="muted">no website listed</span>';
  const chart = protocol.tvl_history && protocol.tvl_history.length > 1
    ? areaChart(sliceHistory(protocol.tvl_history, 180), { width: 620, height: 160 })
    : '<div class="empty">TVL history is fetched only for the largest protocols.</div>';

  return `<tr class="detail"><td colspan="${COLUMNS.length}">
    <div class="detail-grid">
      <div>${chart}</div>
      <div>
        <div class="detail-stats">
          ${stats.map(([label, value]) => `<div><span>${label}</span><span>${value}</span></div>`).join('')}
        </div>
        <p class="stamp" style="margin-top:14px">${link}</p>
        <p class="stamp"><a href="https://defillama.com/protocol/${escapeHtml(protocol.slug)}" target="_blank" rel="noopener noreferrer">View on DefiLlama →</a></p>
      </div>
    </div>
  </td></tr>`;
}

function renderTable() {
  const list = sorted(visibleProtocols());
  const body = document.getElementById('rows');
  const rows = [];
  list.forEach((protocol, index) => {
    rows.push(rowHtml(protocol, index));
    if (state.open === protocol.slug) rows.push(detailHtml(protocol));
  });
  body.innerHTML = rows.join('');
  document.getElementById('empty').hidden = list.length > 0;
  document.getElementById('count').textContent = `${list.length} protocols`;
  renderHead();
}

// --- wiring ----------------------------------------------------------------

function renderCategories() {
  const categories = [...new Set(state.protocols.map((p) => p.category))].sort();
  const select = document.getElementById('category');
  select.innerHTML = '<option value="">All categories</option>' +
    categories.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
}

function bind() {
  document.getElementById('tabs').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-sort]');
    if (!button) return;
    document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('on', b === button));
    state.sort = button.dataset.sort;
    state.asc = false;
    state.open = null;
    renderTable();
  });

  document.getElementById('range').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-days]');
    if (!button) return;
    document.querySelectorAll('#range button').forEach((b) => b.classList.toggle('on', b === button));
    state.days = Number(button.dataset.days);
    renderChainChart();
  });

  document.getElementById('head').addEventListener('click', (event) => {
    const th = event.target.closest('th[data-sortable="true"]');
    if (!th) return;
    if (state.sort === th.dataset.key) state.asc = !state.asc;
    else { state.sort = th.dataset.key; state.asc = false; }
    document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.sort === state.sort));
    renderTable();
  });

  document.getElementById('rows').addEventListener('click', (event) => {
    const row = event.target.closest('tr[data-slug]');
    if (!row) return;
    state.open = state.open === row.dataset.slug ? null : row.dataset.slug;
    renderTable();
  });

  let searchTimer;
  document.getElementById('search').addEventListener('input', (event) => {
    clearTimeout(searchTimer);
    const value = event.target.value;
    searchTimer = setTimeout(() => { state.search = value; state.open = null; renderTable(); }, 120);
  });

  document.getElementById('category').addEventListener('change', (event) => {
    state.category = event.target.value;
    state.open = null;
    renderTable();
  });

  document.getElementById('small').addEventListener('change', (event) => {
    state.includeSmall = event.target.checked;
    renderTable();
  });

  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderChainChart, 150);
  });
}

async function init() {
  try {
    const response = await fetch('data/snapshot.json', { cache: 'no-cache' });
    if (!response.ok) throw new Error(`snapshot.json returned ${response.status}`);
    state.snapshot = await response.json();
  } catch (error) {
    document.getElementById('stamp').textContent = 'Failed to load data — run: soltracker export';
    document.getElementById('empty').hidden = false;
    document.getElementById('empty').textContent = String(error);
    return;
  }

  state.protocols = state.snapshot.protocols;
  document.getElementById('stamp').textContent =
    'snapshot ' + state.snapshot.generated_at.replace('T', ' ').replace('+00:00', ' UTC');

  renderKpis();
  renderChainChart();
  renderCategories();
  renderTable();
  bind();
}

init();
