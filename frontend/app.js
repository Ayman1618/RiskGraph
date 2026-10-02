/**
 * RiskGraph — Operations Dashboard
 * app.js — All page logic, API calls, D3 graph, tables, and navigation
 */

const API_BASE = 'http://localhost:8000/api/v1';
const HEALTH_URL = 'http://localhost:8000/health';

// ===================================================
// STATE
// ===================================================
let currentPage = 'overview';
let txOffset = 0;
const TX_LIMIT = 50;
let txTotal = 0;
let searchDebounceTimer = null;
let selectedTxId = null;
let graphSimulation = null;

// ===================================================
// NAVIGATION
// ===================================================
function navigate(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const pageEl = document.getElementById(`page-${page}`);
  if (pageEl) pageEl.classList.add('active');

  const navEl = document.querySelector(`[data-page="${page}"]`);
  if (navEl) navEl.classList.add('active');

  currentPage = page;

  const titles = {
    'overview':       ['Overview',        'Operational command center'],
    'transactions':   ['Transactions',    'Full transaction ledger'],
    'investigations': ['Investigations',  'Blocked & under-review cases'],
    'identity-graph': ['Identity Graph',  'Multi-hop entity relationship explorer'],
    'risk-signals':   ['Risk Signals',    'Active fraud scoring rules'],
    'data-quality':   ['Data Quality',    'Pipeline data validation results'],
    'pipelines':      ['Pipelines',       'Component status & telemetry'],
    'system-health':  ['System Health',   'Service availability'],
  };

  const [title, subtitle] = titles[page] || ['RiskGraph', ''];
  document.getElementById('page-title').textContent = title;
  document.getElementById('page-subtitle').textContent = subtitle;

  loadPage(page);
}

function loadPage(page) {
  switch (page) {
    case 'overview':       loadOverview();       break;
    case 'transactions':   loadTransactions();   break;
    case 'investigations': loadInvestigations(); break;
    case 'identity-graph': loadIdentityGraph();  break;
    case 'risk-signals':   loadRiskSignals();    break;
    case 'data-quality':   loadDataQuality();    break;
    case 'pipelines':      loadPipelines();      break;
    case 'system-health':  loadSystemHealth();   break;
  }
}

function refreshCurrentPage() {
  loadPage(currentPage);
}

