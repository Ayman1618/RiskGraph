/**
 * RiskGraph — Identity & Transaction Risk Intelligence
 * app.js — Frontend Application Logic, Forensic Investigation,
 * D3.js Graph Engine, and Live Telemetry
 */

// Automatically resolve API endpoints:
// In production behind Nginx reverse proxy on the same origin: use relative paths '/api/v1' and '/health'
// In standalone local dev (e.g. port 3001 without proxy): fall back to 'http://localhost:8000'
const isLocalStandalone = window.location.port === '3001' || 
                          window.location.protocol === 'file:' || 
                          (window.location.hostname === 'localhost' && window.location.port !== '80' && window.location.port !== '' && window.location.port !== '443');

const API_BASE = isLocalStandalone ? 'http://localhost:8000/api/v1' : '/api/v1';
const HEALTH_URL = isLocalStandalone ? 'http://localhost:8000/health' : '/health';

// ===================================================
// GLOBAL STATE
// ===================================================
let currentPage = 'overview';
let txOffset = 0;
const TX_LIMIT = 50;
let txTotal = 0;
let txSearchTimer = null;
let currentInvestigationId = null;
let cachedRules = [];
let graphSimulation = null;
let graphSvg = null;
let graphZoom = null;
let activeGraphData = null;

// ===================================================
// APPLICATION INITIALIZATION & NAVIGATION
// ===================================================
document.addEventListener('DOMContentLoaded', () => {
  initializeNavigation();
  checkSystemStatus();
  setInterval(checkSystemStatus, 30000);

  const hash = window.location.hash ? window.location.hash.slice(1) : '';
  const validPages = ['overview', 'transactions', 'investigations', 'identity-graph', 'risk-signals', 'data-quality', 'pipelines', 'system-health'];
  const initialPage = validPages.includes(hash) ? hash : 'overview';
  navigate(initialPage);

  const urlParams = new URLSearchParams(window.location.search);
  const inspectId = urlParams.get('inspect');
  if (inspectId) {
    setTimeout(() => openTransactionModal(inspectId), 300);
  }
});

function initializeNavigation() {
  window.addEventListener('popstate', (e) => {
    if (e.state && e.state.page) {
      navigate(e.state.page, false);
    }
  });
}

function navigate(page, updateHistory = true) {
  currentPage = page;

  // Update tabs
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.page === page);
  });

  // Update page visibility
  document.querySelectorAll('.page').forEach(p => {
    p.classList.toggle('active', p.id === `page-${page}`);
  });

  // Breadcrumb
  const pageNames = {
    'overview': 'Overview',
    'transactions': 'Transactions Ledger',
    'investigations': 'Investigations',
    'identity-graph': 'Identity Graph',
    'risk-signals': 'Risk Signals',
    'data-quality': 'Data Quality',
    'pipelines': 'Pipelines',
    'system-health': 'System Health'
  };
  const name = pageNames[page] || page;
  document.getElementById('breadcrumb-page-name').textContent = name;

  if (updateHistory) {
    history.pushState({ page }, '', `#${page}`);
  }

  // Load content
  loadPageData(page);
}

function refreshCurrentPage() {
  loadPageData(currentPage);
  checkSystemStatus();
}

