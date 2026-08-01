/**
 * TrustMail API Client
 * =====================
 * TypeScript client for the local TrustMail backend.
 * All requests go to localhost — no external services.
 *
 * Privacy: Raw email content is sent to the local API only.
 * The content never leaves the device (unless the user
 * has configured a remote self-hosted backend).
 */

// ── Request types ──────────────────────────────────────────────────────────────

export interface EmailHeaders {
  from?: string;
  reply_to?: string;
  return_path?: string;
  spf?: string;
  dkim?: string;
  dmarc?: string;
  authentication_results?: string;
  received?: string[];
}

export interface AttachmentMetadata {
  filename: string;
  mime_type?: string;
  size_bytes?: number;
  extension?: string;
}

export interface AnalyzeRequest {
  subject?: string;
  body_text?: string;
  body_html?: string;
  sender?: string;
  sender_domain?: string;
  reply_to?: string;
  return_path?: string;
  urls?: string[];
  attachments?: AttachmentMetadata[];
  headers?: EmailHeaders;
  email_id?: string;
  platform?: string;
  include_explanation?: boolean;
}

// ── Response types ─────────────────────────────────────────────────────────────

export type RiskLevel = 'safe' | 'low_risk' | 'suspicious' | 'phishing' | 'highly_dangerous';

export interface HeaderFinding {
  check: string;
  result: string;
  severity: string;
  detail?: string;
  score_contribution: number;
}

export interface URLFinding {
  url: string;
  risk_score: number;
  threats: string[];
  is_shortened: boolean;
  is_ip_based: boolean;
  is_homograph: boolean;
  is_typosquatting: boolean;
  suspicious_tld: boolean;
  redirect_depth: number;
  decoded_url?: string;
}

export interface NLPFinding {
  category: string;
  confidence: number;
  matched_phrases: string[];
  score_contribution: number;
}

export interface FeatureImportanceItem {
  feature: string;
  importance: number;
  direction: string;
}

export interface SHAPExplanation {
  top_features: FeatureImportanceItem[];
  base_value: number;
  expected_value: number;
  shap_values_summary?: Record<string, number>;
}

export interface LIMEExplanation {
  top_features: FeatureImportanceItem[];
  intercept: number;
  local_prediction: number;
  score: number;
}

export interface ModelPrediction {
  model_name: string;
  phishing_probability: number;
  weight: number;
  weighted_contribution: number;
}

export interface AnalyzeResponse {
  risk_level: RiskLevel;
  risk_score: number;
  confidence: number;
  threat_categories: string[];
  header_findings: HeaderFinding[];
  url_findings: URLFinding[];
  nlp_findings: NLPFinding[];
  attachment_findings: unknown[];
  shap_explanation?: SHAPExplanation;
  lime_explanation?: LIMEExplanation;
  top_reasons: string[];
  suspicious_keywords: string[];
  model_predictions: ModelPrediction[];
  reply_to_mismatch: boolean;
  email_id?: string;
  scan_duration_ms?: number;
  model_version: string;
  analysis_timestamp?: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  models_loaded: boolean;
  uptime_seconds: number;
}

// ── API Client ────────────────────────────────────────────────────────────────

export class TrustMailAPI {
  private baseUrl: string;
  private readonly timeout = 30_000; // 30s timeout

  constructor(baseUrl = 'http://127.0.0.1:8000') {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  private async fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        signal: controller.signal,
        ...options,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(`API error ${response.status}: ${err.detail ?? response.statusText}`);
      }

      return response.json() as Promise<T>;
    } finally {
      clearTimeout(timer);
    }
  }

  async health(): Promise<HealthResponse> {
    return this.fetchJSON<HealthResponse>('/health');
  }

  async analyze(request: AnalyzeRequest): Promise<AnalyzeResponse> {
    return this.fetchJSON<AnalyzeResponse>('/api/v1/analyze', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async analyzeURLs(urls: string[]): Promise<unknown> {
    return this.fetchJSON('/api/v1/urls', {
      method: 'POST',
      body: JSON.stringify({ urls }),
    });
  }

  async analyzeHeaders(headers: EmailHeaders): Promise<unknown> {
    return this.fetchJSON('/api/v1/headers', {
      method: 'POST',
      body: JSON.stringify({ headers }),
    });
  }

  async explain(request: AnalyzeRequest): Promise<unknown> {
    return this.fetchJSON('/api/v1/explain', {
      method: 'POST',
      body: JSON.stringify({ email: request, explanation_methods: ['shap', 'lime'] }),
    });
  }
}