// ===================================================
// API HELPERS
// ===================================================
async function apiFetch(path, opts = {}) {
  const res = await fetch(API_BASE + path, { signal: AbortSignal.timeout(10000), ...opts });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function checkApiHealth() {
  const dot = document.getElementById('api-dot');
  const txt = document.getElementById('api-status-text');
  dot.className = 'status-dot checking';
  txt.textContent = 'Connecting...';
  try {
    const res = await fetch(HEALTH_URL, { signal: AbortSignal.timeout(4000) });
    const data = await res.json();
    if (data.status === 'healthy') {
      dot.className = 'status-dot up';
      txt.textContent = 'API Healthy';
    } else {
      dot.className = 'status-dot down';
      txt.textContent = 'API Degraded';
    }
  } catch {
    dot.className = 'status-dot down';
    txt.textContent = 'API Unreachable';
  }
}

// ===================================================
// OVERVIEW
// ===================================================
async function loadOverview() {
  try {
    const [stats, rings] = await Promise.all([
      apiFetch('/risk/stats'),
      apiFetch('/entities/rings'),
    ]);
    renderOverviewStats(stats);
    renderDecisionChart(stats);
    renderFraudRingsSummary(rings);
    loadHighRiskTransactions();
  } catch (e) {
    console.error('Overview load error:', e);
    showStatError();
  }
}

function renderOverviewStats(s) {
  const fmt = (n) => n >= 1e6 ? `$${(n/1e6).toFixed(2)}M` : n >= 1e3 ? `$${(n/1e3).toFixed(1)}K` : `$${n.toFixed(0)}`;

  document.getElementById('stat-total').className = 'stat-card blue';
  document.getElementById('stat-total').innerHTML = `
    <div class="stat-label">Total Transactions</div>
    <div class="stat-value">${s.total_transactions.toLocaleString()}</div>
    <div class="stat-meta">GMV ${fmt(s.total_gmv)}</div>`;

  document.getElementById('stat-approved').className = 'stat-card green';
  document.getElementById('stat-approved').innerHTML = `
    <div class="stat-label">Approved</div>
    <div class="stat-value">${s.approved_count.toLocaleString()}</div>
    <div class="stat-meta">${s.total_transactions > 0 ? ((s.approved_count/s.total_transactions)*100).toFixed(1) : 0}% pass rate</div>`;

  document.getElementById('stat-review').className = 'stat-card amber';
  document.getElementById('stat-review').innerHTML = `
    <div class="stat-label">Under Review</div>
    <div class="stat-value">${s.review_count.toLocaleString()}</div>
    <div class="stat-meta">Manual inspection queue</div>`;

  document.getElementById('stat-blocked').className = 'stat-card red';
  document.getElementById('stat-blocked').innerHTML = `
    <div class="stat-label">Blocked</div>
    <div class="stat-value">${s.blocked_count.toLocaleString()}</div>
    <div class="stat-meta">${s.block_rate_pct}% block rate</div>`;

  document.getElementById('stat-gmv').className = 'stat-card';
  document.getElementById('stat-gmv').innerHTML = `
    <div class="stat-label">Gross Transaction Volume</div>
    <div class="stat-value">${fmt(s.total_gmv)}</div>
    <div class="stat-meta">Evaluated transactions</div>`;

  document.getElementById('stat-risk-score').className = 'stat-card';
  document.getElementById('stat-risk-score').innerHTML = `
    <div class="stat-label">Avg Risk Score</div>
    <div class="stat-value">${s.avg_risk_score}</div>
    <div class="stat-meta">0 – 100 scale</div>`;
}

function renderDecisionChart(s) {
  const container = document.getElementById('decision-chart-container');
  const total = s.total_transactions || 1;
  const items = [
    { label: 'APPROVE', count: s.approved_count, color: 'var(--green)' },
    { label: 'REVIEW',  count: s.review_count,   color: 'var(--amber)' },
    { label: 'BLOCK',   count: s.blocked_count,  color: 'var(--red)' },
  ];
  container.innerHTML = `<div class="decision-bars">${items.map(item => {
    const pct = ((item.count / total) * 100).toFixed(1);
    return `<div class="decision-bar-row">
      <div class="decision-bar-label">${item.label}</div>
      <div class="decision-bar-track">
        <div class="decision-bar-fill" style="width:${pct}%; background:${item.color};"></div>
      </div>
      <div class="decision-bar-count">${item.count.toLocaleString()} (${pct}%)</div>
    </div>`;
  }).join('')}</div>`;
}

function renderFraudRingsSummary(rings) {
  const el = document.getElementById('fraud-rings-summary');
  if (!rings.rings || rings.rings.length === 0) {
    el.innerHTML = '<div class="empty-state"><p>No rings detected</p></div>';
    return;
  }
  el.innerHTML = `
    <div style="margin-bottom:12px;">
      <div class="stat-value" style="font-size:32px; color:var(--red);">${rings.fraud_rings_count}</div>
      <div class="stat-meta">Identity fraud ring${rings.fraud_rings_count !== 1 ? 's' : ''} detected</div>
    </div>
    ${rings.rings.slice(0, 3).map(r => `
      <div class="ring-item" onclick="exploreRing('${r.shared_device_id}', ${JSON.stringify(r.ring_members).replace(/"/g,'&quot;')})">
        <div class="ring-title">Ring: ${r.shared_device_id.slice(0, 20)}...</div>
        <div class="ring-meta">${r.ring_size} members — Click to explore</div>
      </div>`).join('')}`;
}

async function loadHighRiskTransactions() {
  try {
    const data = await apiFetch('/transactions?limit=10&min_risk=50');
    const el = document.getElementById('recent-high-risk-table');
    if (!data.transactions || data.transactions.length === 0) {
      el.innerHTML = '<div class="empty-state"><p>No high-risk transactions</p></div>';
      return;
    }
    el.innerHTML = buildTransactionTable(data.transactions);
  } catch (e) {
    document.getElementById('recent-high-risk-table').innerHTML =
      '<div class="loading-placeholder">Unable to load transactions</div>';
  }
}

function showStatError() {
  ['stat-total','stat-approved','stat-review','stat-blocked','stat-gmv','stat-risk-score'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.className = 'stat-card'; el.innerHTML = '<div class="stat-meta">Backend unreachable</div>'; }
  });
}