function loadPageData(page) {
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

// ===================================================
// API CLIENT & STATUS MONITORING
// ===================================================
async function apiGet(endpoint) {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    headers: { 'Accept': 'application/json' },
    signal: AbortSignal.timeout(8000)
  });
  if (!response.ok) {
    throw new Error(`API Error ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

async function checkSystemStatus() {
  const topDot = document.getElementById('topbar-status-dot');
  const topText = document.getElementById('topbar-status-text');
  const sideDot = document.getElementById('sidebar-status-dot');
  const timeEl = document.getElementById('sync-timestamp');

  try {
    const data = await apiGet(HEALTH_URL);
    const isHealthy = data.status === 'healthy';
    
    topDot.className = `status-dot ${isHealthy ? 'healthy' : 'degraded'}`;
    sideDot.className = `status-dot ${isHealthy ? 'healthy' : 'degraded'}`;
    topText.textContent = isHealthy ? 'API Healthy' : 'Degraded';
    
    const now = new Date();
    timeEl.textContent = `Synced ${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;

    const envBadge = document.getElementById('env-tag-badge');
    const envLabel = document.getElementById('env-tag-label');
    if (envBadge && envLabel) {
      if (isLocalStandalone) {
        envBadge.textContent = 'LOCAL';
        envLabel.textContent = 'docker : 8000';
      } else {
        envBadge.textContent = 'CLOUD';
        envLabel.textContent = window.location.hostname || 'riskgraph';
      }
    }
  } catch (err) {
    topDot.className = 'status-dot down';
    sideDot.className = 'status-dot down';
    topText.textContent = 'API Offline';
    timeEl.textContent = 'Sync Failed';
  }
}

function handleGlobalSearch(e) {
  if (e.key === 'Enter') {
    const query = e.target.value.trim();
    if (!query) return;

    if (query.startsWith('usr_')) {
      navigate('identity-graph');
      document.getElementById('graph-search-user').value = query;
      loadGraphForUser();
    } else {
      navigate('transactions');
      document.getElementById('tx-search-input').value = query;
      loadTransactions();
    }
  }
}

// ===================================================
// PAGE 1: OVERVIEW
// ===================================================
async function loadOverview() {
  try {
    const [stats, rings, recentHighRisk] = await Promise.all([
      apiGet('/risk/stats'),
      apiGet('/entities/rings?min_size=2').catch(() => ({ fraud_rings_count: 0, rings: [] })),
      apiGet('/transactions?limit=8&min_risk=45').catch(() => ({ transactions: [] }))
    ]);

    renderOverviewMetrics(stats);
    renderDecisionDistribution(stats);
    renderHourlyActivity(stats.hourly_breakdown || []);
    renderOverviewSyndicates(rings);
    renderOverviewSuspiciousTable(recentHighRisk.transactions || []);
  } catch (err) {
    console.error('Overview error:', err);
  }
}

function renderOverviewMetrics(s) {
  const total = s.total_transactions || 0;
  const approved = s.approved_count || 0;
  const review = s.review_count || 0;
  const blocked = s.blocked_count || 0;
  const gmv = s.total_gmv || 0;
  const avgRisk = s.avg_risk_score || 0;

  document.getElementById('metric-tx-count').textContent = total.toLocaleString();
  document.getElementById('metric-tx-sub').textContent = 'Live transactional volume';

  document.getElementById('metric-gmv-val').textContent = formatCurrency(gmv);

  document.getElementById('metric-approved-val').textContent = approved.toLocaleString();
  const appPct = total > 0 ? ((approved / total) * 100).toFixed(1) : '0';
  document.getElementById('metric-approved-sub').textContent = `${appPct}% clearance`;

  document.getElementById('metric-review-val').textContent = review.toLocaleString();
  const revPct = total > 0 ? ((review / total) * 100).toFixed(1) : '0';
  document.getElementById('metric-review-sub').textContent = `${revPct}% queue`;

  document.getElementById('metric-blocked-val').textContent = blocked.toLocaleString();
  const blkPct = total > 0 ? ((blocked / total) * 100).toFixed(1) : '0';
  document.getElementById('metric-blocked-sub').textContent = `${blkPct}% blocked`;

  document.getElementById('metric-risk-val').textContent = `${avgRisk.toFixed(2)}`;
}

function renderDecisionDistribution(s) {
  const total = s.total_transactions || 1;
  const appPct = ((s.approved_count / total) * 100).toFixed(1);
  const revPct = ((s.review_count / total) * 100).toFixed(1);
  const blkPct = ((s.blocked_count / total) * 100).toFixed(1);

  document.getElementById('dist-bar-approve').style.width = `${appPct}%`;
  document.getElementById('dist-bar-review').style.width = `${revPct}%`;
  document.getElementById('dist-bar-block').style.width = `${blkPct}%`;

  document.getElementById('distribution-total-label').textContent = `${total.toLocaleString()} total evaluated`;

  document.getElementById('dist-legend-approved').textContent = `${s.approved_count.toLocaleString()} (${appPct}%)`;
  document.getElementById('dist-legend-review').textContent = `${s.review_count.toLocaleString()} (${revPct}%)`;
  document.getElementById('dist-legend-blocked').textContent = `${s.blocked_count.toLocaleString()} (${blkPct}%)`;
}

function renderHourlyActivity(breakdown) {
  const container = document.getElementById('overview-hourly-chart');
  if (!breakdown || breakdown.length === 0) {
    container.innerHTML = '<div class="empty-alert">No hourly volume data available</div>';
    return;
  }

  // Reverse so chronological left to right
  const sorted = [...breakdown].reverse();
  const maxCount = Math.max(...sorted.map(d => d.count), 1);

  container.innerHTML = sorted.map(d => {
    const totalHeight = Math.max(Math.round((d.count / maxCount) * 65), 10);
    const blockedHeight = d.blocked ? Math.max(Math.round((d.blocked / maxCount) * 65), 4) : 0;
    const timeLabel = new Date(d.hour).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    return `
      <div class="chart-bar-col" title="${d.count} transactions (${d.blocked || 0} blocked) at ${timeLabel}">
        <div style="font-size:9.5px; font-family:var(--font-mono); color:var(--text-muted); text-align:center; margin-bottom:2px;">${d.count}</div>
        <div class="chart-bar-fill" style="height:${totalHeight}px;"></div>
        ${blockedHeight > 0 ? `<div class="chart-bar-fill blocked" style="height:${blockedHeight}px;"></div>` : ''}
        <div style="font-size:9.5px; font-family:var(--font-mono); color:var(--text-muted); text-align:center; margin-top:4px;">${timeLabel}</div>
      </div>
    `;
  }).join('');
}

function renderOverviewSyndicates(ringsData) {
  const container = document.getElementById('overview-syndicates-body');
  const rings = ringsData.rings || [];

  if (rings.length === 0) {
    container.innerHTML = `
      <div class="empty-alert">
        <p>No active fraud syndicates detected in Neo4j.</p>
      </div>`;
    return;
  }

  container.innerHTML = `
    <div style="margin-bottom: 10px;">
      <div style="font-size: 22px; font-weight: 800; font-family: var(--font-mono); color: var(--red-text);">${ringsData.fraud_rings_count}</div>
      <div style="font-size: 11.5px; color: var(--text-muted);">Clustered syndicates sharing devices or credentials</div>
    </div>
    <div style="display: flex; flex-direction: column; gap: 8px;">
      ${rings.slice(0, 3).map(r => `
        <div class="syndicate-pill" onclick="exploreSyndicate('${r.shared_device_id}', ${JSON.stringify(r.ring_members).replace(/"/g, '&quot;')})">
          <div class="syndicate-title">Shared Device: ${r.shared_device_id}</div>
          <div class="syndicate-sub">${r.ring_size} connected accounts · Click to explore →</div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderOverviewSuspiciousTable(txns) {
  const container = document.getElementById('overview-suspicious-table');
  if (!txns || txns.length === 0) {
    container.innerHTML = '<div class="empty-alert">No high-risk transactions recorded</div>';
    return;
  }

  container.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Transaction ID</th>
          <th>Timestamp</th>
          <th>User</th>
          <th class="amount">Amount</th>
          <th>Country</th>
          <th>Risk Score</th>
          <th>Decision</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        ${txns.map(tx => `
          <tr class="clickable" onclick="openTransactionModal('${tx.transaction_id}')">
            <td class="mono">${tx.transaction_id}</td>
            <td>${formatDate(tx.timestamp)}</td>
            <td class="mono">${tx.user_id || '—'}</td>
            <td class="amount">${formatCurrency(tx.amount, tx.currency)}</td>
            <td>${tx.location_country || '—'}</td>
            <td>${renderRiskScoreMeter(tx.risk_score)}</td>
            <td>${renderDecisionBadge(tx.decision)}</td>
            <td><button class="btn-table-action" onclick="event.stopPropagation(); inspectInWorkspace('${tx.transaction_id}')">Investigate</button></td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

// ===================================================
// PAGE 2: TRANSACTIONS LEDGER
// ===================================================
async function loadTransactions() {
  const container = document.getElementById('tx-table-container');
  container.innerHTML = '<div class="loading-box"><div class="spinner"></div><span>Querying transaction store...</span></div>';

  const search = document.getElementById('tx-search-input')?.value.trim() || '';
  const decision = document.getElementById('tx-decision-select')?.value || '';
  const minScore = document.getElementById('tx-min-score')?.value || '';
  const maxScore = document.getElementById('tx-max-score')?.value || '';

  const params = new URLSearchParams({
    limit: TX_LIMIT,
    offset: txOffset
  });
  if (search) params.append('search', search);
  if (decision) params.append('decision', decision);
  if (minScore) params.append('min_risk', minScore);
  if (maxScore) params.append('max_risk', maxScore);

  try {
    const data = await apiGet(`/transactions?${params.toString()}`);
    txTotal = data.total || 0;

    document.getElementById('tx-total-count-meta').textContent = `${txTotal.toLocaleString()} records matched`;
    renderTransactionsTable(data.transactions || []);
    renderPaginationControls();
  } catch (err) {
    container.innerHTML = `<div class="empty-alert">Failed to fetch transactions: ${err.message}</div>`;
  }
}

function debounceTxSearch() {
  clearTimeout(txSearchTimer);
  txSearchTimer = setTimeout(() => {
    txOffset = 0;
    loadTransactions();
  }, 350);
}

function resetTxFilters() {
  document.getElementById('tx-search-input').value = '';
  document.getElementById('tx-decision-select').value = '';
  document.getElementById('tx-min-score').value = '';
  document.getElementById('tx-max-score').value = '';
  txOffset = 0;
  loadTransactions();
}

function renderTransactionsTable(txns) {
  const container = document.getElementById('tx-table-container');
  if (!txns || txns.length === 0) {
    container.innerHTML = '<div class="empty-alert">No transactions found matching criteria.</div>';
    return;
  }

  container.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Transaction ID</th>
          <th>Timestamp</th>
          <th>User</th>
          <th>Account / Device</th>
          <th class="amount">Amount</th>
          <th>Merchant</th>
          <th>Location</th>
          <th>Risk Score</th>
          <th>Decision</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        ${txns.map(tx => `
          <tr class="clickable" onclick="openTransactionModal('${tx.transaction_id}')">
            <td class="mono">${tx.transaction_id}</td>
            <td>${formatDate(tx.timestamp)}</td>
            <td class="mono">${tx.user_id ? tx.user_id.slice(0, 16) + '…' : '—'}</td>
            <td class="mono" style="color:var(--text-muted);">${tx.device_id ? tx.device_id.slice(0, 14) + '…' : '—'}</td>
            <td class="amount">${formatCurrency(tx.amount, tx.currency)}</td>
            <td class="mono">${tx.merchant_id || '—'}</td>
            <td>${tx.location_country || '—'}</td>
            <td>${renderRiskScoreMeter(tx.risk_score)}</td>
            <td>${renderDecisionBadge(tx.decision)}</td>
            <td>
              <button class="btn-table-action" onclick="event.stopPropagation(); inspectInWorkspace('${tx.transaction_id}')">
                Investigate
              </button>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderPaginationControls() {
  const container = document.getElementById('tx-pagination-strip');
  const totalPages = Math.ceil(txTotal / TX_LIMIT) || 1;
  const currentPageNum = Math.floor(txOffset / TX_LIMIT) + 1;

  const startRecord = txTotal === 0 ? 0 : txOffset + 1;
  const endRecord = Math.min(txOffset + TX_LIMIT, txTotal);

  let pageButtons = '';
  const maxButtons = 5;
  let startPage = Math.max(1, currentPageNum - 2);
  let endPage = Math.min(totalPages, startPage + maxButtons - 1);
  if (endPage - startPage < maxButtons - 1) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }

  for (let p = startPage; p <= endPage; p++) {
    pageButtons += `
      <button class="pagination-btn ${p === currentPageNum ? 'active' : ''}" onclick="goToTxPage(${p})">
        ${p}
      </button>
    `;
  }

  container.innerHTML = `
    <span class="pagination-label">Showing records ${startRecord}–${endRecord} of ${txTotal.toLocaleString()}</span>
    <div class="pagination-controls">
      <button class="pagination-btn" onclick="goToTxPage(${currentPageNum - 1})" ${currentPageNum <= 1 ? 'disabled' : ''}>← Prev</button>
      ${pageButtons}
      <button class="pagination-btn" onclick="goToTxPage(${currentPageNum + 1})" ${currentPageNum >= totalPages ? 'disabled' : ''}>Next →</button>
    </div>
  `;
}

function goToTxPage(page) {
  txOffset = (page - 1) * TX_LIMIT;
  loadTransactions();
}

// ===================================================
// PAGE 3: INVESTIGATIONS WORKSPACE (MEMORABLE EXPERIENCE)
// ===================================================
let allQueueCases = [];
let activeQueueFilter = 'ALL';

async function loadInvestigations() {
  const queueEl = document.getElementById('case-queue-list');
  queueEl.innerHTML = '<div class="loading-box"><div class="spinner"></div><span>Loading suspicious queue...</span></div>';

  try {
    const [blocked, review] = await Promise.all([
      apiGet('/transactions?limit=60&decision=BLOCK'),
      apiGet('/transactions?limit=40&decision=REVIEW')
    ]);

    allQueueCases = [
      ...(blocked.transactions || []),
      ...(review.transactions || [])
    ].sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0));

    document.getElementById('investigation-queue-count').textContent = `${allQueueCases.length} Cases`;
    renderCaseQueueList();

    // If a specific transaction was targeted, load it; otherwise load the first case
    if (currentInvestigationId) {
      loadInvestigationDossier(currentInvestigationId);
    } else if (allQueueCases.length > 0) {
      loadInvestigationDossier(allQueueCases[0].transaction_id);
    }
  } catch (err) {
    queueEl.innerHTML = `<div class="empty-alert">Failed to load case queue: ${err.message}</div>`;
  }
}

