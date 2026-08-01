/**
 * TrustMail — ProtonMail Content Script (Plain JS Dev Build)
 */
'use strict';
(function () {
  if (window.__trustmailProtonLoaded) return;
  window.__trustmailProtonLoaded = true;

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
    const c = colors[result.risk_level] || '#9ca3af';
    const pct = Math.round(result.risk_score * 100);
    badge = document.createElement('div');
    badge.id = 'trustmail-badge-proton';
    badge.style.cssText = `position:fixed!important;bottom:24px!important;right:24px!important;z-index:2147483647!important;padding:10px 16px!important;border-radius:12px!important;background:#1a1a2e!important;border:1px solid ${c}55!important;color:${c}!important;font:600 13px system-ui!important;box-shadow:0 4px 20px #0008!important;`;
    badge.textContent = `🛡️ TrustMail: ${result.risk_level.replace(/_/g,' ').toUpperCase()} (${pct}%)`;
    document.body.appendChild(badge);
  }

  const observer = new MutationObserver(() => {
    const subjectEl = document.querySelector('h1[data-testid="message:subject"]');
    const subject = subjectEl?.textContent?.trim();
    if (!subject || subject === lastSubject) return;
    lastSubject = subject;
    const bodyEl = document.querySelector('[class*="messageContent"]');
    const urls = [];
    bodyEl?.querySelectorAll('a[href]').forEach(a => { const h = a.getAttribute('href'); if(h?.startsWith('http')) urls.push(h.slice(0,2048)); });
    chrome.runtime.sendMessage({
      type:'ANALYZE_EMAIL',
      payload:{ subject, bodyText: bodyEl?.textContent?.trim()?.slice(0,50000), urls, platform:'protonmail', emailId: btoa(subject).slice(0,16) }
    }).then(resp => { if(resp?.success) { lastResult = resp.data; injectBadge(resp.data); } });
  });
  observer.observe(document.body, { childList:true, subtree:true });

  // ── Inbox Risk Indicator ───────────────────────────────────────────────────
  // ProtonMail rows: div[data-element-id] or li.item-container
  // Subject: .ItemRowLayout-subject or [data-testid="item-subject"]
  // Sender:  .ItemRowLayout-sender or [data-testid="item-sender-name"]

  function protonInboxExtract(row) {
    const subjectEl = row.querySelector('[class*="ItemRowLayout"][class*="subject"]') ||
                      row.querySelector('[data-testid*="subject"]') ||
                      row.querySelector('[class*="subject"]');
    const subject   = subjectEl?.textContent?.trim() || '';

    const senderEl  = row.querySelector('[class*="ItemRowLayout"][class*="sender"]') ||
                      row.querySelector('[data-testid*="sender"]') ||
                      row.querySelector('[class*="sender"]');
    const sender    = senderEl?.textContent?.trim() || '';

    const emailId = row.getAttribute('data-element-id') ||
                    btoa(subject + sender).slice(0, 20);

    return { subject, sender, urls: [], platform: 'protonmail', emailId, subjectEl };
  }

  function activateProtonInboxScanner() {
    if (!window.__tmScanner) { setTimeout(activateProtonInboxScanner, 300); return; }
    window.__tmScanner.observe({
      rowSelector: 'div[data-element-id], li.item-container, li[data-element-id]',
      extractFn:   protonInboxExtract,
    });
  }
  activateProtonInboxScanner();

  console.log('[TrustMail] ProtonMail content script loaded ✓');
})();