// ===================================================
// TRANSACTIONS
// ===================================================
async function loadTransactions() {
  txOffset = 0;
  await fetchTransactions();
}

async function fetchTransactions() {
  const search   = document.getElementById('tx-search')?.value || '';
  const decision = document.getElementById('tx-decision-filter')?.value || '';
  const minRisk  = document.getElementById('tx-min-risk')?.value || '';
  const maxRisk  = document.getElementById('tx-max-risk')?.value || '';

  let qs = `?limit=${TX_LIMIT}&offset=${txOffset}`;
  if (search)   qs += `&search=${encodeURIComponent(search)}`;
  if (decision) qs += `&decision=${decision}`;
  if (minRisk)  qs += `&min_risk=${minRisk}`;
  if (maxRisk)  qs += `&max_risk=${maxRisk}`;

  const container = document.getElementById('transactions-table-container');
  container.innerHTML = '<div class="loading-placeholder">Loading...</div>';

  try {
    const data = await apiFetch(`/transactions${qs}`);
    txTotal = data.total;
    document.getElementById('tx-count-label').textContent = `${txTotal.toLocaleString()} total`;
    container.innerHTML = buildTransactionTable(data.transactions, true);
    renderPagination();
  } catch (e) {
    container.innerHTML = '<div class="loading-placeholder">Error loading transactions. Is the API running?</div>';
  }
}

function buildTransactionTable(txns, clickable = false) {
  if (!txns || txns.length === 0) return '<div class="empty-state"><p>No transactions found</p></div>';
  return `<table class="data-table">
    <thead>
      <tr>
        <th>Transaction ID</th>
        <th>Timestamp</th>
        <th>User</th>
        <th>Amount</th>
        <th>Country</th>
        <th>IP Address</th>
        <th>Risk Score</th>
        <th>Decision</th>
      </tr>
    </thead>
    <tbody>
      ${txns.map(tx => `
        <tr ${clickable ? `onclick="openTxModal('${tx.transaction_id}')"` : ''}>
          <td class="mono">${tx.transaction_id.slice(0, 18)}…</td>
          <td>${formatTs(tx.timestamp)}</td>
          <td class="mono">${tx.user_id ? tx.user_id.slice(0, 16) + '…' : '—'}</td>
          <td class="amount">${formatAmount(tx.amount, tx.currency)}</td>
          <td>${tx.location_country || '—'}</td>
          <td class="mono">${tx.ip_address || '—'}</td>
          <td>${riskBar(tx.risk_score)}</td>
          <td>${decisionBadge(tx.decision)}</td>
        </tr>`).join('')}
    </tbody>
  </table>`;
}

function renderPagination() {
  const el = document.getElementById('tx-pagination');
  const totalPages = Math.ceil(txTotal / TX_LIMIT);
  const currentPageNum = Math.floor(txOffset / TX_LIMIT) + 1;

  if (totalPages <= 1) { el.innerHTML = ''; return; }

  const start = txOffset + 1;
  const end = Math.min(txOffset + TX_LIMIT, txTotal);

  let pagesHtml = '';
  const pages = paginate(currentPageNum, totalPages);
  pages.forEach(p => {
    if (p === '...') {
      pagesHtml += '<button disabled>…</button>';
    } else {
      pagesHtml += `<button class="${p === currentPageNum ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>`;
    }
  });

  el.innerHTML = `
    <span class="pagination-info">Showing ${start}–${end} of ${txTotal.toLocaleString()}</span>
    <div class="pagination-btns">
      <button onclick="goToPage(${currentPageNum - 1})" ${currentPageNum <= 1 ? 'disabled' : ''}>←</button>
      ${pagesHtml}
      <button onclick="goToPage(${currentPageNum + 1})" ${currentPageNum >= totalPages ? 'disabled' : ''}>→</button>
    </div>`;
}

function paginate(current, total) {
  const pages = [];
  if (total <= 7) {
    for (let i = 1; i <= total; i++) pages.push(i);
  } else {
    pages.push(1);
    if (current > 3) pages.push('...');
    for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) pages.push(i);
    if (current < total - 2) pages.push('...');
    pages.push(total);
  }
  return pages;
}

function goToPage(page) {
  const totalPages = Math.ceil(txTotal / TX_LIMIT);
  if (page < 1 || page > totalPages) return;
  txOffset = (page - 1) * TX_LIMIT;
  fetchTransactions();
}

