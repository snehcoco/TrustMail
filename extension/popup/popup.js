'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let currentResult = null;
let backendOnline = null;
let activeTab = 'overview';

// ── Risk config ───────────────────────────────────────────────────────────────
const RISK = {
  safe:             { label: 'Safe',            icon: '✅', color: '#22c55e', desc: 'No significant threats detected.' },
  low_risk:         { label: 'Low Risk',         icon: '🟡', color: '#84cc16', desc: 'Minor concerns — proceed with caution.' },
  suspicious:       { label: 'Suspicious',       icon: '⚠️', color: '#f59e0b', desc: 'Multiple suspicious indicators detected.' },
  phishing:         { label: 'Phishing',         icon: '🚨', color: '#ef4444', desc: 'High probability phishing. Do not click links.' },
  highly_dangerous: { label: 'Highly Dangerous', icon: '⛔', color: '#dc2626', desc: '⛔ Extremely dangerous. Delete immediately.' },
};

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  checkBackend();

  // Check if an inbox pill was clicked — if so, display that result immediately
  // rather than querying the active tab's content script.
  chrome.storage.local.get(['trustmail_popup_result'], (stored) => {
    if (stored.trustmail_popup_result) {
      currentResult = stored.trustmail_popup_result;
      // Clear so next popup open starts fresh
      chrome.storage.local.remove(['trustmail_popup_result']);
      renderResult(document.getElementById('app'), currentResult);
    } else {
      render();
    }
  });
});

// ── Backend check ─────────────────────────────────────────────────────────────
function checkBackend() {
  chrome.runtime.sendMessage({ type: 'CHECK_BACKEND' }, (resp) => {
    backendOnline = resp?.success ?? false;
    const pill = document.getElementById('status-pill');
    const txt  = document.getElementById('status-text');
    if (backendOnline) {
      pill.className = 'status-pill status-online';
      txt.textContent = 'Online';
    } else {
      pill.className = 'status-pill status-offline';
      txt.textContent = 'Offline';
    }
  });
}

// ── Tab switching ─────────────────────────────────────────────────────────────
function setTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.tab').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === tab);
  });
  document.querySelectorAll('.tab-panel').forEach(el => {
    el.classList.toggle('hidden', el.dataset.panel !== tab);
  });
}

// ── Main render ───────────────────────────────────────────────────────────────
function render() {
  const app = document.getElementById('app');
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs[0]?.id) { renderEmpty(app); return; }
    chrome.tabs.sendMessage(tabs[0].id, { type: 'GET_CURRENT_RESULT' }, (resp) => {
      if (chrome.runtime.lastError || !resp?.data) {
        renderEmpty(app);
      } else {
        currentResult = resp.data;
        renderResult(app, currentResult);
      }
    });
  });
}

function renderEmpty(app) {
  app.innerHTML = `
    <div class="empty">
      <div class="empty-icon">📧</div>
      <h2>No Email Detected</h2>
      <p>Open an email in Gmail, Outlook, Yahoo, or ProtonMail to start scanning.</p>
      ${backendOnline === false ? `
      <div class="offline-warn">
        <strong>Backend offline.</strong><br>
        Start the server:<br>
        <code>cd backend &amp;&amp; python app.py</code>
      </div>` : ''}
    </div>
  `;
}