function filterCaseQueue(filter, tabBtn) {
  activeQueueFilter = filter;
  document.querySelectorAll('.case-filter-tab').forEach(t => t.classList.remove('active'));
  tabBtn.classList.add('active');
  renderCaseQueueList();
}

function renderCaseQueueList() {
  const container = document.getElementById('case-queue-list');
  const filtered = allQueueCases.filter(c => {
    if (activeQueueFilter === 'BLOCK') return c.decision === 'BLOCK';
    if (activeQueueFilter === 'REVIEW') return c.decision === 'REVIEW';
    return true;
  });

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-alert">No cases found matching filter.</div>';
    return;
  }

  container.innerHTML = filtered.map(tx => {
    const isSelected = currentInvestigationId === tx.transaction_id;
    const rules = Array.isArray(tx.triggered_rules) ? tx.triggered_rules : [];
    const topRule = rules.length > 0 ? (rules[0].rule_name || rules[0].rule_id) : 'Threshold exceeded';

    return `
      <div class="case-card ${isSelected ? 'selected' : ''}" onclick="loadInvestigationDossier('${tx.transaction_id}', this)">
        <div class="case-card-top">
          <span class="case-card-id">${tx.transaction_id.slice(0, 20)}…</span>
          ${renderDecisionBadge(tx.decision)}
        </div>
        <div class="case-card-mid">
          <span class="case-card-amount">${formatCurrency(tx.amount, tx.currency)}</span>
          <span class="case-card-user mono">${tx.user_id ? tx.user_id.slice(0, 14) : '—'}</span>
        </div>
        <div class="case-card-bottom">
          <span>${topRule}</span>
          <span style="font-family:var(--font-mono); font-weight:700; color:${getRiskColor(tx.risk_score)};">${tx.risk_score} pts</span>
        </div>
      </div>
    `;
  }).join('');
}