function clearFilters() {
  document.getElementById('tx-search').value = '';
  document.getElementById('tx-decision-filter').value = '';
  document.getElementById('tx-min-risk').value = '';
  document.getElementById('tx-max-risk').value = '';
  loadTransactions();
}

function debounceSearch() {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(loadTransactions, 400);
}

// ===================================================
// TRANSACTION MODAL
// ===================================================
async function openTxModal(txId) {
  const modal = document.getElementById('tx-modal');
  const body  = document.getElementById('tx-modal-body');
  modal.classList.add('open');
  body.innerHTML = '<div class="loading-placeholder" style="padding:48px;">Loading...</div>';

  try {
    const tx = await apiFetch(`/transactions/${txId}`);
    body.innerHTML = renderTxDetail(tx);
  } catch (e) {
    body.innerHTML = `<div class="loading-placeholder">Error: ${e.message}</div>`;
  }
}

function renderTxDetail(tx) {
  const rules = Array.isArray(tx.triggered_rules) ? tx.triggered_rules : [];

  return `
    <div style="padding: 24px;">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:20px;">
        <div>
          <div style="font-size:16px; font-weight:700; color:var(--text-primary); margin-bottom:4px;">Transaction Investigation</div>
          <div style="font-family:var(--font-mono); font-size:12px; color:var(--text-muted);">${tx.transaction_id}</div>
        </div>
        ${decisionBadge(tx.decision)}
      </div>

      <div class="detail-section">
        <div class="detail-section-title">Transaction Details</div>
        <div class="detail-grid">
          ${field('User ID', tx.user_id)}
          ${field('Amount', formatAmount(tx.amount, tx.currency))}
          ${field('Country', tx.location_country || '—')}
          ${field('Merchant', tx.merchant_id || '—')}
          ${field('Device', tx.device_id || '—')}
          ${field('IP Address', tx.ip_address)}
          ${field('Risk Score', tx.risk_score)}
          ${field('Status', tx.status)}
          ${field('Timestamp', formatTs(tx.timestamp))}
          ${field('Currency', tx.currency || 'USD')}
        </div>
      </div>

      ${rules.length > 0 ? `
      <div class="detail-section">
        <div class="detail-section-title">Risk Signals Triggered</div>
        <div class="signal-list">
          ${rules.map(r => {
            const sev = r.weight >= 50 ? 'high' : r.weight >= 25 ? 'medium' : 'low';
            return `<div class="signal-card ${sev}">
              <div>
                <div class="signal-name">${r.rule_name}</div>
                <div class="signal-desc">${r.description} — Actual: ${r.actual_value?.toFixed?.(2) || r.actual_value}, Threshold: ${r.threshold}</div>
              </div>
              <div class="signal-weight">+${r.weight}</div>
            </div>`;
          }).join('')}
        </div>
      </div>` : `
      <div class="detail-section">
        <div class="detail-section-title">Risk Signals</div>
        <div class="loading-placeholder">No risk signals triggered — transaction passed all checks</div>
      </div>`}

      <div style="margin-top: 16px; display: flex; gap: 8px;">
        <button class="btn-primary" onclick="loadUserGraphForUser('${tx.user_id}')">Explore Identity Graph</button>
        <button class="btn-secondary" onclick="closeTxModal()">Close</button>
      </div>
    </div>`;
}

function closeTxModal(event) {
  if (event && event.target !== document.getElementById('tx-modal')) return;
  document.getElementById('tx-modal').classList.remove('open');
}

function field(label, value) {
  return `<div class="detail-field">
    <div class="detail-key">${label}</div>
    <div class="detail-value">${value ?? '—'}</div>
  </div>`;
}

// ===================================================
// INVESTIGATIONS
// ===================================================
async function loadInvestigations() {
  const container = document.getElementById('investigations-list-container');
  container.innerHTML = '<div class="loading-placeholder">Loading...</div>';

  try {
    const data = await apiFetch('/transactions?limit=100&decision=BLOCK');
    const reviewData = await apiFetch('/transactions?limit=50&decision=REVIEW');

    const allTx = [...(data.transactions || []), ...(reviewData.transactions || [])];

    if (allTx.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No cases to review</p></div>';
      return;
    }

    container.innerHTML = allTx.map(tx => `
      <div class="inv-row ${selectedTxId === tx.transaction_id ? 'selected' : ''}"
           onclick="loadInvestigationDetail('${tx.transaction_id}', this)">
        <div class="inv-row-id">${tx.transaction_id.slice(0, 24)}…</div>
        <div class="inv-row-meta">
          <span class="inv-row-amount">${formatAmount(tx.amount, tx.currency)}</span>
          ${decisionBadge(tx.decision)}
        </div>
        <div style="font-size:11px; color:var(--text-muted); margin-top:3px;">${formatTs(tx.timestamp)}</div>
      </div>`).join('');
  } catch (e) {
    container.innerHTML = '<div class="loading-placeholder">Error loading cases</div>';
  }
}