function renderResult(app, result) {
  const rc = RISK[result.risk_level] || RISK.suspicious;
  const pct = Math.round(result.risk_score * 100);
  const confPct = Math.round(result.confidence * 100);
  const r = result.risk_level;

  const size = 72, sw = 6, radius = (size - sw) / 2;
  const circ = 2 * Math.PI * radius;
  const offset = circ - (result.risk_score * circ);
  const cx = size / 2, cy = size / 2;
  const confColor = confPct >= 70 ? '#22c55e' : confPct >= 50 ? '#f59e0b' : '#9ca3af';

  app.innerHTML = `
    <div class="risk-card ${r}">
      <div class="risk-row">
        <div class="ring-wrap">
          <svg width="${size}" height="${size}">
            <circle cx="${cx}" cy="${cy}" r="${radius}" stroke-width="${sw}" stroke="rgba(255,255,255,0.08)" fill="none"/>
            <circle cx="${cx}" cy="${cy}" r="${radius}" stroke-width="${sw}" stroke="${rc.color}" fill="none"
              stroke-linecap="round" stroke-dasharray="${circ.toFixed(1)}" stroke-dashoffset="${offset.toFixed(1)}"
              style="filter:drop-shadow(0 0 6px ${rc.color}88);transition:stroke-dashoffset 0.8s ease"/>
          </svg>
          <div class="ring-label">
            <span class="ring-pct" style="color:${rc.color}">${pct}%</span>
            <span class="ring-sub">Risk</span>
          </div>
        </div>
        <div class="risk-info">
          <div class="risk-label-row">
            <span class="risk-icon">${rc.icon}</span>
            <span class="risk-name" style="color:${rc.color}">${rc.label}</span>
          </div>
          <div class="risk-desc">${rc.desc}</div>
          <div class="confidence-row">
            <span style="color:var(--muted)">Confidence</span>
            <span style="color:${confColor};font-weight:600">${confPct}%</span>
          </div>
          <div class="confidence-bar">
            <div class="confidence-fill" style="width:${confPct}%;background:${confColor}"></div>
          </div>
        </div>
      </div>
      ${result.top_reasons?.length ? `
      <div class="reasons">
        ${result.top_reasons.slice(0, 3).map(reason => `
          <div class="reason">
            <span class="reason-arrow" style="color:${rc.color}">›</span>
            <span>${reason}</span>
          </div>`).join('')}
      </div>` : ''}
    </div>

    <div class="tabs">
      <button class="tab active" data-tab="overview">Overview</button>
      <button class="tab" data-tab="headers">Headers${result.header_findings?.length ? ` (${result.header_findings.length})` : ''}</button>
      <button class="tab" data-tab="urls">URLs${result.url_findings?.length ? ` (${result.url_findings.length})` : ''}</button>
      <button class="tab" data-tab="explain">Explain</button>
      <button class="tab" data-tab="history">History</button>
    </div>

    <div class="tab-content">
      <div class="tab-panel" data-panel="overview">${renderOverview(result)}</div>
      <div class="tab-panel hidden" data-panel="headers">${renderHeaders(result)}</div>
      <div class="tab-panel hidden" data-panel="urls">${renderURLs(result)}</div>
      <div class="tab-panel hidden" data-panel="explain">${renderExplain(result)}</div>
      <div class="tab-panel hidden" data-panel="history">
        <div id="history-container">Loading...</div>
      </div>
    </div>

    <div class="footer">
      <span>${result.scan_duration_ms || '—'}ms · v${result.model_version || '1.0.0'}</span>
      <div>
        <button class="footer-btn" id="btn-export-json">⬇ JSON</button>
        <button class="footer-btn" id="btn-export-text">⬇ Text</button>
      </div>
    </div>
  `;

  // Attach event listeners (no inline onclick needed)
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => setTab(btn.dataset.tab));
  });
  document.getElementById('btn-export-json')?.addEventListener('click', exportJSON);
  document.getElementById('btn-export-text')?.addEventListener('click', exportText);
  document.querySelector('[data-tab="history"]')?.addEventListener('click', loadHistory);
}

function renderOverview(result) {
  let html = '';
  if (result.suspicious_keywords?.length) {
    html += `<div class="section">
      <div class="section-title">Suspicious Keywords</div>
      <div>${result.suspicious_keywords.slice(0, 12).map(k =>
        `<span class="tag" style="color:#fca5a5;border-color:#7f1d1d;background:#2d0000">${k}</span>`
      ).join('')}</div>
    </div>`;
  }
  if (result.model_predictions?.length) {
    html += `<div class="section"><div class="section-title">AI Model Predictions</div>`;
    result.model_predictions.forEach(p => {
      const pct = Math.round(p.phishing_probability * 100);
      const c = pct >= 65 ? '#ef4444' : pct >= 45 ? '#f59e0b' : '#22c55e';
      html += `<div class="bar-row">
        <div class="bar-label"><span style="color:var(--muted)">${p.model_name}</span><span style="color:${c}">${pct}%</span></div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${c}"></div></div>
      </div>`;
    });
    html += `</div>`;
  }
  if (result.threat_categories?.length) {
    html += `<div class="section"><div class="section-title">Threat Categories</div>
      ${result.threat_categories.map(c =>
        `<span class="tag" style="color:#fbbf24;border-color:#78350f;background:#1c0a00">${c.replace(/_/g, ' ')}</span>`
      ).join('')}
    </div>`;
  }
  if (!html) html = `<div style="text-align:center;padding:30px;color:var(--muted)">✅ No significant threats detected.</div>`;
  return html;
}

function renderHeaders(result) {
  if (!result.header_findings?.length) return `<div style="text-align:center;padding:30px;color:var(--muted)">No header data available.</div>`;
  const colors = { Pass: '#22c55e', Fail: '#ef4444', Missing: '#f59e0b', Suspicious: '#f59e0b', Softfail: '#f59e0b' };
  return `<div class="section">
    ${result.header_findings.map(f => {
      const c = colors[f.result] || '#9ca3af';
      return `<div class="finding-row">
        <div class="dot" style="background:${c}"></div>
        <div>
          <div class="finding-name">${f.check} <span style="color:${c};font-size:11px">${f.result}</span></div>
          ${f.detail ? `<div class="finding-val">${f.detail}</div>` : ''}
        </div>
      </div>`;
    }).join('')}
  </div>`;
}

