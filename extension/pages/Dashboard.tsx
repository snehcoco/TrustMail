/**
 * TrustMail Dashboard — Main UI Page
 * =====================================
 * The primary popup view. Shows:
 *   - TrustMail header with status
 *   - Risk Meter (circular gauge)
 *   - Classification badge
 *   - Threat breakdown tabs (Headers | URLs | NLP | Attachments)
 *   - Top reasons / explanation
 *   - Model predictions breakdown
 *   - Scan history
 *   - Export & Settings actions
 */

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Shield, ShieldAlert, ShieldCheck, ShieldX, Activity,
  Globe, Mail, Link2, Paperclip, ChevronRight, Clock,
  Download, Settings, Wifi, WifiOff, RefreshCw, ExternalLink,
} from 'lucide-react';
import { clsx } from 'clsx';
import { RiskMeter } from '../components/RiskMeter';
import { ConfidenceGauge } from '../components/ConfidenceGauge';
import { ThreatBreakdown } from '../components/ThreatBreakdown';
import { HeaderAnalysis } from '../components/HeaderAnalysis';
import { URLAnalysis } from '../components/URLAnalysis';
import { ExplainPanel } from '../components/ExplainPanel';
import { ScanHistory } from '../components/ScanHistory';
import { ExportReport } from '../components/ExportReport';
import { ThemeToggle } from '../components/ThemeToggle';
import { useAnalysis } from '../hooks/useAnalysis';
import { useSettings } from '../hooks/useSettings';
import type { AnalyzeResponse } from '../services/api';

// ── Risk level display config ─────────────────────────────────────────────────
const RISK_CONFIG: Record<string, {
  label: string; icon: typeof Shield; color: string; bgClass: string; description: string;
}> = {
  safe: {
    label: 'Safe', icon: ShieldCheck, color: 'var(--risk-safe)', bgClass: 'risk-bg-safe',
    description: 'No significant threats detected.',
  },
  low_risk: {
    label: 'Low Risk', icon: Shield, color: 'var(--risk-low)', bgClass: 'risk-bg-low_risk',
    description: 'Minor concerns found — proceed with caution.',
  },
  suspicious: {
    label: 'Suspicious', icon: ShieldAlert, color: 'var(--risk-suspicious)', bgClass: 'risk-bg-suspicious',
    description: 'Multiple suspicious indicators detected.',
  },
  phishing: {
    label: 'Phishing', icon: ShieldX, color: 'var(--risk-phishing)', bgClass: 'risk-bg-phishing',
    description: 'High probability phishing email. Do not click links.',
  },
  highly_dangerous: {
    label: 'Highly Dangerous', icon: ShieldX, color: 'var(--risk-dangerous)', bgClass: 'risk-bg-highly_dangerous',
    description: '⛔ Extremely dangerous. Delete immediately.',
  },
};

type ActiveTab = 'overview' | 'headers' | 'urls' | 'explain' | 'history';

