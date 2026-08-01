/**
 * Gmail Content Script
 * ====================
 * Extracts email data from Gmail's DOM and sends it to the background
 * service worker for analysis. Injects a floating risk badge into the
 * email view.
 *
 * Gmail uses dynamic React rendering — we use MutationObserver to detect
 * when an email is opened and re-extract on navigation changes.
 *
 * Selectors are tested against Gmail as of 2024. They may need updating
 * if Google changes Gmail's DOM structure.
 */

// ── Types ──────────────────────────────────────────────────────────────────────

interface ExtractedEmail {
  subject?: string;
  bodyText?: string;
  bodyHtml?: string;
  sender?: string;
  senderDomain?: string;
  replyTo?: string;
  urls?: string[];
  platform: string;
  emailId?: string;
}

// ── State ─────────────────────────────────────────────────────────────────────

let currentEmailId: string | null = null;
let badgeContainer: HTMLElement | null = null;
let isAnalyzing = false;

// ── Selectors (update if Gmail DOM changes) ───────────────────────────────────

const SELECTORS = {
  emailView: '[data-message-id]',
  subject: 'h2[data-legacy-thread-id], h2.hP',
  senderName: '.gD',
  senderEmail: '.go',
  body: '.a3s.aiL',
  replyTo: '.ajA',
  headerRow: '.aJ5',
};

// ── Main: observe Gmail navigation ───────────────────────────────────────────

function init(): void {
  observeEmailOpen();
  console.log('[TrustMail] Gmail content script loaded');
}

function observeEmailOpen(): void {
  const observer = new MutationObserver(() => {
    tryExtractAndAnalyze();
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['data-message-id'],
  });

  // Also run on initial load
  setTimeout(tryExtractAndAnalyze, 1000);
}

function tryExtractAndAnalyze(): void {
  const emailEl = document.querySelector(SELECTORS.emailView);
  if (!emailEl) return;

  const emailId = emailEl.getAttribute('data-message-id');
  if (!emailId || emailId === currentEmailId || isAnalyzing) return;

  currentEmailId = emailId;
  extractAndAnalyze(emailEl, emailId);
}

async function extractAndAnalyze(emailEl: Element, emailId: string): Promise<void> {
  isAnalyzing = true;

  try {
    const email = extractEmail(emailEl, emailId);
    if (!email.bodyText && !email.subject) return;

    showAnalyzingBadge();

    const response = await chrome.runtime.sendMessage({
      type: 'ANALYZE_EMAIL',
      payload: email,
    });

    if (response.success) {
      showResultBadge(response.data);
    } else {
      showErrorBadge(response.error);
    }
  } catch (err) {
    console.error('[TrustMail] Analysis error:', err);
    showErrorBadge('Analysis failed');
  } finally {
    isAnalyzing = false;
  }
}

// ── Email extraction ──────────────────────────────────────────────────────────

function extractEmail(emailEl: Element, emailId: string): ExtractedEmail {
  // Subject
  const subjectEl = document.querySelector(SELECTORS.subject);
  const subject = subjectEl?.textContent?.trim();

  // Sender
  const senderNameEl = document.querySelector(SELECTORS.senderName);
  const senderEmailEl = document.querySelector(SELECTORS.senderEmail);
  const senderEmail = senderEmailEl?.getAttribute('email') ?? senderNameEl?.getAttribute('email');
  const senderDomain = senderEmail?.split('@')[1];

  // Body
  const bodyEl = emailEl.querySelector(SELECTORS.body) ?? document.querySelector(SELECTORS.body);
  const bodyHtml = bodyEl?.innerHTML?.slice(0, 100_000);
  const bodyText = bodyEl?.textContent?.trim()?.slice(0, 50_000);

  // URLs from body
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

function extractURLs(container: Element | null): string[] {
  if (!container) return [];
  const anchors = container.querySelectorAll('a[href]');
  const urls = new Set<string>();
  anchors.forEach((a) => {
    const href = a.getAttribute('href');
    if (href && (href.startsWith('http') || href.startsWith('www'))) {
      urls.add(href.slice(0, 2048));
    }
  });
  return Array.from(urls).slice(0, 100);
}

// ── Badge injection ───────────────────────────────────────────────────────────

function showAnalyzingBadge(): void {
  injectBadge({
    icon: '🔍',
    text: 'Scanning...',
    color: '#6b7280',
    bgColor: '#1f2937',
  });
}

function showResultBadge(result: { risk_level: string; risk_score: number; confidence: number }): void {
  const config: Record<string, { icon: string; color: string; bg: string }> = {
    safe: { icon: '✅', color: '#22c55e', bg: '#052e16' },
    low_risk: { icon: '🟡', color: '#84cc16', bg: '#1a2e05' },
    suspicious: { icon: '⚠️', color: '#f59e0b', bg: '#2d1b00' },
    phishing: { icon: '🚨', color: '#ef4444', bg: '#2d0000' },
    highly_dangerous: { icon: '⛔', color: '#dc2626', bg: '#450a0a' },
  };

  const c = config[result.risk_level] ?? config.suspicious;
  const label = result.risk_level.replace('_', ' ').toUpperCase();
  const pct = Math.round(result.risk_score * 100);

  injectBadge({
    icon: c.icon,
    text: `${label} (${pct}%)`,
    color: c.color,
    bgColor: c.bg,
  });
}

function showErrorBadge(error?: string): void {
  injectBadge({
    icon: '❓',
    text: error ?? 'TrustMail: Start backend',
    color: '#9ca3af',
    bgColor: '#111827',
  });
}

interface BadgeConfig {
  icon: string;
  text: string;
  color: string;
  bgColor: string;
}

function injectBadge(config: BadgeConfig): void {
  // Remove existing badge
  badgeContainer?.remove();

  badgeContainer = document.createElement('div');
  badgeContainer.id = 'trustmail-badge';
  badgeContainer.style.cssText = `
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 999999;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    border-radius: 12px;
    background: ${config.bgColor};
    border: 1px solid ${config.color}44;
    color: ${config.color};
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 4px 24px rgba(0,0,0,0.4);
    backdrop-filter: blur(12px);
    transition: all 0.2s ease;
    user-select: none;
    letter-spacing: 0.02em;
  `;

  badgeContainer.innerHTML = `
    <span style="font-size: 16px">${config.icon}</span>
    <span>TrustMail: ${config.text}</span>
    <span id="trustmail-badge-close" style="margin-left:8px;opacity:0.6;cursor:pointer;font-size:16px">✕</span>
  `;

  // Hover effect
  badgeContainer.addEventListener('mouseenter', () => {
    (badgeContainer as HTMLElement).style.transform = 'translateY(-2px)';
  });
  badgeContainer.addEventListener('mouseleave', () => {
    (badgeContainer as HTMLElement).style.transform = 'translateY(0)';
  });

  // Close button
  badgeContainer.querySelector('#trustmail-badge-close')?.addEventListener('click', (e) => {
    e.stopPropagation();
    badgeContainer?.remove();
    badgeContainer = null;
  });

  // Click opens extension popup (opens via chrome.action — badge is just visual)
  badgeContainer.addEventListener('click', () => {
    chrome.runtime.sendMessage({ type: 'OPEN_POPUP' });
  });

  document.body.appendChild(badgeContainer);
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────

init();
