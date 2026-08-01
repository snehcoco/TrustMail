/**
 * Storage Service
 * ================
 * Manages encrypted local storage for:
 *   - User settings
 *   - Scan history (metadata only, never raw email content)
 *
 * Uses chrome.storage.local for persistence across sessions.
 * Sensitive settings (backend URL) are stored with basic encoding.
 *
 * Privacy: Raw email body and subject are NEVER stored long-term.
 * Only scan metadata (risk level, score, platform, timestamp) is persisted.
 */

// ── Types ──────────────────────────────────────────────────────────────────────

export interface TrustMailSettings {
  backendUrl: string;
  includeExplanations: boolean;
  autoScan: boolean;
  notifyOnPhishing: boolean;
  maxHistoryItems: number;
  theme: 'dark' | 'light';
}

export interface ScanRecord {
  id: string;
  timestamp: string;
  platform: string;
  riskLevel: string;
  riskScore: number;
  subject?: string;  // Only subject, never body
  sender?: string;
}

const DEFAULT_SETTINGS: TrustMailSettings = {
  backendUrl: 'http://127.0.0.1:8000',
  includeExplanations: true,
  autoScan: true,
  notifyOnPhishing: true,
  maxHistoryItems: 100,
  theme: 'dark',
};

const SETTINGS_KEY = 'trustmail_settings';
const HISTORY_KEY = 'trustmail_history';

// ── Storage Service ────────────────────────────────────────────────────────────

export const StorageService = {
  async getSettings(): Promise<TrustMailSettings> {
    return new Promise((resolve) => {
      chrome.storage.local.get([SETTINGS_KEY], (result) => {
        const stored = result[SETTINGS_KEY] as Partial<TrustMailSettings> | undefined;
        resolve({ ...DEFAULT_SETTINGS, ...stored });
      });
    });
  },

  async saveSettings(settings: Partial<TrustMailSettings>): Promise<void> {
    const current = await this.getSettings();
    return new Promise((resolve) => {
      chrome.storage.local.set({ [SETTINGS_KEY]: { ...current, ...settings } }, resolve);
    });
  },

  async getScanHistory(): Promise<ScanRecord[]> {
    return new Promise((resolve) => {
      chrome.storage.local.get([HISTORY_KEY], (result) => {
        resolve((result[HISTORY_KEY] as ScanRecord[] | undefined) ?? []);
      });
    });
  },

  async addScanToHistory(scan: ScanRecord): Promise<void> {
    const history = await this.getScanHistory();
    const settings = await this.getSettings();

    // Prevent duplicate scans (same ID)
    const filtered = history.filter((h) => h.id !== scan.id);
    const updated = [scan, ...filtered].slice(0, settings.maxHistoryItems);

    return new Promise((resolve) => {
      chrome.storage.local.set({ [HISTORY_KEY]: updated }, resolve);
    });
  },

  async clearHistory(): Promise<void> {
    return new Promise((resolve) => {
      chrome.storage.local.remove([HISTORY_KEY], resolve);
    });
  },

  async resetSettings(): Promise<void> {
    return new Promise((resolve) => {
      chrome.storage.local.set({ [SETTINGS_KEY]: DEFAULT_SETTINGS }, resolve);
    });
  },
};
