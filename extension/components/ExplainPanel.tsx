/**
 * ExplainPanel — SHAP + LIME explanation visualization
 */

import { motion } from 'framer-motion';
import { Info } from 'lucide-react';
import type { AnalyzeResponse } from '../services/api';

interface Props {
  result: AnalyzeResponse;
}

export function ExplainPanel({ result }: Props) {
  const shap = result.shap_explanation;
  const lime = result.lime_explanation;

  if (!shap && !lime && !result.top_reasons?.length) {
    return (
      <div className="text-center py-8 text-slate-500 text-sm">
        <Info className="w-8 h-8 mx-auto mb-2 text-slate-700" />
        <p>No explanation available.</p>
        <p className="text-xs mt-1">Enable "Include Explanations" in settings for detailed AI reasoning.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Top Reasons */}
      {result.top_reasons && result.top_reasons.length > 0 && (
        <div className="glass-card p-3">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Why This Classification</h3>
          <div className="space-y-1.5">
            {result.top_reasons.map((reason, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="text-sm text-slate-300 flex items-start gap-2"
              >
                <span className="text-cyan-500 flex-shrink-0 mt-0.5">›</span>
                <span>{reason}</span>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* SHAP Top Features */}
      {shap && shap.top_features && shap.top_features.length > 0 && (
        <div className="glass-card p-3">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
            SHAP Feature Importance
          </h3>
          <div className="space-y-2">
            {shap.top_features.slice(0, 10).map((feat, i) => {
              const isPhishing = feat.direction === 'phishing';
              const magnitude = Math.abs(feat.importance);
              const barWidth = Math.min(magnitude * 200, 100);
              const color = isPhishing ? '#ef4444' : '#22c55e';

              return (
                <div key={i}>
                  <div className="flex justify-between text-xs mb-0.5">
                    <span className="text-slate-400 font-mono truncate max-w-[60%]">
                      {feat.feature.replace(/_/g, ' ')}
                    </span>
                    <span style={{ color }}>
                      {isPhishing ? '+' : '-'}{magnitude.toFixed(3)}
                    </span>
                  </div>
                  <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                    <motion.div
                      className="h-full rounded-full"
                      style={{ background: color, width: `${barWidth}%` }}
                      initial={{ width: 0 }}
                      animate={{ width: `${barWidth}%` }}
                      transition={{ duration: 0.4, delay: i * 0.03 }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
          <p className="text-xs text-slate-600 mt-2">
            Base rate: {((shap.base_value ?? 0) * 100).toFixed(1)}%
          </p>
        </div>
      )}

      {/* LIME Top Features */}
      {lime && lime.top_features && lime.top_features.length > 0 && (
        <div className="glass-card p-3">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
            LIME Text Explanation
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {lime.top_features.slice(0, 12).map((feat, i) => {
              const isPhishing = feat.direction === 'phishing';
              const color = isPhishing ? '#ef4444' : '#22c55e';
              const opacity = 0.3 + Math.abs(feat.importance) * 4;
              return (
                <span
                  key={i}
                  className="text-xs px-2 py-0.5 rounded font-medium"
                  style={{
                    color,
                    background: `${color}${Math.round(opacity * 40).toString(16).padStart(2, '0')}`,
                    border: `1px solid ${color}44`,
                  }}
                >
                  {feat.feature}
                </span>
              );
            })}
          </div>
          <p className="text-xs text-slate-600 mt-2">
            Local prediction: {((lime.local_prediction ?? 0) * 100).toFixed(1)}%
            · Score: {(lime.score ?? 0).toFixed(3)}
          </p>
        </div>
      )}
    </div>
  );
}
