/**
 * ThreatBreakdown — Overview tab showing all threat categories
 */

import { motion } from 'framer-motion';
import { AlertTriangle, CheckCircle, Shield } from 'lucide-react';
import { clsx } from 'clsx';
import type { AnalyzeResponse } from '../services/api';

interface Props {
  result: AnalyzeResponse;
}

export function ThreatBreakdown({ result }: Props) {
  const sections = [
    {
      title: 'Email Authentication',
      items: result.header_findings?.map((f) => ({
        label: f.check,
        value: f.result,
        severity: f.severity,
        detail: f.detail,
      })) ?? [],
    },
    {
      title: 'NLP Threats Detected',
      items: result.nlp_findings?.map((f) => ({
        label: f.category.replace(/_/g, ' '),
        value: `${Math.round(f.confidence * 100)}% confidence`,
        severity: f.confidence > 0.7 ? 'critical' : 'medium',
        detail: f.matched_phrases?.slice(0, 2).join(', '),
      })) ?? [],
    },
    {
      title: 'Threat Categories',
      items: result.threat_categories?.map((cat) => ({
        label: cat.replace(/_/g, ' '),
        value: 'Detected',
        severity: 'high',
        detail: undefined,
      })) ?? [],
    },
  ];

  const severityColor: Record<string, string> = {
    critical: '#ef4444', high: '#f59e0b', medium: '#6366f1', low: '#22c55e', info: '#6b7280',
  };

  return (
    <div className="space-y-4">
      {/* Suspicious keywords */}
      {result.suspicious_keywords && result.suspicious_keywords.length > 0 && (
        <div className="glass-card p-3">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
            Suspicious Keywords
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {result.suspicious_keywords.slice(0, 12).map((kw) => (
              <span key={kw} className="text-xs px-2 py-0.5 rounded-full bg-red-950 border border-red-900 text-red-300">
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Model breakdown */}
      {result.model_predictions && result.model_predictions.length > 0 && (
        <div className="glass-card p-3">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
            AI Model Predictions
          </h3>
          <div className="space-y-2">
            {result.model_predictions.map((pred) => {
              const pct = Math.round(pred.phishing_probability * 100);
              const color = pct >= 65 ? '#ef4444' : pct >= 45 ? '#f59e0b' : '#22c55e';
              return (
                <div key={pred.model_name}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-400">{pred.model_name}</span>
                    <span style={{ color }}>{pct}%</span>
                  </div>
                  <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                    <motion.div
                      className="h-full rounded-full"
                      style={{ background: color }}
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{ duration: 0.5, ease: 'easeOut' }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Threat sections */}
      {sections.map((section) =>
        section.items.length > 0 ? (
          <div key={section.title} className="glass-card p-3">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
              {section.title}
            </h3>
            <div className="space-y-2">
              {section.items.map((item, i) => (
                <div key={i} className="flex items-start gap-2">
                  <div
                    className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0"
                    style={{ background: severityColor[item.severity] ?? '#6b7280' }}
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-slate-200 capitalize">{item.label}</span>
                      <span className="text-xs text-slate-500">{item.value}</span>
                    </div>
                    {item.detail && (
                      <p className="text-xs text-slate-500 mt-0.5 truncate">{item.detail}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null
      )}

      {/* All clear */}
      {sections.every((s) => s.items.length === 0) && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-green-950/30 border border-green-900/50">
          <CheckCircle className="w-6 h-6 text-green-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-green-400">All Clear</p>
            <p className="text-xs text-slate-500">No significant threats detected in this email.</p>
          </div>
        </div>
      )}
    </div>
  );
}