function renderURLs(result) {
  if (!result.url_findings?.length) return `<div style="text-align:center;padding:30px;color:var(--muted)">No URLs found.</div>`;
  const sorted = [...result.url_findings].sort((a, b) => b.risk_score - a.risk_score);
  return sorted.map(f => {
    const pct = Math.round(f.risk_score * 100);
    const c = pct >= 65 ? '#ef4444' : pct >= 40 ? '#f59e0b' : '#22c55e';
    const truncated = f.url.length > 45 ? f.url.slice(0, 45) + '…' : f.url;
    const tags = [
      f.is_ip_based && ['IP URL', '#f59e0b'],
      f.is_shortened && ['Shortened', '#f59e0b'],
      f.is_homograph && ['Homograph', '#dc2626'],
      f.is_typosquatting && ['Typosquat', '#dc2626'],
      f.suspicious_tld && ['Bad TLD', '#f59e0b'],
    ].filter(Boolean);
    return `<div class="url-item">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px">
        <div class="url-code">${truncated}</div>
        <div class="url-risk" style="color:${c}">${pct}%</div>
      </div>
      ${tags.map(([t, tc]) => `<span class="tag" style="color:${tc};border-color:${tc}44;background:${tc}11">${t}</span>`).join('')}
    </div>`;
  }).join('');
}

function renderExplain(result) {
  let html = '';
  if (result.top_reasons?.length) {
    html += `<div class="section"><div class="section-title">Why This Classification</div>
      ${result.top_reasons.map(r => `
        <div class="reason" style="margin-bottom:6px">
          <span style="color:var(--cyan)">›</span>
          <span>${r}</span>
        </div>`).join('')}
    </div>`;
  }
  if (result.shap_explanation?.top_features?.length) {
    html += `<div class="section"><div class="section-title">SHAP Feature Importance</div>`;
    result.shap_explanation.top_features.slice(0, 8).forEach(f => {
      const c = f.direction === 'phishing' ? '#ef4444' : '#22c55e';
      const w = Math.min(Math.abs(f.importance) * 200, 100);
      html += `<div class="bar-row">
        <div class="bar-label">
          <span style="color:var(--muted);font-family:monospace;font-size:10px">${f.feature.replace(/_/g, ' ')}</span>
          <span style="color:${c}">${f.direction === 'phishing' ? '+' : '−'}${Math.abs(f.importance).toFixed(3)}</span>
        </div>
        <div class="bar-track"><div class="bar-fill" style="width:${w}%;background:${c}"></div></div>
      </div>`;
    });
    html += '</div>';
  }
  if (!html) html = `<div style="text-align:center;padding:30px;color:var(--muted)">Enable "Include Explanations" in settings for detailed AI reasoning.</div>`;
  return html;
}

function loadHistory() {
  chrome.runtime.sendMessage({ type: 'GET_SCAN_HISTORY' }, (resp) => {
    const container = document.getElementById('history-container');
    if (!container) return;
    const history = resp?.data || [];
    if (!history.length) {
      container.innerHTML = `<div style="text-align:center;padding:30px;color:var(--muted)">No scan history yet.</div>`;
      return;
    }
    const colors = { safe: '#22c55e', low_risk: '#84cc16', suspicious: '#f59e0b', phishing: '#ef4444', highly_dangerous: '#dc2626' };
    container.innerHTML = history.slice(0, 20).map(s => {
      const c = colors[s.riskLevel] || '#9ca3af';
      const pct = Math.round(s.riskScore * 100);
      const date = new Date(s.timestamp).toLocaleString();
      return `<div class="section" style="margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;gap:8px">
          <div style="min-width:0;flex:1">
            <div style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${s.subject || '(No subject)'}</div>
            <div style="color:var(--muted);font-size:11px">${s.sender || ''}</div>
            <div style="color:var(--dim);font-size:10px">${date} · ${s.platform}</div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="color:${c};font-weight:700">${pct}%</div>
            <div style="color:${c};font-size:11px;text-transform:capitalize">${s.riskLevel.replace('_', ' ')}</div>
          </div>
        </div>
      </div>`;
    }).join('') + `<button id="btn-clear-history" style="width:100%;margin-top:8px;padding:6px;border-radius:8px;border:1px solid #334155;background:none;color:#ef4444;cursor:pointer;font-size:11px">Clear History</button>`;

    document.getElementById('btn-clear-history')?.addEventListener('click', clearHistory);
  });
}

function clearHistory() {
  chrome.runtime.sendMessage({ type: 'CLEAR_HISTORY' }, () => loadHistory());
}

function exportJSON() {
  if (!currentResult) return;
  const blob = new Blob([JSON.stringify(currentResult, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `trustmail-report-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function exportText() {
  if (!currentResult) return;
  const r = currentResult;
  const lines = [
    '=== TrustMail Security Report ===',
    `Date: ${new Date().toISOString()}`,
    `Risk Level: ${r.risk_level.toUpperCase()}`,
    `Risk Score: ${Math.round(r.risk_score * 100)}%`,
    `Confidence: ${Math.round(r.confidence * 100)}%`,
    '', '--- Top Reasons ---',
    ...(r.top_reasons || []).map(x => `• ${x}`),
    '', '--- Headers ---',
    ...(r.header_findings || []).map(h => `${h.check}: ${h.result}${h.detail ? ' — ' + h.detail : ''}`),
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `trustmail-report-${Date.now()}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}
