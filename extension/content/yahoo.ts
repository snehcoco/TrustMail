/**
 * Yahoo Mail Content Script
 * ==========================
 * Extracts email content from Yahoo Mail's dynamic interface.
 */

const SELECTORS = {
  subject: 'h1[data-test-id="message-subject"]',
  body: '[data-test-id="message-body"]',
};

let lastSubject: string | null = null;

const observer = new MutationObserver(() => {
  const subjectEl = document.querySelector(SELECTORS.subject);
  const subject = subjectEl?.textContent?.trim();
  if (!subject || subject === lastSubject) return;
  lastSubject = subject;

  const bodyEl = document.querySelector(SELECTORS.body);
  const urls: string[] = [];
  bodyEl?.querySelectorAll('a[href]').forEach((a) => {
    const h = a.getAttribute('href');
    if (h?.startsWith('http')) urls.push(h.slice(0, 2048));
  });

  chrome.runtime.sendMessage({
    type: 'ANALYZE_EMAIL',
    payload: {
      subject,
      bodyText: bodyEl?.textContent?.trim()?.slice(0, 50_000),
      bodyHtml: bodyEl?.innerHTML?.slice(0, 100_000),
      urls,
      platform: 'yahoo',
      emailId: btoa(subject).slice(0, 16),
    },
  }).then((resp) => {
    if (resp?.success) injectBadge(resp.data);
  });
});

observer.observe(document.body, { childList: true, subtree: true });

function injectBadge(result: { risk_level: string; risk_score: number }) {
  document.getElementById('trustmail-badge-yahoo')?.remove();
  const el = document.createElement('div');
  el.id = 'trustmail-badge-yahoo';
  const colors: Record<string, string> = {
    safe: '#22c55e', low_risk: '#84cc16', suspicious: '#f59e0b',
    phishing: '#ef4444', highly_dangerous: '#dc2626',
  };
  const c = colors[result.risk_level] ?? '#9ca3af';
  el.style.cssText = `position:fixed;bottom:24px;right:24px;z-index:9999;padding:10px 16px;border-radius:12px;background:#111;border:1px solid ${c}44;color:${c};font:600 13px system-ui;box-shadow:0 4px 20px #0008;`;
  el.textContent = `TrustMail: ${result.risk_level.toUpperCase()} (${Math.round(result.risk_score * 100)}%)`;
  document.body.appendChild(el);
}

console.log('[TrustMail] Yahoo Mail content script loaded');