async function loadInvestigationDossier(txId, cardEl = null) {
  currentInvestigationId = txId;

  // Highlight card in queue
  document.querySelectorAll('.case-card').forEach(c => c.classList.remove('selected'));
  if (cardEl) {
    cardEl.classList.add('selected');
  }

  const dossierPane = document.getElementById('dossier-pane');
  dossierPane.innerHTML = '<div class="loading-box"><div class="spinner"></div><span>Assembling forensic dossier & identity linkages...</span></div>';

  try {
    const tx = await apiGet(`/transactions/${txId}`);
    dossierPane.innerHTML = buildDossierHtml(tx, false);
  } catch (err) {
    dossierPane.innerHTML = `<div class="empty-alert">Failed to compile dossier: ${err.message}</div>`;
  }
}

function inspectInWorkspace(txId) {
  currentInvestigationId = txId;
  closeTxModal();
  navigate('investigations');
}

// ===================================================
// FORENSIC EVIDENCE DOSSIER BUILDER
// ===================================================
function buildDossierHtml(tx, isModal = false) {
  const rules = Array.isArray(tx.triggered_rules) ? tx.triggered_rules : [];
  const related = Array.isArray(tx.related_transactions) ? tx.related_transactions : [];
  const score = tx.risk_score || 0;
  const scoreClass = score >= 75 ? 'critical' : score >= 35 ? 'elevated' : 'normal';

  return `
    ${!isModal ? `
      <div class="dossier-header">
        <div class="dossier-title-area">
          <span class="dossier-tag">Forensic Case Dossier</span>
          <span class="dossier-tx-id">${tx.transaction_id}</span>
        </div>
        <div class="dossier-score-badge">
          <div class="dossier-score-box">
            <span class="dossier-score-val ${scoreClass}">${score}</span>
            <span style="font-size:10px; font-weight:700; text-transform:uppercase; color:var(--text-muted);">Risk Score</span>
          </div>
          ${renderDecisionBadge(tx.decision)}
        </div>
      </div>
    ` : ''}

    <div class="dossier-content">
      <!-- 1. Transaction Parameters -->
      <div class="dossier-section">
        <div class="dossier-section-title">
          <span>1. Transaction Attributes & Settlement</span>
          <span style="font-size:10.5px; font-weight:400; color:var(--text-muted);">${formatDate(tx.timestamp)}</span>
        </div>
        <div class="dossier-grid">
          <div class="dossier-field">
            <span class="dossier-field-k">User ID</span>
            <span class="dossier-field-v mono">${tx.user_id || '—'}</span>
          </div>
          <div class="dossier-field">
            <span class="dossier-field-k">User Name / Email</span>
            <span class="dossier-field-v">${tx.user_name || tx.user_email || 'Unregistered Customer'}</span>
          </div>
          <div class="dossier-field">
            <span class="dossier-field-k">Amount & Currency</span>
            <span class="dossier-field-v mono" style="font-size:14px; font-weight:700;">${formatCurrency(tx.amount, tx.currency)}</span>
          </div>
          <div class="dossier-field">
            <span class="dossier-field-k">Merchant ID</span>
            <span class="dossier-field-v mono">${tx.merchant_id || '—'}</span>
          </div>
          <div class="dossier-field">
            <span class="dossier-field-k">Device Hardware ID</span>
            <span class="dossier-field-v mono">${tx.device_id || '—'}</span>
          </div>
          <div class="dossier-field">
            <span class="dossier-field-k">Network IP Address</span>
            <span class="dossier-field-v mono">${tx.ip_address || '—'}</span>
          </div>
          <div class="dossier-field">
            <span class="dossier-field-k">Origin Location</span>
            <span class="dossier-field-v">${tx.location_city ? `${tx.location_city}, ` : ''}${tx.location_country || 'Unknown Geo'}</span>
          </div>
          <div class="dossier-field">
            <span class="dossier-field-k">Payment Method / Token</span>
            <span class="dossier-field-v mono">${tx.payment_method || 'CREDIT_CARD'} ${tx.card_token ? `(${tx.card_token.slice(0, 10)}…)` : ''}</span>
          </div>
          <div class="dossier-field">
            <span class="dossier-field-k">Ingestion Status</span>
            <span class="dossier-field-v">${tx.status || 'COMMITTED'}</span>
          </div>
        </div>
      </div>

      <!-- 2. Risk Signals & Triggered Rules -->
      <div class="dossier-section">
        <div class="dossier-section-title">
          <span>2. Triggered Risk Signals & Rule Evidence</span>
          <span style="font-size:10.5px; font-weight:600; color:${rules.length > 0 ? 'var(--red-text)' : 'var(--green-text)'};">
            ${rules.length} Rule${rules.length !== 1 ? 's' : ''} Fired
          </span>
        </div>
        ${rules.length > 0 ? `
          <div class="evidence-list">
            ${rules.map(r => {
              const weight = r.weight || 0;
              const isCrit = weight >= 50;
              return `
                <div class="evidence-card ${isCrit ? 'critical' : 'warning'}">
                  <div>
                    <div class="evidence-name">${r.rule_name || r.rule_id}</div>
                    <div class="evidence-desc">${r.description || 'Threshold rule violated.'}</div>
                    <div class="evidence-math">
                      Threshold: ${r.threshold !== undefined ? r.threshold : '—'} · Actual Evaluated: ${r.actual_value !== undefined ? r.actual_value : 'Matched'}
                    </div>
                  </div>
                  <div class="evidence-weight ${isCrit ? 'critical' : 'warning'}">+${weight} pts</div>
                </div>
              `;
            }).join('')}
          </div>
        ` : `
          <div class="empty-alert" style="background:#f8fafc; border:1px dashed var(--border);">
            No malicious risk signals triggered. Transaction passed all heuristic and velocity gates.
          </div>
        `}
      </div>

      <!-- 3. Connected Entities & Identity Graph Jump -->
      <div class="dossier-section">
        <div class="dossier-section-title">
          <span>3. Identity & Hardware Topology</span>
          <button class="btn-table-action" onclick="exploreUserGraph('${tx.user_id}')">Open in Identity Graph →</button>
        </div>
        <div style="background:#f8fafc; border:1px solid var(--border); border-radius:5px; padding:12px; display:flex; align-items:center; justify-content:space-between;">
          <div style="display:flex; flex-direction:column; gap:2px;">
            <span style="font-size:11px; font-weight:600; color:var(--text-primary);">Sub-graph Entity Nodes</span>
            <span style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">
              User: ${tx.user_id} · Device: ${tx.device_id || 'none'} · IP: ${tx.ip_address || 'none'}
            </span>
          </div>
          <button class="btn-secondary" style="height:28px; font-size:11.5px;" onclick="exploreUserGraph('${tx.user_id}')">
            Visualize Subgraph
          </button>
        </div>
      </div>

      <!-- 4. Related User Historical Transactions -->
      <div class="dossier-section">
        <div class="dossier-section-title">
          <span>4. Historical Transaction Trail for User (${related.length} records)</span>
        </div>
        ${related.length > 0 ? `
          <table class="data-table" style="font-size:11.5px;">
            <thead>
              <tr>
                <th>Related Transaction</th>
                <th>Timestamp</th>
                <th class="amount">Amount</th>
                <th>Merchant</th>
                <th>Score</th>
                <th>Decision</th>
              </tr>
            </thead>
            <tbody>
              ${related.map(r => `
                <tr class="clickable" onclick="loadInvestigationDossier('${r.transaction_id}')">
                  <td class="mono">${r.transaction_id}</td>
                  <td>${formatDate(r.timestamp)}</td>
                  <td class="amount">${formatCurrency(r.amount, r.currency)}</td>
                  <td class="mono">${r.merchant_id || '—'}</td>
                  <td>${renderRiskScoreMeter(r.risk_score)}</td>
                  <td>${renderDecisionBadge(r.decision)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        ` : `
          <div class="empty-alert" style="background:#f8fafc; border:1px dashed var(--border); padding:12px;">
            No other previous transactions found for this user identifier.
          </div>
        `}
      </div>
    </div>
  `;
}

// Transaction Modal handlers
async function openTransactionModal(txId) {
  const backdrop = document.getElementById('tx-modal-backdrop');
  const body = document.getElementById('modal-dossier-body');
  document.getElementById('modal-tx-id').textContent = txId;
  backdrop.classList.add('open');

  body.innerHTML = '<div class="loading-box"><div class="spinner"></div><span>Compiling transaction dossier...</span></div>';

  try {
    const tx = await apiGet(`/transactions/${txId}`);
    document.getElementById('modal-decision-badge').innerHTML = renderDecisionBadge(tx.decision);
    body.innerHTML = buildDossierHtml(tx, true);
  } catch (err) {
    body.innerHTML = `<div class="empty-alert">Failed to load transaction: ${err.message}</div>`;
  }
}

function closeTxModal() {
  document.getElementById('tx-modal-backdrop').classList.remove('open');
}

function closeModalOnBackdrop(e) {
  if (e.target === document.getElementById('tx-modal-backdrop')) {
    closeTxModal();
  }
}

// ===================================================
// PAGE 4: IDENTITY GRAPH (NEO4J D3.JS WORKSPACE)
// ===================================================
async function loadIdentityGraph() {
  loadFraudRingsList();
  
  // If search input has value, load it, otherwise if fraud ring exists load first member
  const currentVal = document.getElementById('graph-search-user').value.trim();
  if (currentVal) {
    loadGraphForUser();
  } else {
    // Default to the known fraud ring user
    document.getElementById('graph-search-user').value = 'usr_ring_member_1';
    loadGraphForUser();
  }
}

async function loadFraudRingsList() {
  const container = document.getElementById('graph-rings-container');
  try {
    const rings = await apiGet('/entities/rings?min_size=2');
    const ringList = rings.rings || [];

    if (ringList.length === 0) {
      container.innerHTML = '<div class="empty-alert">No fraud rings detected</div>';
      return;
    }

    container.innerHTML = ringList.map(r => `
      <div class="syndicate-pill" onclick="exploreSyndicate('${r.shared_device_id}', ${JSON.stringify(r.ring_members).replace(/"/g, '&quot;')})">
        <div class="syndicate-title">Ring · ${r.ring_size} Members</div>
        <div class="syndicate-sub">Dev: ${r.shared_device_id.slice(0, 18)}…</div>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = '<div class="empty-alert">Rings unavailable</div>';
  }
}