export function Dashboard() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('overview');
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [showExport, setShowExport] = useState(false);
  const { settings } = useSettings();

  // Check backend on mount
  useEffect(() => {
    chrome.runtime.sendMessage({ type: 'CHECK_BACKEND' }).then((resp) => {
      setBackendOnline(resp?.success ?? false);
    });

    // Request current page analysis
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]?.id) {
        chrome.tabs.sendMessage(tabs[0].id, { type: 'GET_CURRENT_RESULT' }, (resp) => {
          if (chrome.runtime.lastError) return; // Tab might not have content script
          if (resp?.data) setResult(resp.data as AnalyzeResponse);
        });
      }
    });
  }, []);

  const riskConfig = result ? (RISK_CONFIG[result.risk_level] ?? RISK_CONFIG.suspicious) : null;
  const RiskIcon = riskConfig?.icon ?? Shield;

  const tabs: { id: ActiveTab; label: string; icon: typeof Shield; count?: number }[] = [
    { id: 'overview', label: 'Overview', icon: Activity },
    { id: 'headers', label: 'Headers', icon: Mail, count: result?.header_findings?.length },
    { id: 'urls', label: 'URLs', icon: Link2, count: result?.url_findings?.length },
    { id: 'explain', label: 'Explain', icon: Globe },
    { id: 'history', label: 'History', icon: Clock },
  ];

  return (
    <div className="w-full min-h-screen bg-[#050a0f] text-slate-100 flex flex-col" style={{ width: 420, minHeight: 560 }}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center">
            <Shield className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-base gradient-text">TrustMail</h1>
            <p className="text-xs text-slate-500">AI Email Shield</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Backend status indicator */}
          <div className={clsx(
            'flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border',
            backendOnline === true && 'text-green-400 border-green-800 bg-green-950',
            backendOnline === false && 'text-red-400 border-red-900 bg-red-950',
            backendOnline === null && 'text-slate-500 border-slate-700 bg-slate-900',
          )}>
            {backendOnline === true ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            {backendOnline === true ? 'Online' : backendOnline === false ? 'Offline' : '...'}
          </div>
          <ThemeToggle />
          <button
            onClick={() => chrome.runtime.openOptionsPage()}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* ── Risk Summary Card ──────────────────────────────────────────────── */}
      {result && riskConfig && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className={clsx(
            'mx-4 mt-4 p-4 rounded-2xl border glass-card',
            riskConfig.bgClass,
          )}
        >
          <div className="flex items-center gap-4">
            <RiskMeter score={result.risk_score} riskLevel={result.risk_level} />

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <RiskIcon className="w-5 h-5" style={{ color: riskConfig.color }} />
                <span className="font-bold text-lg" style={{ color: riskConfig.color }}>
                  {riskConfig.label}
                </span>
              </div>
              <p className="text-xs text-slate-400 mb-2">{riskConfig.description}</p>
              <ConfidenceGauge confidence={result.confidence} />
            </div>
          </div>

          {/* Top reasons */}
          {result.top_reasons.length > 0 && (
            <div className="mt-3 space-y-1">
              {result.top_reasons.slice(0, 3).map((reason, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-slate-300">
                  <ChevronRight className="w-3 h-3 mt-0.5 flex-shrink-0" style={{ color: riskConfig.color }} />
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          )}
        </motion.div>
      )}

      {/* ── Empty State ────────────────────────────────────────────────────── */}
      {!result && !isLoading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex-1 flex flex-col items-center justify-center gap-4 px-8 py-12"
        >
          <div className="w-20 h-20 rounded-full bg-slate-900 border border-slate-700 flex items-center justify-center">
            <Mail className="w-10 h-10 text-slate-600" />
          </div>
          <div className="text-center">
            <h2 className="text-base font-semibold text-slate-300 mb-1">No Email Detected</h2>
            <p className="text-sm text-slate-500">Open an email in Gmail, Outlook, Yahoo, or ProtonMail to start scanning.</p>
          </div>
          {backendOnline === false && (
            <div className="w-full p-3 rounded-xl bg-red-950 border border-red-900 text-xs text-red-300">
              <strong>Backend offline.</strong> Start the server:<br />
              <code className="font-mono text-red-200">cd backend && python app.py</code>
            </div>
          )}
        </motion.div>
      )}

      {/* ── Loading State ─────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <RefreshCw className="w-8 h-8 text-cyan-500 animate-spin mx-auto mb-3" />
            <p className="text-sm text-slate-400 animate-scan">Analyzing email...</p>
          </div>
        </div>
      )}

      {/* ── Tabs ──────────────────────────────────────────────────────────── */}
      {result && (
        <>
          <div className="flex border-b border-slate-800 mt-4 px-4 gap-1">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={clsx(
                    'flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-lg border-b-2 transition-colors',
                    activeTab === tab.id
                      ? 'text-cyan-400 border-cyan-400 bg-cyan-950/30'
                      : 'text-slate-500 border-transparent hover:text-slate-300 hover:bg-slate-800/50'
                  )}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {tab.label}
                  {tab.count !== undefined && tab.count > 0 && (
                    <span className="bg-slate-700 text-slate-300 text-xs rounded-full px-1.5 py-0.5 min-w-[18px] text-center">
                      {tab.count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* ── Tab Content ──────────────────────────────────────────────── */}
          <div className="flex-1 overflow-y-auto px-4 py-3">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                transition={{ duration: 0.15 }}
              >
                {activeTab === 'overview' && (
                  <ThreatBreakdown result={result} />
                )}
                {activeTab === 'headers' && (
                  <HeaderAnalysis findings={result.header_findings} />
                )}
                {activeTab === 'urls' && (
                  <URLAnalysis findings={result.url_findings} />
                )}
                {activeTab === 'explain' && (
                  <ExplainPanel result={result} />
                )}
                {activeTab === 'history' && (
                  <ScanHistory />
                )}
              </motion.div>
            </AnimatePresence>
          </div>

          {/* ── Footer Actions ───────────────────────────────────────────── */}
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800 bg-slate-950/50">
            <span className="text-xs text-slate-600">
              {result.scan_duration_ms}ms · v{result.model_version}
            </span>
            <div className="flex gap-2">
              <ExportReport result={result} />
              <button
                onClick={() => chrome.runtime.openOptionsPage()}
                className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 px-3 py-1.5 rounded-lg hover:bg-slate-800"
              >
                <ExternalLink className="w-3 h-3" />
                Report
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
