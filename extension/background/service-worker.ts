/**
 * TrustMail Background Service Worker (MV3)
 * ==========================================
 * Handles:
 *   - Message routing between content scripts and popup
 *   - API communication with the local backend
 *   - Scan result caching in chrome.storage.session
 *   - Backend connectivity checking
 *   - Alarm-based cache cleanup
 *
 * Privacy: Only metadata is stored. Raw email content is NEVER persisted.
 */

import type { AnalyzeRequest, AnalyzeResponse } from '../services/api';
import { TrustMailAPI } from '../services/api';
import { StorageService } from '../services/storage';

// ── Types ──────────────────────────────────────────────────────────────────────

interface ExtractedEmail {
  subject?: string;
  bodyText?: string;
  bodyHtml?: string;
  sender?: string;
  senderDomain?: string;
  replyTo?: string;
  returnPath?: string;
  urls?: string[];
  platform?: string;
  emailId?: string;
}

interface MessageRequest {
  type: string;
  payload?: unknown;
}

interface MessageResponse {
  success: boolean;
  data?: unknown;
  error?: string;
}

// ── Cache for scan results (session-scoped, not persistent) ───────────────────

const scanCache = new Map<string, { result: AnalyzeResponse; timestamp: number }>();
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

function getCacheKey(email: ExtractedEmail): string {
  // Encode to UTF-8 bytes first so non-Latin1 characters (emoji, CJK, Arabic, etc.)
  // in sender/subject don't cause btoa() to throw InvalidCharacterError.
  const raw = `${email.sender ?? ''}::${email.subject ?? ''}`;
  const bytes = new TextEncoder().encode(raw).slice(0, 96);
  return btoa(String.fromCharCode(...bytes)).slice(0, 32);
}

// ── Message handler ──────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener(
  (request: MessageRequest, sender, sendResponse: (response: MessageResponse) => void) => {
    // Return true to indicate async response
    handleMessage(request, sender)
      .then(sendResponse)
      .catch((err) => sendResponse({ success: false, error: String(err) }));
    return true;
  }
);

async function handleMessage(
  request: MessageRequest,
  sender: chrome.runtime.MessageSender
): Promise<MessageResponse> {
  switch (request.type) {
    case 'ANALYZE_EMAIL':
      return analyzeEmail(request.payload as ExtractedEmail);

    case 'CHECK_BACKEND':
      return checkBackend();

    case 'GET_SETTINGS':
      return getSettings();

    case 'GET_SCAN_HISTORY':
      return getScanHistory();

    case 'CLEAR_HISTORY':
      return clearHistory();

    default:
      return { success: false, error: `Unknown message type: ${request.type}` };
  }
}

// ── Core analysis function ────────────────────────────────────────────────────

async function analyzeEmail(email: ExtractedEmail): Promise<MessageResponse> {
  try {
    const cacheKey = getCacheKey(email);
    const cached = scanCache.get(cacheKey);

    // Return cached result if fresh
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return { success: true, data: { ...cached.result, fromCache: true } };
    }

    const settings = await StorageService.getSettings();
    const api = new TrustMailAPI(settings.backendUrl);

    const analyzeReq: AnalyzeRequest = {
      subject: email.subject,
      body_text: email.bodyText,
      body_html: email.bodyHtml,
      sender: email.sender,
      sender_domain: email.senderDomain,
      reply_to: email.replyTo,
      urls: email.urls,
      platform: email.platform,
      email_id: email.emailId,
      include_explanation: settings.includeExplanations,
    };

    const result = await api.analyze(analyzeReq);

    // Cache result (without raw email content)
    scanCache.set(cacheKey, { result, timestamp: Date.now() });

    // Persist scan to history (metadata only, not email content)
    await StorageService.addScanToHistory({
      id: email.emailId ?? cacheKey,
      timestamp: new Date().toISOString(),
      platform: email.platform ?? 'unknown',
      riskLevel: result.risk_level,
      riskScore: result.risk_score,
      subject: email.subject, // Only subject, not body
      sender: email.sender,
    });

    // Update badge icon based on risk
    updateBadge(result.risk_level, sender.tab?.id);

    return { success: true, data: result };
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return { success: false, error };
  }
}

// ── Badge update ──────────────────────────────────────────────────────────────

function updateBadge(riskLevel: string, tabId?: number): void {
  const colors: Record<string, string> = {
    safe: '#22c55e',
    low_risk: '#84cc16',
    suspicious: '#f59e0b',
    phishing: '#ef4444',
    highly_dangerous: '#7f1d1d',
  };

  const labels: Record<string, string> = {
    safe: '✓',
    low_risk: '!',
    suspicious: '?!',
    phishing: '⚠',
    highly_dangerous: '⛔',
  };

  const color = colors[riskLevel] ?? '#6b7280';
  const label = labels[riskLevel] ?? '?';

  chrome.action.setBadgeBackgroundColor({ color, tabId });
  chrome.action.setBadgeText({ text: label, tabId });
}

// ── Backend health check ──────────────────────────────────────────────────────

async function checkBackend(): Promise<MessageResponse> {
  try {
    const settings = await StorageService.getSettings();
    const api = new TrustMailAPI(settings.backendUrl);
    const health = await api.health();
    return { success: true, data: health };
  } catch {
    return { success: false, error: 'Backend not reachable' };
  }
}

// ── Settings & history helpers ────────────────────────────────────────────────

async function getSettings(): Promise<MessageResponse> {
  const settings = await StorageService.getSettings();
  return { success: true, data: settings };
}

async function getScanHistory(): Promise<MessageResponse> {
  const history = await StorageService.getScanHistory();
  return { success: true, data: history };
}

async function clearHistory(): Promise<MessageResponse> {
  await StorageService.clearHistory();
  return { success: true };
}

// ── Alarm: clean stale cache entries every 10 minutes ────────────────────────

chrome.alarms.create('CLEAN_CACHE', { periodInMinutes: 10 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'CLEAN_CACHE') {
    const now = Date.now();
    for (const [key, value] of scanCache.entries()) {
      if (now - value.timestamp > CACHE_TTL_MS) {
        scanCache.delete(key);
      }
    }
  }
});