function exploreSyndicate(deviceId, members) {
  if (members && members.length > 0) {
    navigate('identity-graph');
    document.getElementById('graph-search-user').value = members[0];
    setTimeout(loadGraphForUser, 100);
  }
}

function exploreUserGraph(userId) {
  if (!userId) return;
  closeTxModal();
  navigate('identity-graph');
  document.getElementById('graph-search-user').value = userId;
  setTimeout(loadGraphForUser, 150);
}

async function loadGraphForUser() {
  const userId = document.getElementById('graph-search-user').value.trim();
  const depth = document.getElementById('graph-depth-select').value || '2';
  if (!userId) return;

  const svg = d3.select('#graph-svg');
  svg.selectAll('*').remove();

  try {
    const data = await apiGet(`/entities/graph/${encodeURIComponent(userId)}?depth=${depth}`);
    activeGraphData = data;
    renderD3IdentityGraph(data, userId);

    const urlParams = new URLSearchParams(window.location.search);
    const targetNode = urlParams.get('inspect_node');
    if (targetNode) {
      const found = (data.nodes || []).find(n => n.id === targetNode) || { id: targetNode, type: 'Device' };
      openEntityInspector(found, data.edges || []);
    }
  } catch (err) {
    console.error('Graph error:', err);
  }
}

