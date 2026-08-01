/**
 * TrustMail — Inbox Risk Indicator Engine
 * =========================================
 * Shared module loaded by every provider content script.
 * Injects colored risk pills into inbox email rows so users
 * can assess threats without opening each email.
 *
 * Architecture:
 *  Provider content script
 *    └─ calls window.__tmScanner.observe(config)
 *         └─ MutationObserver watches inbox rows
 *              └─ Queues lightweight ANALYZE_INBOX_ROW messages
 *                   └─ Service worker → /api/v1/analyze (header-only)
 *                        └─ Pill injected into row with result
 *                             └─ Click pill → in-page detail modal
 *
 * Performance guarantees:
 *  - WeakMap deduplication (each row scanned once)
 *  - 5-min result cache in service worker (reused from full scan)
 *  - Max 8 concurrent scans (queue drains in order)
 *  - requestIdleCallback batching (scans during browser idle time)
 *  - Pill injection via element.style (no <style> injection race)
 */

'use strict';

(function () {
  // Guard: only initialise once per page load
  if (window.__tmScannerLoaded) return;
  window.__tmScannerLoaded = true;

  // ── Constants ──────────────────────────────────────────────────────────────

  const MAX_CONCURRENT = 8;
  const PILL_CLASS     = 'tm-inbox-pill';
  const TOOLTIP_ID     = 'tm-inbox-tooltip';
  const MODAL_ID       = 'tm-detail-modal';

  /** Visual config for each risk level */
  const RISK = {
    safe:             { emoji: '🟢', label: 'Safe',             color: '#22c55e', bg: 'rgba(34,197,94,0.13)',   border: 'rgba(34,197,94,0.4)',   glow: 'rgba(34,197,94,0.15)'  },
    low_risk:         { emoji: '🟡', label: 'Low Risk',         color: '#84cc16', bg: 'rgba(132,204,22,0.13)',  border: 'rgba(132,204,22,0.4)',  glow: 'rgba(132,204,22,0.15)' },
    suspicious:       { emoji: '🟠', label: 'Suspicious',       color: '#f59e0b', bg: 'rgba(245,158,11,0.13)',  border: 'rgba(245,158,11,0.4)',  glow: 'rgba(245,158,11,0.15)' },
    phishing:         { emoji: '🔴', label: 'Phishing',         color: '#ef4444', bg: 'rgba(239,68,68,0.14)',   border: 'rgba(239,68,68,0.45)',  glow: 'rgba(239,68,68,0.18)'  },
    highly_dangerous: { emoji: '⚫', label: 'Highly Dangerous', color: '#f87171', bg: 'rgba(220,38,38,0.18)',   border: 'rgba(220,38,38,0.6)',   glow: 'rgba(220,38,38,0.25)'  },
  };

  // ── State ──────────────────────────────────────────────────────────────────

  // inFlight: rows currently being scanned (prevents double-queuing).
  // We do NOT use a permanent "processed" map because Gmail's virtual scroll
  // RECYCLES the same <tr> DOM elements with new content — a row element that
  // was marked as processed may now show a completely different email whose
  // pill was wiped. The correct dedup signal is whether a pill is CURRENTLY
  // present in the DOM, not whether we ever processed this element object.
  const inFlight    = new WeakSet();  // rows currently in flight (dedup in-progress)
  let   activeScans = 0;
  const queue       = [];             // pending scan jobs
  let   tooltip     = null;           // singleton tooltip element
  let   modal       = null;           // singleton detail modal

  // ── Animations (injected once) ────────────────────────────────────────────

  const styleTag = document.createElement('style');
  styleTag.textContent = `
    @keyframes tm-spin { to { transform: rotate(360deg); } }
    @keyframes tm-fade-in { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }
    @keyframes tm-modal-in { from { opacity:0; transform:scale(0.96) translateY(8px); } to { opacity:1; transform:scale(1) translateY(0); } }
    @keyframes tm-overlay-in { from { opacity:0; } to { opacity:1; } }
    @keyframes tm-bar-fill { from { width: 0%; } to { width: var(--tm-bar-w); } }
    #${MODAL_ID} { animation: tm-modal-in 0.22s cubic-bezier(.4,0,.2,1) forwards; }
    #${MODAL_ID}-overlay { animation: tm-overlay-in 0.18s ease forwards; }
    .tm-bar { animation: tm-bar-fill 0.6s cubic-bezier(.4,0,.2,1) forwards; animation-delay: 0.1s; }
    .tm-feature-row:hover { background: rgba(99,102,241,0.07) !important; }
    #${MODAL_ID} *::-webkit-scrollbar { width:4px; }
    #${MODAL_ID} *::-webkit-scrollbar-track { background:rgba(255,255,255,0.04); }
    #${MODAL_ID} *::-webkit-scrollbar-thumb { background:rgba(99,102,241,0.35); border-radius:4px; }
  `;
  (document.head || document.documentElement).appendChild(styleTag);

  // ── Tooltip ────────────────────────────────────────────────────────────────

  function getTooltip() {
    if (tooltip && document.contains(tooltip)) return tooltip;
    tooltip = document.createElement('div');
    tooltip.id = TOOLTIP_ID;
    Object.assign(tooltip.style, {
      position:        'fixed',
      zIndex:          '2147483646',
      maxWidth:        '260px',
      padding:         '12px 14px',
      borderRadius:    '12px',
      background:      '#0f172a',
      border:          '1px solid rgba(99,102,241,0.4)',
      boxShadow:       '0 8px 32px rgba(0,0,0,0.65)',
      fontFamily:      "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      fontSize:        '12px',
      color:           '#f1f5f9',
      lineHeight:      '1.55',
      pointerEvents:   'none',
      opacity:         '0',
      transition:      'opacity 0.15s ease',
    });
    document.body.appendChild(tooltip);
    return tooltip;
  }

  function showTooltip(pill, result) {
    const tt  = getTooltip();
    const rc  = RISK[result.risk_level] || RISK.suspicious;
    const pct = Math.round(result.risk_score * 100);
    const con = Math.round((result.confidence || 0) * 100);
    const reasons = (result.top_reasons || []).slice(0, 3);

    tt.innerHTML =
      `<div style="margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid rgba(255,255,255,0.1);display:flex;align-items:center;gap:7px">` +
        `<span style="font-size:15px">${rc.emoji}</span>` +
        `<span style="font-weight:700;color:${rc.color}">${rc.label}</span>` +
        `<span style="color:#64748b;margin-left:auto">${pct}% risk</span>` +
      `</div>` +
      `<div style="margin-bottom:7px;color:#94a3b8">Confidence: <strong style="color:#e2e8f0">${con}%</strong></div>` +
      (reasons.length
        ? `<div style="color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px">Why</div>` +
          reasons.map(r =>
            `<div style="color:#cbd5e1;padding:2px 0;display:flex;gap:5px;align-items:flex-start">` +
              `<span style="color:${rc.color};flex-shrink:0;margin-top:1px">›</span><span>${r}</span>` +
            `</div>`
          ).join('')
        : '') +
      `<div style="margin-top:8px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.07);font-size:10px;color:#6366f1;font-weight:600">` +
        `Click for full threat report →` +
      `</div>`;

    const rect = pill.getBoundingClientRect();
    tt.style.opacity = '0';
    tt.style.display = 'block';

    requestAnimationFrame(() => {
      const tw = 260, th = tt.offsetHeight || 140;
      let top  = rect.bottom + 6;
      let left = rect.left;
      if (top + th  > window.innerHeight - 8) top  = rect.top - th - 6;
      if (left + tw > window.innerWidth  - 8) left = window.innerWidth - tw - 8;
      tt.style.top    = top  + 'px';
      tt.style.left   = left + 'px';
      tt.style.opacity = '1';
    });
  }

  function hideTooltip() {
    if (tooltip) tooltip.style.opacity = '0';
  }

  // ── Detail Modal ───────────────────────────────────────────────────────────

  function closeModal() {
    const existing = document.getElementById(MODAL_ID);
    const overlay  = document.getElementById(MODAL_ID + '-overlay');
    if (existing) existing.remove();
    if (overlay)  overlay.remove();
    modal = null;
  }

  function makeScoreBar(score, color) {
    const pct = Math.round(score * 100);
    return `
      <div style="width:100%;height:6px;background:rgba(255,255,255,0.07);border-radius:999px;overflow:hidden">
        <div class="tm-bar" style="height:100%;border-radius:999px;background:${color};width:0%;--tm-bar-w:${pct}%"></div>
      </div>`;
  }

  function makeFeatureTag(text, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;background:${color}22;border:1px solid ${color}44;color:${color};font-size:10px;font-weight:600;margin:2px 3px 2px 0">${text}</span>`;
  }

  function openDetailModal(result, subject, sender) {
    closeModal(); // close any existing

    const rc  = RISK[result.risk_level] || RISK.suspicious;
    const pct = Math.round(result.risk_score * 100);
    const con = Math.round((result.confidence || 0) * 100);
    const reasons   = result.top_reasons || [];
    const features  = (result.shap_explanation?.top_features || []).slice(0, 8);
    const modelPreds = result.model_predictions || [];

    // ── Overlay ───────────────────────────────────────────────────────────
    const overlay = document.createElement('div');
    overlay.id = MODAL_ID + '-overlay';
    Object.assign(overlay.style, {
      position:  'fixed',
      inset:     '0',
      zIndex:    '2147483646',
      background:'rgba(2,6,23,0.75)',
      backdropFilter: 'blur(4px)',
    });
    overlay.addEventListener('click', closeModal);
    document.body.appendChild(overlay);

    // ── Modal card ────────────────────────────────────────────────────────
    const card = document.createElement('div');
    card.id = MODAL_ID;
    Object.assign(card.style, {
      position:   'fixed',
      top:        '50%',
      left:       '50%',
      transform:  'translate(-50%, -50%)',
      zIndex:     '2147483647',
      width:      'min(520px, 92vw)',
      maxHeight:  '85vh',
      overflowY:  'auto',
      background: '#0b1120',
      border:     `1px solid ${rc.border}`,
      borderRadius: '20px',
      boxShadow:  `0 0 0 1px rgba(0,0,0,0.5), 0 24px 80px rgba(0,0,0,0.8), 0 0 60px ${rc.glow}`,
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      color:      '#f1f5f9',
      lineHeight: '1.55',
    });

    // ── Risk score ring visual ─────────────────────────────────────────────
    const ringCircumference = 2 * Math.PI * 36;
    const ringOffset = ringCircumference * (1 - result.risk_score);

    // ── Model predictions table ────────────────────────────────────────────
    let modelTable = '';
    if (modelPreds.length) {
      modelTable = `
        <div style="margin-top:16px">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#475569;margin-bottom:8px">Model Votes</div>
          ${modelPreds.map(p => {
            const prob = Math.round((p.probability || 0) * 100);
            const isPhish = prob >= 50;
            const barColor = isPhish ? '#ef4444' : '#22c55e';
            return `
              <div class="tm-feature-row" style="display:flex;align-items:center;gap:8px;padding:4px 6px;border-radius:6px;transition:background 0.15s">
                <div style="width:110px;flex-shrink:0;font-size:11px;color:#94a3b8">${p.model_name || p.model || '—'}</div>
                <div style="flex:1;height:5px;background:rgba(255,255,255,0.06);border-radius:999px;overflow:hidden">
                  <div style="height:100%;width:${prob}%;background:${barColor};border-radius:999px;transition:width 0.5s"></div>
                </div>
                <div style="width:38px;text-align:right;font-size:11px;font-weight:600;color:${barColor}">${prob}%</div>
              </div>`;
          }).join('')}
        </div>`;
    }

    // ── SHAP feature importance ────────────────────────────────────────────
    let shapSection = '';
    if (features.length) {
      shapSection = `
        <div style="margin-top:16px">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#475569;margin-bottom:8px">Feature Importance (SHAP)</div>
          ${features.map(f => {
            const isPhish = f.direction === 'phishing';
            const magnitude = Math.min(Math.abs(f.importance || 0), 1);
            const barColor = isPhish ? '#ef4444' : '#22c55e';
            const dirLabel = isPhish ? '▲ phishing' : '▼ safe';
            return `
              <div class="tm-feature-row" style="display:flex;align-items:center;gap:8px;padding:4px 6px;border-radius:6px;transition:background 0.15s">
                <div style="width:130px;flex-shrink:0;font-size:11px;color:#94a3b8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${f.feature}">${f.feature || '—'}</div>
                <div style="flex:1;height:5px;background:rgba(255,255,255,0.06);border-radius:999px;overflow:hidden">
                  <div style="height:100%;width:${Math.round(magnitude*100)}%;background:${barColor};border-radius:999px"></div>
                </div>
                <div style="width:72px;text-align:right;font-size:10px;font-weight:600;color:${barColor}">${dirLabel}</div>
              </div>`;
          }).join('')}
        </div>`;
    }

    // ── What to do section ─────────────────────────────────────────────────
    const adviceMap = {
      safe:             { icon: '✓', text: 'This email appears safe. No action needed.', color: '#22c55e' },
      low_risk:         { icon: '!', text: 'Minor concerns detected. Proceed with normal caution.', color: '#84cc16' },
      suspicious:       { icon: '?', text: 'Multiple threat indicators found. Verify the sender before clicking links or sharing information.', color: '#f59e0b' },
      phishing:         { icon: '⚠', text: 'High-confidence phishing attempt. Do not click any links, download attachments, or reply. Report and delete.', color: '#ef4444' },
      highly_dangerous: { icon: '⛔', text: 'Critical threat. Delete immediately. Do not interact with this email in any way.', color: '#f87171' },
    };
    const advice = adviceMap[result.risk_level] || adviceMap.suspicious;

    card.innerHTML = `
      <!-- Header -->
      <div style="padding:20px 20px 0;display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="font-size:18px">${rc.emoji}</span>
            <span style="font-weight:800;font-size:16px;color:${rc.color};letter-spacing:-0.01em">${rc.label}</span>
            <span style="font-size:11px;padding:1px 8px;border-radius:999px;background:${rc.bg};border:1px solid ${rc.border};color:${rc.color};font-weight:700;margin-left:2px">${pct}% risk</span>
          </div>
          ${subject ? `<div style="font-size:13px;font-weight:600;color:#e2e8f0;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${subject}">${subject}</div>` : ''}
          ${sender  ? `<div style="font-size:11px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${sender}</div>` : ''}
        </div>
        <!-- SVG Score Ring -->
        <div style="flex-shrink:0;position:relative;width:76px;height:76px">
          <svg width="76" height="76" viewBox="0 0 80 80" style="transform:rotate(-90deg)">
            <circle cx="40" cy="40" r="36" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="7"/>
            <circle cx="40" cy="40" r="36" fill="none" stroke="${rc.color}" stroke-width="7"
              stroke-dasharray="${ringCircumference.toFixed(1)}"
              stroke-dashoffset="${ringOffset.toFixed(1)}"
              stroke-linecap="round"
              style="transition:stroke-dashoffset 0.8s cubic-bezier(.4,0,.2,1)"/>
          </svg>
          <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center">
            <span style="font-size:17px;font-weight:800;color:${rc.color};line-height:1">${pct}</span>
            <span style="font-size:9px;color:#64748b;font-weight:600;letter-spacing:.04em">RISK %</span>
          </div>
        </div>
        <!-- Close button -->
        <button id="tm-modal-close" style="flex-shrink:0;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);color:#94a3b8;cursor:pointer;border-radius:8px;width:28px;height:28px;font-size:14px;display:flex;align-items:center;justify-content:center;padding:0;transition:background 0.15s;line-height:1">✕</button>
      </div>

      <!-- Confidence bar -->
      <div style="padding:14px 20px 0">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px">
          <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#475569">Analysis Confidence</span>
          <span style="font-size:12px;font-weight:700;color:#e2e8f0">${con}%</span>
        </div>
        ${makeScoreBar(result.confidence || 0, '#6366f1')}
      </div>

      <!-- Divider -->
      <div style="margin:16px 20px 0;height:1px;background:rgba(255,255,255,0.06)"></div>

      <!-- Body -->
      <div style="padding:14px 20px 20px">

        <!-- Advice banner -->
        <div style="padding:10px 14px;border-radius:10px;background:${rc.bg};border:1px solid ${rc.border};display:flex;gap:10px;align-items:flex-start;margin-bottom:16px">
          <span style="font-size:16px;flex-shrink:0">${advice.icon}</span>
          <span style="font-size:12px;color:#e2e8f0;line-height:1.5">${advice.text}</span>
        </div>

        ${reasons.length ? `
          <!-- Threat reasons -->
          <div style="margin-bottom:16px">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#475569;margin-bottom:8px">Threat Indicators</div>
            ${reasons.map(r => `
              <div style="display:flex;gap:8px;align-items:flex-start;padding:5px 0">
                <span style="color:${rc.color};flex-shrink:0;font-size:13px;margin-top:1px">›</span>
                <span style="font-size:12px;color:#cbd5e1">${r}</span>
              </div>`).join('')}
          </div>` : ''}

        ${modelTable}
        ${shapSection}

        <!-- Score breakdown -->
        ${(result.signal_breakdown || result.score_breakdown) ? (() => {
          const b = result.signal_breakdown || result.score_breakdown;
          const signals = [
            { key: 'ensemble_score', label: 'ML Ensemble', icon: '🤖' },
            { key: 'header_score',   label: 'Headers',     icon: '📋' },
            { key: 'url_score',      label: 'URLs',        icon: '🔗' },
            { key: 'nlp_score',      label: 'Language',    icon: '📝' },
            { key: 'attachment_score', label: 'Attachments', icon: '📎' },
          ].filter(s => b[s.key] !== undefined);
          if (!signals.length) return '';
          return `
            <div style="margin-top:16px">
              <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#475569;margin-bottom:8px">Signal Breakdown</div>
              ${signals.map(s => {
                const val = b[s.key] || 0;
                const color = val > 0.65 ? '#ef4444' : val > 0.35 ? '#f59e0b' : '#22c55e';
                return `
                  <div class="tm-feature-row" style="display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:6px;transition:background 0.15s">
                    <span style="font-size:13px">${s.icon}</span>
                    <div style="width:90px;flex-shrink:0;font-size:11px;color:#94a3b8">${s.label}</div>
                    <div style="flex:1">${makeScoreBar(val, color)}</div>
                    <div style="width:34px;text-align:right;font-size:11px;font-weight:600;color:${color}">${Math.round(val*100)}%</div>
                  </div>`;
              }).join('')}
            </div>`;
        })() : ''}

        <!-- Footer -->
        <div style="margin-top:16px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.06);display:flex;align-items:center;justify-content:space-between">
          <div style="display:flex;align-items:center;gap:6px">
            <span style="font-size:14px">🛡️</span>
            <span style="font-size:11px;font-weight:700;color:#6366f1;letter-spacing:.02em">TrustMail</span>
            <span style="font-size:10px;color:#334155">· Local AI · No data shared</span>
          </div>
          <span style="font-size:10px;color:#334155">v2.0</span>
        </div>
      </div>
    `;

    document.body.appendChild(card);
    modal = card;

    // Close button handler
    card.querySelector('#tm-modal-close')?.addEventListener('click', (e) => {
      e.stopPropagation();
      closeModal();
    });

    // Close on Escape
    const onKey = (e) => { if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', onKey); } };
    document.addEventListener('keydown', onKey);

    // Prevent overlay click from bubbling into inbox row
    card.addEventListener('click', (e) => e.stopPropagation());
  }

  // ── Pill factory ───────────────────────────────────────────────────────────

  function makePill(state, result, meta) {
    const pill = document.createElement('span');
    pill.className = PILL_CLASS;

    const base = [
      'display:inline-flex', 'align-items:center', 'vertical-align:middle',
      'margin-left:6px', 'border-radius:999px', 'font-size:11px',
      'font-weight:600', 'white-space:nowrap', 'flex-shrink:0',
      'line-height:1.4', 'padding:1px 7px', 'border:1px solid',
    ].join(';');

    if (state === 'loading') {
      pill.style.cssText = base +
        ';background:rgba(148,163,184,0.08);border-color:rgba(148,163,184,0.2);color:#64748b;cursor:default';
      const dot = document.createElement('span');
      Object.assign(dot.style, {
        display:         'inline-block',
        width:           '8px',
        height:          '8px',
        borderRadius:    '50%',
        border:          '1.5px solid #64748b',
        borderTopColor:  'transparent',
        animation:       'tm-spin 0.7s linear infinite',
      });
      pill.appendChild(dot);

    } else if (state === 'error') {
      pill.style.cssText = base +
        ';background:rgba(107,114,128,0.08);border-color:rgba(107,114,128,0.2);color:#6b7280;cursor:default';
      pill.textContent = '—';

    } else if (state === 'result' && result) {
      const rc  = RISK[result.risk_level] || RISK.suspicious;
      const pct = Math.round(result.risk_score * 100);
      pill.style.cssText = base +
        `;background:${rc.bg};border-color:${rc.border};color:${rc.color};cursor:pointer;gap:3px`;
      pill.innerHTML = `${rc.emoji}&thinsp;<span>${pct}%</span>`;
      pill.title = ''; // prevent native tooltip from clashing

      pill.addEventListener('mouseenter', () => showTooltip(pill, result));
      pill.addEventListener('mouseleave', hideTooltip);

      // ── Click: open full detail modal ────────────────────────────────────
      pill.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        hideTooltip();
        openDetailModal(result, meta?.subject, meta?.sender);
        // Also store for popup
        chrome.runtime.sendMessage({ type: 'SET_POPUP_RESULT', payload: result });
      });
    }

    return pill;
  }

  // ── Queue & scanning ───────────────────────────────────────────────────────

  function drain() {
    while (activeScans < MAX_CONCURRENT && queue.length) {
      const job = queue.shift();
      runScan(job);
    }
  }

  function runScan({ row, data, anchor }) {
    activeScans++;

    // Place a loading pill immediately
    const loading = makePill('loading');
    anchor.appendChild(loading);

    const doScan = () => {
      chrome.runtime.sendMessage(
        { type: 'ANALYZE_INBOX_ROW', payload: data },
        (resp) => {
          activeScans = Math.max(0, activeScans - 1);
          inFlight.delete(row);   // ← unblock so row can be re-scanned if Gmail wipes it again
          drain();

          // Row removed from DOM while we waited — discard result
          if (!row.isConnected) return;

          // Anchor became stale: Gmail recycled it into a different email row.
          // In this case the anchor element itself is no longer a child of the row,
          // so injecting into it would silently attach a pill to detached content.
          if (!anchor.isConnected) return;

          // Replace loading pill with result or error
          const currentPill = anchor.querySelector('.' + PILL_CLASS);
          const newPill = (resp?.success && resp.data)
            ? makePill('result', resp.data, { subject: data.subject, sender: data.sender })
            : makePill('error');

          if (currentPill) currentPill.replaceWith(newPill);
          else anchor.appendChild(newPill);
        }
      );
    };

    // Yield to browser during idle time — prevents jank
    if (typeof requestIdleCallback !== 'undefined') {
      requestIdleCallback(doScan, { timeout: 4000 });
    } else {
      setTimeout(doScan, 80);
    }
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Schedule an inbox row for risk scanning.
   * @param {Element}  row       - The email list row element
   * @param {Function} extractFn - Provider-specific extractor: (row) => { subject, sender, urls, platform, emailId, subjectEl }
   */
  function scheduleRow(row, extractFn) {
    if (!row) return;

    const data = extractFn(row);
    if (!data || (!data.subject && !data.sender)) return; // Nothing to scan

    // Determine where to inject the pill (alongside subject text)
    const anchor = data.subjectEl || row;

    // Pill is currently in DOM → nothing to do.
    // This is the correct dedup signal instead of a permanent WeakMap:
    // Gmail's virtual scroll REUSES <tr> elements, wiping innerHTML each time
    // the row is scrolled off-screen and back. A WeakMap would permanently
    // mark a recycled row as "done" even after its content (and pill) is gone.
    if (anchor.querySelector('.' + PILL_CLASS)) return;

    // Scan already in flight for this exact row element → don't double-queue.
    if (inFlight.has(row)) return;
    inFlight.add(row);

    queue.push({ row, data, anchor });
    drain();
  }

  /**
   * Set up a MutationObserver that calls scheduleRow for every new email row.
   * @param {Object} config
   *   - rowSelector   {string}   CSS selector matching inbox email rows
   *   - extractFn     {Function} (row) => scan data object
   *   - observeRoot   {Element}  Element to observe (default: document.body)
   */
  function observe(config) {
    const { rowSelector, extractFn, observeRoot = document.body } = config;

    function processVisible() {
      document.querySelectorAll(rowSelector).forEach((row) => {
        scheduleRow(row, extractFn);
      });
    }

    // Initial scan for already-rendered rows
    setTimeout(processVisible, 800);

    // Watch for new rows (folder switches, scroll-loads, search results)
    const mo = new MutationObserver(() => {
      // Debounce: batch mutations into a single pass
      clearTimeout(mo._timer);
      mo._timer = setTimeout(processVisible, 200);
    });

    mo.observe(observeRoot, { childList: true, subtree: true });
    return mo; // caller can disconnect if needed
  }

  // Expose scanner to provider content scripts
  window.__tmScanner = { observe, scheduleRow };

  console.log('[TrustMail] Inbox scanner engine loaded ✓');
})();