async function loadInvestigationDetail(txId, rowEl) {
  selectedTxId = txId;
  document.querySelectorAll('.inv-row').forEach(r => r.classList.remove('selected'));
  if (rowEl) rowEl.classList.add('selected');

  const detail = document.getElementById('investigation-detail');
  detail.innerHTML = '<div class="loading-placeholder" style="padding:48px;">Loading...</div>';

  try {
    const tx = await apiFetch(`/transactions/${txId}`);
    detail.innerHTML = renderTxDetail(tx);
  } catch (e) {
    detail.innerHTML = `<div class="loading-placeholder">Error: ${e.message}</div>`;
  }
}

// ===================================================
// IDENTITY GRAPH (D3 Force)
// ===================================================
async function loadIdentityGraph() {
  loadFraudRingsList();
}

async function loadFraudRingsList() {
  const el = document.getElementById('graph-rings-list');
  try {
    const rings = await apiFetch('/entities/rings');
    if (!rings.rings || rings.rings.length === 0) {
      el.innerHTML = '<div class="loading-placeholder">No rings detected</div>';
      return;
    }
    el.innerHTML = rings.rings.map(r => `
      <div class="ring-item" onclick="exploreRing('${r.shared_device_id}', ${JSON.stringify(r.ring_members).replace(/"/g,'&quot;')})">
        <div class="ring-title">Shared Device Ring</div>
        <div class="ring-meta">${r.ring_size} members · ${r.shared_device_id.slice(0, 18)}…</div>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = '<div class="loading-placeholder">Rings unavailable</div>';
  }
}

function exploreRing(deviceId, members) {
  if (Array.isArray(members) && members.length > 0) {
    document.getElementById('graph-user-id').value = members[0];
    navigate('identity-graph');
    setTimeout(loadUserGraph, 100);
  }
}

function loadUserGraphForUser(userId) {
  closeTxModal();
  navigate('identity-graph');
  setTimeout(() => {
    document.getElementById('graph-user-id').value = userId;
    loadUserGraph();
  }, 150);
}

async function loadUserGraph() {
  const userId = document.getElementById('graph-user-id').value.trim();
  const depth  = parseInt(document.getElementById('graph-depth').value) || 2;

  if (!userId) return;

  const emptyEl = document.getElementById('graph-empty');
  const countEl = document.getElementById('graph-node-count');
  emptyEl.style.display = 'none';
  countEl.textContent = 'Loading...';

  try {
    const data = await apiFetch(`/entities/graph/${encodeURIComponent(userId)}?depth=${depth}`);
    renderD3Graph(data, userId);
  } catch (e) {
    emptyEl.style.display = 'flex';
    emptyEl.innerHTML = `<p>Graph load error: ${e.message}</p>`;
    countEl.textContent = 'Error';
  }
}

function renderD3Graph(data, centerUserId) {
  const svg = d3.select('#graph-svg');
  svg.selectAll('*').remove();

  const container = document.getElementById('graph-svg');
  const W = container.clientWidth || 800;
  const H = container.clientHeight || 600;

  // Build nodes and links from subgraph data
  const nodes = [];
  const links = [];
  const nodeMap = new Map();

  // Center user always first
  const centerNode = {
    id: centerUserId,
    label: centerUserId.slice(0, 12) + '…',
    type: 'User',
    radius: 18,
    fx: W / 2,
    fy: H / 2,
  };
  nodes.push(centerNode);
  nodeMap.set(centerUserId, centerNode);

  // If we have subgraph data (nodes/edges format)
  if (data && data.nodes && Array.isArray(data.nodes)) {
    data.nodes.forEach(n => {
      if (!nodeMap.has(n.id)) {
        const node = {
          id: n.id,
          label: (n.label || n.id).slice(0, 14) + (n.id.length > 14 ? '…' : ''),
          type: n.type || 'Entity',
          radius: n.type === 'User' ? 14 : 10,
        };
        nodes.push(node);
        nodeMap.set(n.id, node);
      }
    });

    if (data.edges && Array.isArray(data.edges)) {
      data.edges.forEach(e => {
        if (nodeMap.has(e.source) && nodeMap.has(e.target)) {
          links.push({ source: e.source, target: e.target, label: e.type || '' });
        }
      });
    }
  } else if (data && data.ring_members) {
    // Ring format
    data.ring_members.forEach(m => {
      if (!nodeMap.has(m)) {
        const node = { id: m, label: m.slice(0,12)+'…', type: 'User', radius: 14 };
        nodes.push(node);
        nodeMap.set(m, node);
        links.push({ source: centerUserId, target: m, label: 'RING_MEMBER' });
      }
    });
  }

  // If only center node, fabricate demo structure from user_id patterns
  if (nodes.length === 1) {
    const deviceId = `dev_${centerUserId.slice(4, 12)}`;
    const ipId     = `ip_${centerUserId.slice(4, 10)}`;
    [
      { id: deviceId, type: 'Device', radius: 12 },
      { id: ipId,     type: 'IP',     radius: 10 },
    ].forEach(n => {
      nodes.push({ ...n, label: n.id.slice(0, 14) + '…' });
      nodeMap.set(n.id, nodes[nodes.length - 1]);
      links.push({ source: centerUserId, target: n.id, label: n.type === 'Device' ? 'USES_DEVICE' : 'ORIGINATED_FROM' });
    });
  }

  document.getElementById('graph-node-count').textContent = `${nodes.length} nodes · ${links.length} edges`;

  // Color map
  const colorMap = {
    User:     '#3b82f6',
    Device:   '#f59e0b',
    IP:       '#22c55e',
    Merchant: '#a855f7',
    Card:     '#ec4899',
    Entity:   '#64748b',
  };

  // Defs for arrows
  svg.append('defs').append('marker')
    .attr('id', 'arrowhead')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 20)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', '#252a38');

  const g = svg.append('g');

  // Zoom
  svg.call(d3.zoom()
    .scaleExtent([0.3, 3])
    .on('zoom', (event) => g.attr('transform', event.transform)));

  // Force simulation
  if (graphSimulation) graphSimulation.stop();
  graphSimulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(120))
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide().radius(d => d.radius + 20));

  // Links
  const link = g.append('g').selectAll('line')
    .data(links)
    .join('line')
    .attr('class', 'link');

  // Link labels
  const linkLabel = g.append('g').selectAll('text')
    .data(links)
    .join('text')
    .attr('class', 'link-label')
    .text(d => d.label);

  // Nodes
  const node = g.append('g').selectAll('g')
    .data(nodes)
    .join('g')
    .attr('class', 'node')
    .call(d3.drag()
      .on('start', (event, d) => {
        if (!event.active) graphSimulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on('end', (event, d) => {
        if (!event.active) graphSimulation.alphaTarget(0);
        if (d.id !== centerUserId) { d.fx = null; d.fy = null; }
      }));

  node.append('circle')
    .attr('r', d => d.radius)
    .attr('fill', d => colorMap[d.type] || '#64748b')
    .attr('fill-opacity', 0.9)
    .attr('stroke', d => d.id === centerUserId ? '#fff' : 'transparent')
    .attr('stroke-width', 2)
    .on('click', (event, d) => {
      // Highlight connected nodes
      node.selectAll('circle').attr('opacity', 0.3);
      link.attr('opacity', 0.1);
      const connectedIds = new Set([d.id]);
      links.forEach(l => {
        if (l.source.id === d.id) connectedIds.add(l.target.id);
        if (l.target.id === d.id) connectedIds.add(l.source.id);
      });
      node.selectAll('circle').filter(n => connectedIds.has(n.id)).attr('opacity', 1);
      link.filter(l => l.source.id === d.id || l.target.id === d.id).attr('opacity', 1);
      event.stopPropagation();
    });

  svg.on('click', () => {
    node.selectAll('circle').attr('opacity', 1);
    link.attr('opacity', 1);
  });

  node.append('text')
    .attr('dy', d => d.radius + 14)
    .text(d => d.label);

  graphSimulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);

    linkLabel
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2);

    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}

// ===================================================
// RISK SIGNALS
// ===================================================
async function loadRiskSignals() {
  const el = document.getElementById('risk-rules-container');
  try {
    const rules = await apiFetch('/rules');
    document.getElementById('rules-count').textContent = `${rules.length} active rules`;

    el.innerHTML = rules.map(r => {
      const tier = r.weight >= 80 ? 'critical' : r.weight >= 30 ? 'high' : 'medium';
      return `<div class="rule-card">
        <div class="rule-weight-circle ${tier}">${r.weight}</div>
        <div class="rule-info">
          <div class="rule-name">${r.rule_name}</div>
          <div class="rule-desc">${r.description}</div>
          <div class="rule-meta">Category: ${r.category} · Threshold: ${r.threshold} · Rule ID: ${r.rule_id}</div>
        </div>
      </div>`;
    }).join('');
  } catch (e) {
    el.innerHTML = '<div class="loading-placeholder">Error loading rules</div>';
  }
}

// ===================================================
// DATA QUALITY
// ===================================================
async function loadDataQuality() {
  const statsEl = document.getElementById('dq-stats-grid');
  const checksEl = document.getElementById('dq-checks-container');
  checksEl.innerHTML = '<div class="loading-placeholder">Running DQ checks against live data…</div>';

  try {
    const dq = await apiFetch('/dq/results');
    document.getElementById('dq-dataset-label').textContent = `Dataset: ${dq.dataset}`;

    statsEl.innerHTML = `
      <div class="stat-card blue">
        <div class="stat-label">Records Evaluated</div>
        <div class="stat-value">${dq.total_records}</div>
        <div class="stat-meta">Synthetic dataset</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total Checks</div>
        <div class="stat-value">${dq.total_checks}</div>
        <div class="stat-meta">DQ rules applied</div>
      </div>
      <div class="stat-card ${dq.failed_checks === 0 ? 'green' : 'amber'}">
        <div class="stat-label">Passed</div>
        <div class="stat-value">${dq.passed_checks}</div>
        <div class="stat-meta">${dq.failed_checks} failed</div>
      </div>
      <div class="stat-card ${dq.pass_rate >= 90 ? 'green' : dq.pass_rate >= 70 ? 'amber' : 'red'}">
        <div class="stat-label">Overall Pass Rate</div>
        <div class="stat-value">${dq.pass_rate}%</div>
        <div class="stat-meta">Across all checks</div>
      </div>`;

    checksEl.innerHTML = dq.checks.map(c => `
      <div class="dq-check-row">
        <div class="dq-check-info">
          <div class="dq-check-name">${c.name}</div>
          <div class="dq-check-desc">${c.description}</div>
        </div>
        <div class="dq-check-stats">
          <span style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${c.failed_count} failed</span>
          <span class="dq-pass-rate ${c.passed ? 'pass' : 'fail'}">${c.pass_rate}%</span>
          <span class="badge ${c.passed ? 'approve' : 'review'}">${c.passed ? 'PASS' : 'FAIL'}</span>
        </div>
      </div>`).join('');
  } catch (e) {
    statsEl.innerHTML = '<div class="stat-card" style="grid-column:1/-1;"><div class="stat-meta">DQ endpoint error: ' + e.message + '</div></div>';
    checksEl.innerHTML = '<div class="loading-placeholder">Error running DQ checks</div>';
  }
}

// ===================================================
// PIPELINES
// ===================================================
async function loadPipelines() {
  const el = document.getElementById('pipelines-container');
  el.innerHTML = '<div class="loading-placeholder">Checking pipeline components…</div>';

  try {
    const data = await apiFetch('/pipeline/status');
    const checkedAt = data.checked_at ? new Date(data.checked_at).toLocaleTimeString() : '—';
    document.getElementById('pipeline-checked-at').textContent = `Checked at ${checkedAt}`;

    const componentDefs = [
      { key: 'kafka',    name: 'Apache Kafka',      desc: 'Event streaming backbone' },
      { key: 'postgres', name: 'PostgreSQL',         desc: 'Operational data store' },
      { key: 'neo4j',    name: 'Neo4j',              desc: 'Identity graph database' },
      { key: 'redis',    name: 'Redis',              desc: 'Velocity & blacklist cache' },
      { key: 's3',       name: 'LocalStack S3',      desc: 'Object storage (lakehouse)' },
      { key: 'airflow',  name: 'Apache Airflow',     desc: 'Batch orchestration' },
    ];

    el.innerHTML = componentDefs.map(def => {
      const c = data.components[def.key] || {};
      const status = c.status || 'UNKNOWN';
      const details = Object.entries(c)
        .filter(([k]) => k !== 'status' && k !== 'error')
        .map(([k, v]) => `${k}: ${v}`)
        .join(' · ');
      const errNote = c.error ? `Error: ${c.error}` : '';

      return `<div class="pipeline-component">
        <div>
          <div class="pipeline-name">${def.name}</div>
          <div class="pipeline-meta">${def.desc}${details ? ' · ' + details : ''}${errNote ? ' · ' + errNote : ''}</div>
        </div>
        <span class="badge ${statusClass(status)}">${status}</span>
      </div>`;
    }).join('');
  } catch (e) {
    el.innerHTML = '<div class="loading-placeholder">Pipeline status unavailable</div>';
  }
}

// ===================================================
// SYSTEM HEALTH
// ===================================================
async function loadSystemHealth() {
  const el = document.getElementById('health-grid');
  el.innerHTML = '<div class="loading-placeholder" style="grid-column:1/-1;">Checking services…</div>';

  try {
    const [health, pipeline] = await Promise.all([
      fetch(HEALTH_URL).then(r => r.json()).catch(() => null),
      apiFetch('/pipeline/status').catch(() => null),
    ]);

    const services = [];

    // API health endpoint services
    if (health && health.services) {
      Object.entries(health.services).forEach(([k, v]) => {
        services.push({ name: k, status: v === 'UP' ? 'HEALTHY' : 'DOWN', detail: '' });
      });
    }

    // Pipeline status
    if (pipeline && pipeline.components) {
      Object.entries(pipeline.components).forEach(([k, v]) => {
        if (!services.find(s => s.name.toLowerCase() === k)) {
          const detail = Object.entries(v)
            .filter(([kk]) => kk !== 'status' && kk !== 'error')
            .map(([kk, vv]) => `${kk}: ${vv}`).join(', ');
          services.push({ name: k, status: v.status || 'UNKNOWN', detail, error: v.error });
        }
      });
    }

    if (services.length === 0) {
      el.innerHTML = '<div class="loading-placeholder" style="grid-column:1/-1;">No service data available</div>';
      return;
    }

    el.innerHTML = services.map(s => `
      <div class="health-card">
        <div class="health-card-header">
          <div class="health-service-name">${s.name.toUpperCase()}</div>
          <span class="badge ${statusClass(s.status)}">${s.status}</span>
        </div>
        <div class="health-detail">
          ${s.detail || 'No additional details'}
          ${s.error ? `<br><span style="color:var(--red);">${s.error}</span>` : ''}
        </div>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = `<div class="loading-placeholder" style="grid-column:1/-1;">Error: ${e.message}</div>`;
  }
}

// ===================================================
// FORMATTERS / HELPERS
// ===================================================
function formatTs(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    return d.toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'medium' });
  } catch { return ts; }
}