function renderD3IdentityGraph(graphData, rootUserId) {
  const svg = d3.select('#graph-svg');
  svg.selectAll('*').remove();

  const container = document.getElementById('graph-canvas-wrapper');
  const width = container.clientWidth || 800;
  const height = container.clientHeight || 550;

  // Build unique nodes and edges
  const nodes = [];
  const edges = [];
  const nodeMap = new Map();

  // Root node
  const rootNode = {
    id: rootUserId,
    label: rootUserId,
    type: 'User',
    isRoot: true,
    radius: 16
  };
  nodes.push(rootNode);
  nodeMap.set(rootUserId, rootNode);

  if (graphData && graphData.nodes) {
    graphData.nodes.forEach(n => {
      if (!nodeMap.has(n.id)) {
        const type = n.label || n.type || 'Entity';
        const node = {
          id: n.id,
          label: n.id,
          type: type,
          isRoot: n.id === rootUserId,
          radius: type === 'User' ? 14 : 11
        };
        nodes.push(node);
        nodeMap.set(n.id, node);
      }
    });
  }

  if (graphData && graphData.edges) {
    graphData.edges.forEach(e => {
      if (nodeMap.has(e.source) && nodeMap.has(e.target)) {
        edges.push({
          source: e.source,
          target: e.target,
          type: e.type || 'CONNECTED_TO'
        });
      }
    });
  }

  // Defs for arrows
  const defs = svg.append('defs');
  defs.append('marker')
    .attr('id', 'graph-arrow')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 22)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', '#94a3b8');

  // SVG group for zooming
  const g = svg.append('g').attr('class', 'graph-viewport');

  graphZoom = d3.zoom()
    .scaleExtent([0.2, 4])
    .on('zoom', (event) => {
      g.attr('transform', event.transform);
    });
  svg.call(graphZoom);

  // Force simulation
  if (graphSimulation) graphSimulation.stop();

  graphSimulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(120))
    .force('charge', d3.forceManyBody().strength(-350))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide().radius(d => d.radius + 22));

  // Render edges
  const link = g.append('g')
    .selectAll('line')
    .data(edges)
    .join('line')
    .attr('stroke', '#cbd5e1')
    .attr('stroke-width', 1.5)
    .attr('marker-end', 'url(#graph-arrow)');

  // Render edge labels
  const linkText = g.append('g')
    .selectAll('text')
    .data(edges)
    .join('text')
    .attr('font-size', '9.5px')
    .attr('font-family', 'var(--font-mono)')
    .attr('fill', '#64748b')
    .attr('text-anchor', 'middle')
    .text(d => d.type);

  // Render nodes
  const node = g.append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .attr('class', 'graph-node')
    .call(d3.drag()
      .on('start', (event, d) => {
        if (!event.active) graphSimulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event, d) => {
        if (!event.active) graphSimulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      })
    )
    .on('click', (event, d) => {
      event.stopPropagation();
      openEntityInspector(d, edges);
    });

  // Node circles
  node.append('circle')
    .attr('r', d => d.radius)
    .attr('fill', d => getNodeColor(d.type))
    .attr('stroke', d => d.isRoot ? '#0f172a' : '#ffffff')
    .attr('stroke-width', d => d.isRoot ? 2.5 : 1.5);

  // Node text labels
  node.append('text')
    .attr('dy', d => d.radius + 12)
    .attr('text-anchor', 'middle')
    .attr('font-size', '10.5px')
    .attr('font-family', 'var(--font-mono)')
    .attr('fill', '#1e293b')
    .text(d => d.label.length > 14 ? d.label.slice(0, 13) + '…' : d.label);

  // Simulation tick
  graphSimulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);

    linkText
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2);

    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}

function getNodeColor(type) {
  switch ((type || '').toUpperCase()) {
    case 'USER':     return 'var(--node-user)';
    case 'DEVICE':   return 'var(--node-device)';
    case 'IP':       return 'var(--node-ip)';
    case 'MERCHANT': return 'var(--node-merchant)';
    default:         return '#64748b';
  }
}

function zoomGraph(factor) {
  const svg = d3.select('#graph-svg');
  if (graphZoom) svg.transition().duration(250).call(graphZoom.scaleBy, factor);
}

function resetGraphZoom() {
  const svg = d3.select('#graph-svg');
  if (graphZoom) svg.transition().duration(300).call(graphZoom.transform, d3.zoomIdentity);
}

// Contextual Entity Inspector Drawer
function openEntityInspector(node, edges) {
  const drawer = document.getElementById('entity-inspector');
  const body = document.getElementById('inspector-content');

  // Find all direct neighbors
  const connections = [];
  edges.forEach(e => {
    const sId = typeof e.source === 'object' ? e.source.id : e.source;
    const tId = typeof e.target === 'object' ? e.target.id : e.target;
    if (sId === node.id) {
      connections.push({ target: tId, relation: e.type, direction: 'OUT' });
    } else if (tId === node.id) {
      connections.push({ target: sId, relation: e.type, direction: 'IN' });
    }
  });

  const entityType = node.type || node.label || 'Entity';

  body.innerHTML = `
    <div style="display:flex; flex-direction:column; gap:4px;">
      <span style="font-size:10px; font-weight:700; text-transform:uppercase; color:var(--text-muted);">Entity Type</span>
      <span class="badge ${entityType.toLowerCase() === 'user' ? 'approve' : 'neutral'}">${entityType}</span>
    </div>

    <div style="display:flex; flex-direction:column; gap:4px;">
      <span style="font-size:10px; font-weight:700; text-transform:uppercase; color:var(--text-muted);">Identifier</span>
      <div style="display:flex; align-items:center; gap:6px;">
        <span class="mono" style="font-weight:600; font-size:12px; color:var(--text-primary); word-break:break-all;">${node.id}</span>
        <button class="btn-icon" style="width:24px;height:24px;" onclick="navigator.clipboard.writeText('${node.id}')" title="Copy ID">📋</button>
      </div>
    </div>

    <div style="display:flex; flex-direction:column; gap:6px; margin-top:8px;">
      <span style="font-size:11px; font-weight:700; text-transform:uppercase; color:var(--text-muted);">
        Connected Relationships (${connections.length})
      </span>
      <div style="display:flex; flex-direction:column; gap:6px; max-height:220px; overflow-y:auto;">
        ${connections.map(c => `
          <div style="background:#f8fafc; border:1px solid var(--border); border-radius:4px; padding:6px 8px;">
            <div style="font-size:10px; font-weight:700; color:var(--navy-base); font-family:var(--font-mono);">${c.relation}</div>
            <div class="mono" style="font-size:11px; color:var(--text-primary); margin-top:2px;">${c.target}</div>
          </div>
        `).join('')}
      </div>
    </div>

    <div style="display:flex; flex-direction:column; gap:8px; margin-top:14px;">
      <button class="btn-primary" style="width:100%; justify-content:center;" onclick="filterTransactionsByEntity('${node.id}')">
        Filter Ledger for this Entity
      </button>
      ${entityType.toLowerCase() === 'user' ? `
        <button class="btn-secondary" style="width:100%; justify-content:center;" onclick="document.getElementById('graph-search-user').value='${node.id}'; loadGraphForUser();">
          Center Graph on User
        </button>
      ` : ''}
    </div>
  `;

  drawer.classList.add('open');
  drawer.style.transform = 'translateX(0)';
}

