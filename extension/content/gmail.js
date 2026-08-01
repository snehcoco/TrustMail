/**
 * TrustMail — Gmail Content Script (Plain JS Dev Build)
 * ======================================================
 * Extracts email data from Gmail's DOM and sends to backend for analysis.
 * Shows a floating risk badge in the corner of the screen.
 */

'use strict';

(function () {
  if (window.__trustmailGmailLoaded) return;
  window.__trustmailGmailLoaded = true;

  let currentEmailId = null;
  let badge = null;
  let isAnalyzing = false;
  let lastResult = null;

  // Allow popup to retrieve current result
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.type === 'GET_CURRENT_RESULT') {
      sendResponse({ success: true, data: lastResult });
    }
    return false;
  });

  // Gmail DOM selectors
  const SELECTORS = {
    emailView: '[data-message-id]',
    subject: 'h2.hP',
    senderEmail: '.go',
    senderName: '.gD',
    body: '.a3s.aiL',
  };

  function extractURLs(container) {
    if (!container) return [];
    const urls = new Set();
    container.querySelectorAll('a[href]').forEach((a) => {
      const href = a.getAttribute('href');
      if (href && (href.startsWith('http') || href.startsWith('www'))) {
        urls.add(href.slice(0, 2048));
      }
    });
    return Array.from(urls).slice(0, 100);
  }

  function extractEmail(emailEl, emailId) {
    const subjectEl = document.querySelector(SELECTORS.subject);
    const subject = subjectEl?.textContent?.trim();

    const senderEmailEl = document.querySelector(SELECTORS.senderEmail);
    const senderNameEl = document.querySelector(SELECTORS.senderName);
    const senderEmail =
      senderEmailEl?.getAttribute('email') ||
      senderNameEl?.getAttribute('email') ||
      '';
    const senderDomain = senderEmail.includes('@') ? senderEmail.split('@')[1] : '';

    const bodyEl =
      emailEl.querySelector(SELECTORS.body) ||
      document.querySelector(SELECTORS.body);
    const bodyText = bodyEl?.textContent?.trim()?.slice(0, 50000) || '';
    const bodyHtml = bodyEl?.innerHTML?.slice(0, 100000) || '';
    const urls = extractURLs(bodyEl);

    return {
      subject,
      bodyText,
      bodyHtml,
      sender: senderEmail,
      senderDomain,
      urls,
      platform: 'gmail',
      emailId,
    };
  }

  function showBadge(config) {
    if (badge) badge.remove();
    badge = document.createElement('div');
    badge.id = 'trustmail-badge';
    badge.style.cssText = `
      position: fixed !important;
      bottom: 24px !important;
      right: 24px !important;
      z-index: 2147483647 !important;
      display: flex !important;
      align-items: center !important;
      gap: 8px !important;
      padding: 10px 16px !important;
      border-radius: 12px !important;
      background: ${config.bg} !important;
      border: 1px solid ${config.color}55 !important;
      color: ${config.color} !important;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
      font-size: 13px !important;
      font-weight: 600 !important;
      cursor: pointer !important;
      box-shadow: 0 4px 24px rgba(0,0,0,0.5) !important;
      user-select: none !important;
      letter-spacing: 0.02em !important;
      transition: transform 0.15s ease !important;
    `;
    badge.innerHTML = `
      <span style="font-size:16px">${config.icon}</span>
      <span>TrustMail: ${config.text}</span>
      <span id="tm-close" style="margin-left:6px;opacity:0.5;font-size:14px;cursor:pointer">✕</span>
    `;
    badge.addEventListener('mouseenter', () => { badge.style.transform = 'translateY(-2px)'; });
    badge.addEventListener('mouseleave', () => { badge.style.transform = 'translateY(0)'; });
    badge.querySelector('#tm-close')?.addEventListener('click', (e) => {
      e.stopPropagation();
      badge.remove();
      badge = null;
    });
    document.body.appendChild(badge);
  }

  function showScanning() {
    showBadge({ icon: '🔍', text: 'Scanning...', color: '#94a3b8', bg: '#1e293b' });
  }

  function showResult(result) {
    const map = {
      safe:             { icon: '✅', color: '#22c55e', bg: '#052e16' },
      low_risk:         { icon: '🟡', color: '#84cc16', bg: '#1a2e05' },
      suspicious:       { icon: '⚠️', color: '#f59e0b', bg: '#2d1b00' },
      phishing:         { icon: '🚨', color: '#ef4444', bg: '#2d0000' },
      highly_dangerous: { icon: '⛔', color: '#dc2626', bg: '#450a0a' },
    };
    const c = map[result.risk_level] || map.suspicious;
    const label = result.risk_level.replace(/_/g, ' ').toUpperCase();
    const pct = Math.round(result.risk_score * 100);
    showBadge({ ...c, text: `${label} (${pct}%)` });
  }

  function showError(msg) {
    showBadge({ icon: '❓', text: msg || 'Start the TrustMail backend', color: '#9ca3af', bg: '#111827' });
  }

  async function analyzeEmail(emailEl, emailId) {
    isAnalyzing = true;
    try {
      const email = extractEmail(emailEl, emailId);
      if (!email.bodyText && !email.subject) return;
      showScanning();
      const resp = await chrome.runtime.sendMessage({ type: 'ANALYZE_EMAIL', payload: email });
      if (resp?.success) { lastResult = resp.data; showResult(resp.data); }
      else showError(resp?.error);
    } catch (e) {
      showError('Error — is backend running?');
    } finally {
      isAnalyzing = false;
    }
  }

  function tryExtract() {
    const emailEl = document.querySelector(SELECTORS.emailView);
    if (!emailEl) return;
    const emailId = emailEl.getAttribute('data-message-id');
    if (!emailId || emailId === currentEmailId || isAnalyzing) return;
    currentEmailId = emailId;
    analyzeEmail(emailEl, emailId);
  }

  // Observe Gmail's dynamic DOM (full email open detection)
  const observer = new MutationObserver(tryExtract);
  observer.observe(document.body, { childList: true, subtree: true });
  setTimeout(tryExtract, 1500);

  // ── Inbox Risk Indicator ───────────────────────────────────────────────────
  // Runs AFTER the engine is ready. Uses a lightweight subject+sender payload.
  // Gmail inbox rows are <tr class="zA"> elements.
  // Subject text lives in .bog; sender name in .zF.

  function gmailInboxExtract(row) {
    // Subject element — pill will be appended here
    const subjectEl = row.querySelector('.bog') || row.querySelector('.y6');
    const subject   = subjectEl?.textContent?.trim() || '';

    // Sender email attribute lives on .zF
    const senderEl   = row.querySelector('.zF');
    const sender     = senderEl?.getAttribute('email') || senderEl?.textContent?.trim() || '';

    // First URL in the snippet (if any) — best-effort
    const snippetEl  = row.querySelector('.y2');
    const urls       = [];
    row.querySelectorAll('a[href]').forEach((a) => {
      const h = a.getAttribute('href');
      if (h?.startsWith('http')) urls.push(h.slice(0, 2048));
    });

    const emailIdRaw = new TextEncoder().encode(subject + sender).slice(0, 60);
    const emailId = row.getAttribute('data-legacy-thread-id') ||
                    row.getAttribute('id') ||
                    btoa(String.fromCharCode(...emailIdRaw)).slice(0, 20);

    return { subject, sender, urls, platform: 'gmail', emailId, subjectEl };
  }

  // Wait for the inbox scanner engine to be ready, then activate
  function activateGmailInboxScanner() {
    if (!window.__tmScanner) {
      setTimeout(activateGmailInboxScanner, 300);
      return;
    }
    window.__tmScanner.observe({
      rowSelector: 'tr.zA',          // Gmail inbox row
      extractFn:   gmailInboxExtract,
    });
  }
  activateGmailInboxScanner();

  console.log('[TrustMail] Gmail content script loaded ✓');
})();

