/**
 * Shared Constants — TrustMail
 * (TypeScript version for extension)
 */

export const RISK_LEVELS = ['safe', 'low_risk', 'suspicious', 'phishing', 'highly_dangerous'] as const;
export type RiskLevel = typeof RISK_LEVELS[number];

export const RISK_THRESHOLDS = {
  safe: 0,
  low_risk: 0.20,
  suspicious: 0.45,
  phishing: 0.65,
  highly_dangerous: 0.85,
} as const;

export const RISK_LABELS: Record<RiskLevel, string> = {
  safe: 'Safe',
  low_risk: 'Low Risk',
  suspicious: 'Suspicious',
  phishing: 'Phishing',
  highly_dangerous: 'Highly Dangerous',
};

export const RISK_COLORS: Record<RiskLevel, string> = {
  safe: '#22c55e',
  low_risk: '#84cc16',
  suspicious: '#f59e0b',
  phishing: '#ef4444',
  highly_dangerous: '#dc2626',
};

export const SUPPORTED_PLATFORMS = ['gmail', 'outlook', 'yahoo', 'protonmail', 'outlook365'] as const;
export type EmailPlatform = typeof SUPPORTED_PLATFORMS[number];

export const API_ENDPOINTS = {
  analyze: '/api/v1/analyze',
  batch: '/api/v1/batch',
  headers: '/api/v1/headers',
  urls: '/api/v1/urls',
  attachments: '/api/v1/attachments',
  explain: '/api/v1/explain',
  health: '/health',
  version: '/version',
  metrics: '/metrics',
  status: '/status',
} as const;

export const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000';
export const MAX_EMAIL_BODY_LENGTH = 50_000;
export const MAX_URLS_PER_EMAIL = 100;
export const CACHE_TTL_MS = 5 * 60 * 1000;