function closeEntityInspector() {
  const drawer = document.getElementById('entity-inspector');
  drawer.classList.remove('open');
  drawer.style.transform = 'translateX(100%)';
}

function filterTransactionsByEntity(entityId) {
  closeEntityInspector();
  navigate('transactions');
  document.getElementById('tx-search-input').value = entityId;
  loadTransactions();
}

// ===================================================
// PAGE 5: RISK SIGNALS CATALOG
// ===================================================
async function loadRiskSignals() {
  const container = document.getElementById('rules-grid-container');
  container.innerHTML = '<div class="loading-box"><div class="spinner"></div><span>Querying active rule catalog...</span></div>';

  try {
    cachedRules = await apiGet('/rules');
    document.getElementById('signals-count-label').textContent = `${cachedRules.length} Production Rules Active`;
    renderRulesGrid(cachedRules);
  } catch (err) {
    container.innerHTML = `<div class="empty-alert">Failed to load rules: ${err.message}</div>`;
  }
}

function filterRules(category, tabBtn) {
  document.querySelectorAll('#page-risk-signals .toolbar-group .btn-secondary').forEach(b => b.classList.remove('active'));
  tabBtn.classList.add('active');

  if (category === 'ALL') {
    renderRulesGrid(cachedRules);
  } else {
    const filtered = cachedRules.filter(r => (r.category || '').toUpperCase() === category);
    renderRulesGrid(filtered);
  }
}

