/**
 * ExportReport — Download analysis as JSON or formatted text
 */

import { Download } from 'lucide-react';
import { useState } from 'react';
import type { AnalyzeResponse } from '../services/api';

interface Props {
  result: AnalyzeResponse;
}

export function ExportReport({ result }: Props) {
  const [open, setOpen] = useState(false);

  const exportJSON = () => {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trustmail-report-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setOpen(false);
  };

  const exportText = () => {
    const lines = [
      '=== TrustMail Security Report ===',
      `Date: ${new Date().toISOString()}`,
      `Risk Level: ${result.risk_level.toUpperCase()}`,
      `Risk Score: ${Math.round(result.risk_score * 100)}%`,
      `Confidence: ${Math.round(result.confidence * 100)}%`,
      '',
      '--- Top Findings ---',
      ...(result.top_reasons ?? []).map((r) => `• ${r}`),
      '',
      '--- Header Analysis ---',
      ...(result.header_findings ?? []).map((h) => `${h.check}: ${h.result} — ${h.detail ?? ''}`),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trustmail-report-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 px-3 py-1.5 rounded-lg hover:bg-slate-800"
      >
        <Download className="w-3 h-3" />
        Export
      </button>

      {open && (
        <div className="absolute bottom-full right-0 mb-1 glass-card p-1 min-w-[120px] z-50">
          <button
            onClick={exportJSON}
            className="w-full text-left text-xs text-slate-300 hover:text-white px-3 py-2 rounded-lg hover:bg-slate-700"
          >
            JSON Report
          </button>
          <button
            onClick={exportText}
            className="w-full text-left text-xs text-slate-300 hover:text-white px-3 py-2 rounded-lg hover:bg-slate-700"
          >
            Text Report
          </button>
        </div>
      )}
    </div>
  );
}