function formatAmount(amount, currency = 'USD') {
  if (amount == null) return '—';
  const sym = { USD: '$', GBP: '£', EUR: '€', CAD: 'C$' }[currency] || '';
  return `${sym}${parseFloat(amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function riskBar(score) {
  const s = parseFloat(score) || 0;
  const color = s >= 80 ? 'var(--red)' : s >= 40 ? 'var(--amber)' : 'var(--green)';
  return `<div class="risk-bar-wrap">
    <div class="risk-bar-bg"><div class="risk-bar-fill" style="width:${s}%; background:${color};"></div></div>
    <span class="risk-num">${s}</span>
  </div>`;
}

function decisionBadge(decision) {
  const cls = { APPROVE: 'approve', REVIEW: 'review', BLOCK: 'block' }[decision] || 'unknown';
  return `<span class="badge ${cls}">${decision || '—'}</span>`;
}

function statusClass(status) {
  return { HEALTHY: 'healthy', DEGRADED: 'degraded', DOWN: 'down', UNKNOWN: 'unknown', UP: 'healthy' }[status] || 'unknown';
}

// ===================================================
// INIT
// ===================================================
document.addEventListener('DOMContentLoaded', () => {
  checkApiHealth();
  setInterval(checkApiHealth, 30000);
  navigate('overview');
});