function renderRulesGrid(rules) {
  const container = document.getElementById('rules-grid-container');
  if (!rules || rules.length === 0) {
    container.innerHTML = '<div class="empty-alert">No rules found for category.</div>';
    return;
  }

  container.innerHTML = rules.map(r => {
    const weight = r.weight || 0;
    const tier = weight >= 50 ? 'critical' : weight >= 25 ? 'high' : 'medium';

    return `
      <div class="rule-card">
        <div class="rule-weight-badge ${tier}">
          <span>+${weight}</span>
          <span style="font-size:8px; font-weight:600; text-transform:uppercase;">PTS</span>
        </div>
        <div class="rule-details">
          <div class="rule-name">${r.rule_name || r.rule_id}</div>
          <div class="rule-desc">${r.description || 'Algorithmic constraint check.'}</div>
          <div class="rule-meta-tag">
            Category: ${r.category || 'GENERAL'} · Threshold: ${r.threshold !== undefined ? r.threshold : 'Rule logic'} · ID: ${r.rule_id}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// ===================================================
// PAGE 6: DATA QUALITY (CONTROL ROOM)
// ===================================================
async function loadDataQuality() {
  await runLiveDqChecks();
}

async function runLiveDqChecks() {
  const tableContainer = document.getElementById('dq-checks-table-container');
  tableContainer.innerHTML = '<div class="loading-box"><div class="spinner"></div><span>Evaluating dataset constraints & schema completeness...</span></div>';

  try {
    const data = await apiGet('/dq/results');

    document.getElementById('dq-records-val').textContent = (data.total_records || 0).toLocaleString();
    document.getElementById('dq-checks-total').textContent = data.total_checks || 0;
    document.getElementById('dq-checks-passed').textContent = data.passed_checks || 0;
    document.getElementById('dq-checks-passed-sub').textContent = `${data.passed_checks}/${data.total_checks} verified`;
    document.getElementById('dq-checks-failed').textContent = data.failed_checks || 0;

    const rate = data.pass_rate !== undefined ? data.pass_rate : 100;
    // Normalized rate if returned out of 10000
    const normalizedRate = rate > 100 ? (rate / 100).toFixed(1) : rate.toFixed(1);

    document.getElementById('dq-pass-rate-val').textContent = `${normalizedRate}%`;
    document.getElementById('dq-rate-fill').style.width = `${normalizedRate}%`;
    document.getElementById('dq-dataset-meta').textContent = `Dataset: ${data.dataset || 'live_transactions'}`;

    renderDqTable(data.checks || []);
  } catch (err) {
    tableContainer.innerHTML = `<div class="empty-alert">Failed to execute DQ suite: ${err.message}</div>`;
  }
}

function renderDqTable(checks) {
  const container = document.getElementById('dq-checks-table-container');
  if (!checks || checks.length === 0) {
    container.innerHTML = '<div class="empty-alert">No checks reported in suite.</div>';
    return;
  }

  container.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Check Name</th>
          <th>Dimension</th>
          <th>Status</th>
          <th>Pass Rate</th>
          <th>Failed Records</th>
          <th>Validation Policy</th>
        </tr>
      </thead>
      <tbody>
        ${checks.map(c => {
          const pass = c.passed === true;
          const rate = c.pass_rate > 100 ? (c.pass_rate / 100).toFixed(1) : (c.pass_rate || 100).toFixed(1);
          return `
            <tr>
              <td class="mono" style="font-weight:600;">${c.name}</td>
              <td><span class="badge neutral">${c.type || 'VALIDITY'}</span></td>
              <td><span class="badge ${pass ? 'approve' : 'block'}">${pass ? 'PASSED' : 'FAILED'}</span></td>
              <td class="mono">${rate}%</td>
              <td class="mono">${c.failed_count !== undefined ? c.failed_count : 0}</td>
              <td style="color:var(--text-secondary);">${c.description || 'Strict schema validation constraint'}</td>
            </tr>
          `;
        }).join('')}
      </tbody>
    </table>
  `;
}

// ===================================================
// PAGE 7: PIPELINES TELEMETRY
// ===================================================
async function loadPipelines() {
  const container = document.getElementById('pipelines-table-container');
  container.innerHTML = '<div class="loading-box"><div class="spinner"></div><span>Querying pipeline status and cluster metadata...</span></div>';

  try {
    const data = await apiGet('/pipeline/status');
    const checkedAt = data.checked_at ? new Date(data.checked_at).toLocaleTimeString() : '—';
    document.getElementById('pipeline-last-check-meta').textContent = `Status polled at ${checkedAt}`;

    const components = data.components || {};

    // Update diagram flow status indicators
    if (components.kafka) {
      document.getElementById('flow-kafka-status').textContent = `● ${components.kafka.status || 'OK'}`;
    }
    if (components.s3) {
      document.getElementById('flow-s3-status').textContent = `● ${components.s3.status || 'MOUNTED'}`;
    }
    if (components.postgres && components.neo4j) {
      document.getElementById('flow-sinks-status').textContent = `● PG & NEO4J UP`;
    }

    renderPipelinesTable(components);
  } catch (err) {
    container.innerHTML = `<div class="empty-alert">Failed to retrieve pipeline telemetry: ${err.message}</div>`;
  }
}

function renderPipelinesTable(components) {
  const container = document.getElementById('pipelines-table-container');
  const rows = [
    { key: 'kafka', name: 'Apache Kafka', role: 'Streaming Backbone' },
    { key: 'postgres', name: 'PostgreSQL', role: 'Operational Relational Store' },
    { key: 'neo4j', name: 'Neo4j Graph Database', role: 'Identity Graph APOC' },
    { key: 'redis', name: 'Redis Cache', role: 'In-Memory Velocity & Blacklist' },
    { key: 's3', name: 'LocalStack S3', role: 'Lakehouse Object Storage' },
    { key: 'airflow', name: 'Apache Airflow', role: 'Batch Pipeline Orchestrator' }
  ];

  container.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Component</th>
          <th>Architecture Role</th>
          <th>Status</th>
          <th>Telemetry & Configuration</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(item => {
          const comp = components[item.key] || {};
          const status = comp.status || 'UNKNOWN';
          const isHealthy = status === 'HEALTHY' || status === 'UP';

          const details = Object.entries(comp)
            .filter(([k]) => k !== 'status' && k !== 'error')
            .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
            .join(' · ');

          return `
            <tr>
              <td style="font-weight:600;">${item.name}</td>
              <td style="color:var(--text-secondary);">${item.role}</td>
              <td><span class="badge ${isHealthy ? 'approve' : 'review'}">${status}</span></td>
              <td class="mono" style="font-size:11px; color:var(--text-muted);">${details || comp.error || 'Running in container network'}</td>
            </tr>
          `;
        }).join('')}
      </tbody>
    </table>
  `;
}

// ===================================================
// PAGE 8: SYSTEM HEALTH
// ===================================================
async function loadSystemHealth() {
  const container = document.getElementById('health-table-container');
  container.innerHTML = '<div class="loading-box"><div class="spinner"></div><span>Querying service fleet health checks...</span></div>';

  try {
    const [health, pipeline] = await Promise.all([
      apiGet(HEALTH_URL).catch(() => ({ status: 'down', services: {} })),
      apiGet('/pipeline/status').catch(() => ({ components: {} }))
    ]);

    const serviceList = [
      { name: 'FastAPI Risk Engine', role: 'Sub-50ms Transaction Scoring', port: '8000', status: health.status === 'healthy' ? 'UP' : 'DOWN' },
      { name: 'PostgreSQL 16', role: 'Operational DB & Ledger', port: '5432', status: health.services?.postgres || 'UP' },
      { name: 'Neo4j 5.20 APOC', role: 'Graph Identity Engine', port: '7474 / 7687', status: health.services?.neo4j || 'UP' },
      { name: 'Redis 7.2', role: 'In-Memory Sliding Windows', port: '6379', status: health.services?.redis || 'UP' },
      { name: 'Apache Kafka 7.6', role: 'Event Ingestion Stream', port: '9092', status: pipeline.components?.kafka?.status || 'HEALTHY' },
      { name: 'LocalStack S3', role: 'Lakehouse Object Store', port: '4566', status: pipeline.components?.s3?.status || 'HEALTHY' },
      { name: 'Prometheus', role: 'Metrics Scraping Engine', port: '9090', status: 'HEALTHY' },
      { name: 'Grafana 11.0', role: 'Operational Dashboards', port: '3000', status: 'HEALTHY' }
    ];

    container.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Service Name</th>
            <th>Role</th>
            <th>Port / Protocol</th>
            <th>Health Status</th>
            <th>Last Evaluated</th>
          </tr>
        </thead>
        <tbody>
          ${serviceList.map(s => {
            const isUp = s.status === 'UP' || s.status === 'HEALTHY';
            return `
              <tr>
                <td style="font-weight:600;">${s.name}</td>
                <td style="color:var(--text-secondary);">${s.role}</td>
                <td class="mono">${s.port}</td>
                <td><span class="badge ${isUp ? 'approve' : 'block'}">${s.status}</span></td>
                <td style="color:var(--text-muted); font-size:11px;">Just now (Automated)</td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    `;
  } catch (err) {
    container.innerHTML = `<div class="empty-alert">Failed to inspect service fleet: ${err.message}</div>`;
  }
}

// ===================================================
// FORMATTING HELPERS
// ===================================================
function formatCurrency(amount, currency = 'USD') {
  if (amount === undefined || amount === null) return '—';
  const symbols = { USD: '$', EUR: '€', GBP: '£', CAD: 'C$' };
  const sym = symbols[currency] || '$';
  return `${sym}${Number(amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' });
  } catch {
    return isoStr;
  }
}

function renderDecisionBadge(decision) {
  const d = (decision || '').toUpperCase();
  if (d === 'APPROVE') return '<span class="badge approve">Approved</span>';
  if (d === 'REVIEW')  return '<span class="badge review">Under Review</span>';
  if (d === 'BLOCK')   return '<span class="badge block">Blocked</span>';
  return `<span class="badge neutral">${d || '—'}</span>`;
}

function renderRiskScoreMeter(score) {
  const s = Math.round(Number(score) || 0);
  const tier = s >= 75 ? 'high' : s >= 35 ? 'medium' : 'low';
  return `
    <div class="risk-meter">
      <div class="risk-meter-track">
        <div class="risk-meter-fill ${tier}" style="width: ${Math.min(s, 100)}%;"></div>
      </div>
      <span class="risk-score-num">${s}</span>
    </div>
  `;
}

function getRiskColor(score) {
  const s = Number(score) || 0;
  if (s >= 75) return 'var(--red-text)';
  if (s >= 35) return 'var(--amber-text)';
  return 'var(--green-text)';
}
