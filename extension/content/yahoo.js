/**
 * TrustMail — Yahoo Mail Content Script (Plain JS Dev Build)
 */
'use strict';
(function () {
  if (window.__trustmailYahooLoaded) return;
  window.__trustmailYahooLoaded = true;

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
    badge.id = 'trustmail-badge-yahoo';
    badge.style.cssText = `position:fixed!important;bottom:24px!important;right:24px!important;z-index:2147483647!important;padding:10px 16px!important;border-radius:12px!important;background:#111!important;border:1px solid ${c}44!important;color:${c}!important;font:600 13px system-ui!important;box-shadow:0 4px 20px #0008!important;`;
    badge.textContent = `TrustMail: ${result.risk_level.replace(/_/g,' ').toUpperCase()} (${pct}%)`;
    document.body.appendChild(badge);
  }

  const observer = new MutationObserver(() => {
    const subjectEl = document.querySelector('h1[data-test-id="message-subject"]');
    const subject = subjectEl?.textContent?.trim();
    if (!subject || subject === lastSubject) return;
    lastSubject = subject;
    const bodyEl = document.querySelector('[data-test-id="message-body"]');
    const urls = [];
    bodyEl?.querySelectorAll('a[href]').forEach(a => { const h = a.getAttribute('href'); if(h?.startsWith('http')) urls.push(h.slice(0,2048)); });
    chrome.runtime.sendMessage({
      type:'ANALYZE_EMAIL',
      payload:{ subject, bodyText: bodyEl?.textContent?.trim()?.slice(0,50000), urls, platform:'yahoo', emailId: btoa(subject).slice(0,16) }
    }).then(resp => { if(resp?.success) { lastResult = resp.data; injectBadge(resp.data); } });
  });
  observer.observe(document.body, { childList:true, subtree:true });

  // ── Inbox Risk Indicator ───────────────────────────────────────────────────
  // Yahoo inbox rows: li[data-test-id="virtual-list-item"] or li[data-item-id]
  // Subject: [data-test-id*="subject"], Sender: [data-test-id*="from"]

  function yahooInboxExtract(row) {
    const subjectEl = row.querySelector('[data-test-id*="subject"]') ||
                      row.querySelector('[class*="subject"]');
    const subject   = subjectEl?.textContent?.trim() || '';

    const senderEl  = row.querySelector('[data-test-id*="from"]') ||
                      row.querySelector('[class*="from"]') ||
                      row.querySelector('[class*="sender"]');
    const sender    = senderEl?.textContent?.trim() || '';

    const emailId = row.getAttribute('data-item-id') ||
                    row.getAttribute('data-test-id') ||
                    btoa(subject + sender).slice(0, 20);

    return { subject, sender, urls: [], platform: 'yahoo', emailId, subjectEl };
  }

  function activateYahooInboxScanner() {
    if (!window.__tmScanner) { setTimeout(activateYahooInboxScanner, 300); return; }
    window.__tmScanner.observe({
      rowSelector: 'li[data-test-id], li[data-item-id], [data-test-id="virtual-list-item"]',
      extractFn:   yahooInboxExtract,
    });
  }
  activateYahooInboxScanner();

  console.log('[TrustMail] Yahoo content script loaded ✓');
})();

