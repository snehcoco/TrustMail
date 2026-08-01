/**
 * TrustMail — Outlook Content Script (Plain JS Dev Build)
 */
'use strict';
(function () {
  if (window.__trustmailOutlookLoaded) return;
  window.__trustmailOutlookLoaded = true;

  let lastSubject = null;
  let badge = null;
  let lastResult = null;

  chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
    if (req.type === 'GET_CURRENT_RESULT') { sendResponse({ success: true, data: lastResult }); }
    return false;
  });

  function injectBadge(result) {
    if (badge) badge.remove();
    const colors = { safe:'#22c55e', low_risk:'#84cc16', suspicious:'#f59e0b', phishing:'#ef4444', highly_dangerous:'#dc2626' };
    const icons  = { safe:'✅', low_risk:'🟡', suspicious:'⚠️', phishing:'🚨', highly_dangerous:'⛔' };
    const c = colors[result.risk_level] || '#9ca3af';
    const icon = icons[result.risk_level] || '❓';
    const pct = Math.round(result.risk_score * 100);
    const label = result.risk_level.replace(/_/g,' ').toUpperCase();
    badge = document.createElement('div');
    badge.id = 'trustmail-badge-outlook';
    badge.style.cssText = `position:fixed!important;bottom:24px!important;right:24px!important;z-index:2147483647!important;display:flex!important;align-items:center!important;gap:8px!important;padding:10px 16px!important;border-radius:12px!important;background:#111!important;border:1px solid ${c}55!important;color:${c}!important;font-family:system-ui,sans-serif!important;font-size:13px!important;font-weight:600!important;box-shadow:0 4px 20px #0008!important;cursor:pointer!important;`;
    badge.innerHTML = `<span>${icon}</span><span>TrustMail: ${label} (${pct}%)</span><span id="tm-close-ol" style="margin-left:6px;opacity:0.5;cursor:pointer">✕</span>`;
    badge.querySelector('#tm-close-ol')?.addEventListener('click', e => { e.stopPropagation(); badge.remove(); badge = null; });
    document.body.appendChild(badge);
  }

  const observer = new MutationObserver(() => {
    const subjectEl = document.querySelector('[aria-label="Message Subject"], .allowTextSelection h1');
    const subject = subjectEl?.textContent?.trim();
    if (!subject || subject === lastSubject) return;
    lastSubject = subject;
    const bodyEl = document.querySelector('.allowTextSelection, .ReadingPaneContent');
    const urls = [];
    bodyEl?.querySelectorAll('a[href]').forEach(a => { const h = a.getAttribute('href'); if(h?.startsWith('http')) urls.push(h.slice(0,2048)); });
    chrome.runtime.sendMessage({
      type:'ANALYZE_EMAIL',
      payload:{ subject, bodyText: bodyEl?.textContent?.trim()?.slice(0,50000), bodyHtml: bodyEl?.innerHTML?.slice(0,100000), urls, platform:'outlook', emailId: btoa(subject).slice(0,16) }
    }).then(resp => { if(resp?.success) { lastResult = resp.data; injectBadge(resp.data); } });
  });
  observer.observe(document.body, { childList:true, subtree:true });

  // ── Inbox Risk Indicator ───────────────────────────────────────────────────
  // Outlook inbox rows: div[role="option"] in the message list panel.
  // Subject text: [class*="subject"] or .NE2BD-Jm
  // Sender: [class*="sender"] or .acMRUd

  function outlookInboxExtract(row) {
    // Try multiple selector variants (Outlook updates its classnames frequently)
    const subjectEl = row.querySelector('[class*="subject"]') ||
                      row.querySelector('[class*="Subject"]') ||
                      row.querySelector('.NE2BD-Jm');
    const subject   = subjectEl?.textContent?.trim() || row.getAttribute('aria-label') || '';

    const senderEl  = row.querySelector('[class*="sender"]') ||
                      row.querySelector('[class*="Sender"]') ||
                      row.querySelector('.acMRUd');
    const sender    = senderEl?.textContent?.trim() || '';

    const emailId = row.getAttribute('data-convid') ||
                    row.getAttribute('data-item-id') ||
                    btoa(subject + sender).slice(0, 20);

    return { subject, sender, urls: [], platform: 'outlook', emailId, subjectEl };
  }

  function activateOutlookInboxScanner() {
    if (!window.__tmScanner) { setTimeout(activateOutlookInboxScanner, 300); return; }
    window.__tmScanner.observe({
      rowSelector: 'div[role="option"][aria-label], div[data-convid], div[data-item-id]',
      extractFn:   outlookInboxExtract,
    });
  }
  activateOutlookInboxScanner();

  console.log('[TrustMail] Outlook content script loaded ✓');
})();

