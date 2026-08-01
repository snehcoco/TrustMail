/**
 * ScanHistory — Shows recent email scans from local storage
 */

import { useState, useEffect } from 'react';
import { Clock, Trash2 } from 'lucide-react';
import { clsx } from 'clsx';
import { StorageService, type ScanRecord } from '../services/storage';

const RISK_COLORS: Record<string, string> = {
  safe: '#22c55e', low_risk: '#84cc16', suspicious: '#f59e0b',
  phishing: '#ef4444', highly_dangerous: '#dc2626',
};

export function ScanHistory() {
  const [history, setHistory] = useState<ScanRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    StorageService.getScanHistory().then((h) => {
      setHistory(h);
      setLoading(false);
    });
  }, []);

  const clearHistory = async () => {
    await StorageService.clearHistory();
    setHistory([]);
  };

  if (loading) return <div className="text-center py-8 text-slate-500 text-sm">Loading...</div>;

  if (history.length === 0) {
    return (
      <div className="text-center py-8">
        <Clock className="w-8 h-8 mx-auto mb-2 text-slate-700" />
        <p className="text-slate-500 text-sm">No scan history yet.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
          Recent Scans ({history.length})
        </h3>
        <button
          onClick={clearHistory}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-red-400 transition-colors"
        >
          <Trash2 className="w-3 h-3" />
          Clear
        </button>
      </div>

      <div className="space-y-2">
        {history.slice(0, 20).map((scan) => {
          const color = RISK_COLORS[scan.riskLevel] ?? '#6b7280';
          const date = new Date(scan.timestamp).toLocaleString();
          const pct = Math.round(scan.riskScore * 100);

          return (
            <div key={scan.id} className="glass-card p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-200 truncate">
                    {scan.subject ?? '(No subject)'}
                  </p>
                  <p className="text-xs text-slate-500 truncate">{scan.sender}</p>
                  <p className="text-xs text-slate-600">{date} · {scan.platform}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-sm font-bold" style={{ color }}>{pct}%</p>
                  <p className="text-xs capitalize" style={{ color }}>
                    {scan.riskLevel.replace('_', ' ')}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
