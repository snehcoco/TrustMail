/**
 * HeaderAnalysis — Email header security findings display
 */

import { CheckCircle, XCircle, AlertTriangle, HelpCircle } from 'lucide-react';
import { clsx } from 'clsx';

interface HeaderFinding {
  check: string;
  result: string;
  severity: string;
  detail?: string;
  score_contribution: number;
}

interface Props {
  findings: HeaderFinding[];
}

const RESULT_ICONS: Record<string, typeof CheckCircle> = {
  Pass: CheckCircle,
  Fail: XCircle,
  Missing: XCircle,
  Suspicious: AlertTriangle,
  Softfail: AlertTriangle,
};

const RESULT_COLORS: Record<string, string> = {
  Pass: '#22c55e',
  Fail: '#ef4444',
  Missing: '#f59e0b',
  Suspicious: '#f59e0b',
  Softfail: '#f59e0b',
};

export function HeaderAnalysis({ findings }: Props) {
  if (!findings || findings.length === 0) {
    return (
      <div className="text-center py-8 text-slate-500 text-sm">
        No header information available.
      </div>
    );
  }

  const critical = findings.filter((f) => f.severity === 'critical' || f.severity === 'high');
  const others = findings.filter((f) => f.severity !== 'critical' && f.severity !== 'high');

  return (
    <div className="space-y-3">
      {critical.length > 0 && (
        <div className="glass-card p-3 border-red-900/50 bg-red-950/20">
          <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-2">
            ⚠ Critical Issues
          </h3>
          {critical.map((f, i) => <FindingRow key={i} finding={f} />)}
        </div>
      )}
      {others.length > 0 && (
        <div className="glass-card p-3">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
            Other Checks
          </h3>
          {others.map((f, i) => <FindingRow key={i} finding={f} />)}
        </div>
      )}
    </div>
  );
}

function FindingRow({ finding }: { finding: HeaderFinding }) {
  const Icon = RESULT_ICONS[finding.result] ?? HelpCircle;
  const color = RESULT_COLORS[finding.result] ?? '#6b7280';

  return (
    <div className="flex items-start gap-3 py-2 border-b border-slate-800/50 last:border-0">
      <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color }} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium text-slate-200">{finding.check}</span>
          <span className="text-xs font-semibold" style={{ color }}>{finding.result}</span>
        </div>
        {finding.detail && (
          <p className="text-xs text-slate-500 mt-0.5">{finding.detail}</p>
        )}
      </div>
    </div>
  );
}
