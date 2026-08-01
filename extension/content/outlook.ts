/**
 * Outlook Content Script (Outlook Live + Office 365)
 * ====================================================
 * Extracts email content from Outlook's SPA and injects the TrustMail badge.
 * Works with both outlook.live.com and outlook.office.com / outlook.office365.com
 */

// ── Selectors for Outlook Web ─────────────────────────────────────────────────
const SELECTORS = {
  subject: '[aria-label="Message Subject"], .allowTextSelection > div',
  senderName: '.jL7Na, [aria-label^="From"]',
  body: '.allowTextSelection, .ReadingPaneContent',
  headerArea: '.c_h',
};

let currentSubject: string | null = null;
let badge: HTMLElement | null = null;

function extractEmail() {
  const subjectEl = document.querySelector(SELECTORS.subject);
  const subject = subjectEl?.textContent?.trim() ?? '';
  if (!subject || subject === currentSubject) return null;

  const bodyEl = document.querySelector(SELECTORS.body);
  const bodyText = bodyEl?.textContent?.trim()?.slice(0, 50_000);
  const bodyHtml = bodyEl?.innerHTML?.slice(0, 100_000);

  const urls: string[] = [];
  bodyEl?.querySelectorAll('a[href]').forEach((a) => {
    const href = a.getAttribute('href');
    if (href?.startsWith('http')) urls.push(href.slice(0, 2048));
  });

  return { subject, bodyText, bodyHtml, urls, platform: 'outlook', emailId: btoa(subject).slice(0, 16) };
}

const observer = new MutationObserver(() => {
  const email = extractEmail();
  if (email) {
    currentSubject = email.subject ?? null;
    chrome.runtime.sendMessage({ type: 'ANALYZE_EMAIL', payload: email }).then((resp) => {
      if (resp?.success) showBadge(resp.data);
    });
  }
});

observer.observe(document.body, { childList: true, subtree: true });

function showBadge(result: { risk_level: string; risk_score: number }) {
  badge?.remove();
  badge = document.createElement('div');
  badge.id = 'trustmail-badge-outlook';

  const colors: Record<string, string> = {
    safe: '#22c55e', low_risk: '#84cc16', suspicious: '#f59e0b',
    phishing: '#ef4444', highly_dangerous: '#dc2626',
  };
  const icons: Record<string, string> = {
    safe: '✅', low_risk: '🟡', suspicious: '⚠️',
    phishing: '🚨', highly_dangerous: '⛔',
  };

  const color = colors[result.risk_level] ?? '#9ca3af';
  const icon = icons[result.risk_level] ?? '❓';
  const pct = Math.round(result.risk_score * 100);
  const label = result.risk_level.replace('_', ' ').toUpperCase();

  badge.style.cssText = `
    position:fixed;bottom:24px;right:24px;z-index:999999;
    display:flex;align-items:center;gap:8px;padding:10px 16px;
    border-radius:12px;background:#111;border:1px solid ${color}55;
    color:${color};font-family:system-ui,sans-serif;font-size:13px;
    font-weight:600;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,0.5);
  `;
  badge.innerHTML = `<span>${icon}</span><span>TrustMail: ${label} (${pct}%)</span>`;
  document.body.appendChild(badge);
}

console.log('[TrustMail] Outlook content script loaded');
