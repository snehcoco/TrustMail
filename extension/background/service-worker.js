/**
 * TrustMail Background Service Worker (Plain JS — Dev Build)
 * ===========================================================
 * This is the development build that runs without npm/Vite.
 * For production, run: npm run build in the extension/ directory.
 */

const CACHE_TTL_MS = 5 * 60 * 1000;
const scanCache = new Map();

const RISK_COLORS = {
  safe: '#22c55e',
  low_risk: '#84cc16',
  suspicious: '#f59e0b',
  phishing: '#ef4444',
  highly_dangerous: '#dc2626',
};

const RISK_LABELS = {
  safe: '✓',
  low_risk: '!',
  suspicious: '?',
  phishing: '⚠',
  highly_dangerous: '⛔',
};

// ── Settings helpers ──────────────────────────────────────────────────────────

function getSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get(['trustmail_settings'], (result) => {
      resolve({
        backendUrl: 'http://127.0.0.1:8000',
        includeExplanations: true,
        autoScan: true,
        ...result.trustmail_settings,
      });
    });
  });
}

function addToHistory(scan) {
  chrome.storage.local.get(['trustmail_history'], (result) => {
    const history = result.trustmail_history || [];
    const filtered = history.filter((h) => h.id !== scan.id);
    const updated = [scan, ...filtered].slice(0, 100);
    chrome.storage.local.set({ trustmail_history: updated });
  });
}

// ── Badge ─────────────────────────────────────────────────────────────────────

function updateBadge(riskLevel, tabId) {
  const color = RISK_COLORS[riskLevel] || '#6b7280';
  const label = RISK_LABELS[riskLevel] || '?';
  const opts = tabId ? { color, tabId } : { color };
  const lblOpts = tabId ? { text: label, tabId } : { text: label };
  chrome.action.setBadgeBackgroundColor(opts);
  chrome.action.setBadgeText(lblOpts);
}

// ── Core analysis ─────────────────────────────────────────────────────────────

/**
 * Safe base64 cache key that handles non-Latin1 characters
 * (emoji, CJK, Arabic, etc.) in sender/subject fields.
 * btoa() only accepts Latin1; we encode to UTF-8 bytes first.
 */
function makeCacheKey(sender, subject) {
  const raw = `${sender || ''}::${subject || ''}`;
  const bytes = new TextEncoder().encode(raw).slice(0, 96);
  return btoa(String.fromCharCode(...bytes)).slice(0, 32);
}

async function analyzeEmail(email, tabId) {
  const cacheKey = makeCacheKey(email.sender, email.subject);
  const cached = scanCache.get(cacheKey);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
    return { success: true, data: { ...cached.result, fromCache: true } };
  }

  const settings = await getSettings();
  try {
    const resp = await fetch(`${settings.backendUrl}/api/v1/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject: email.subject,
        body_text: email.bodyText,
        body_html: email.bodyHtml,
        sender: email.sender,
        sender_domain: email.senderDomain,
        reply_to: email.replyTo,
        urls: email.urls || [],
        platform: email.platform,
        email_id: email.emailId,
        include_explanation: settings.includeExplanations,
      }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      return { success: false, error: err.detail || `API error ${resp.status}` };
    }

    const result = await resp.json();
    scanCache.set(cacheKey, { result, timestamp: Date.now() });

    addToHistory({
      id: email.emailId || cacheKey,
      timestamp: new Date().toISOString(),
      platform: email.platform || 'unknown',
      riskLevel: result.risk_level,
      riskScore: result.risk_score,
      subject: email.subject,
      sender: email.sender,
    });

    updateBadge(result.risk_level, tabId);
    return { success: true, data: result };
  } catch (err) {
    return { success: false, error: err.message || 'Backend unreachable. Is the server running?' };
  }
}

// ── Message routing ───────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const tabId = sender.tab?.id;

  if (request.type === 'ANALYZE_EMAIL') {
    analyzeEmail(request.payload, tabId).then(sendResponse);
    return true;
  }

  // ── Lightweight inbox row scan ─────────────────────────────────────────
  // Sends only subject + sender (no body) for fast inbox indicators.
  // The full analysis still runs when the user opens the email.
  if (request.type === 'ANALYZE_INBOX_ROW') {
    const { subject, sender, urls, platform, emailId } = request.payload;
    analyzeEmail({
      subject,
      sender,
      senderDomain: sender?.includes('@') ? sender.split('@')[1] : '',
      bodyText: '',   // Intentionally empty — inbox scan is header-only
      bodyHtml: '',
      urls: urls || [],
      platform,
      emailId,
    }, tabId).then(sendResponse);
    return true;
  }

  // ── Store popup result from inbox pill click ────────────────────────────
  // Content script sends this when user clicks an inbox pill.
  // Popup reads it on open to display the pre-loaded result.
  if (request.type === 'SET_POPUP_RESULT') {
    chrome.storage.local.set({ trustmail_popup_result: request.payload }, () => {
      sendResponse({ success: true });
    });
    return true;
  }

  if (request.type === 'CHECK_BACKEND') {
    getSettings().then((s) =>
      fetch(`${s.backendUrl}/health`)
        .then((r) => r.json())
        .then((data) => sendResponse({ success: true, data }))
        .catch(() => sendResponse({ success: false, error: 'Backend offline' }))
    );
    return true;
  }

  if (request.type === 'GET_SETTINGS') {
    getSettings().then((s) => sendResponse({ success: true, data: s }));
    return true;
  }

  if (request.type === 'GET_SCAN_HISTORY') {
    chrome.storage.local.get(['trustmail_history'], (r) => {
      sendResponse({ success: true, data: r.trustmail_history || [] });
    });
    return true;
  }

  if (request.type === 'CLEAR_HISTORY') {
    chrome.storage.local.remove(['trustmail_history'], () => sendResponse({ success: true }));
    return true;
  }
});

// ── Alarm: clean stale cache every 10 minutes ─────────────────────────────────
chrome.alarms.create('CLEAN_CACHE', { periodInMinutes: 10 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'CLEAN_CACHE') {
    const now = Date.now();
    for (const [key, val] of scanCache.entries()) {
      if (now - val.timestamp > CACHE_TTL_MS) scanCache.delete(key);
    }
  }
});

console.log('[TrustMail] Service worker loaded ✓');
