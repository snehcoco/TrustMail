/**
 * URLAnalysis — URL threat findings display
 */

import { ExternalLink, AlertTriangle, ShieldAlert } from 'lucide-react';
import { clsx } from 'clsx';

interface URLFinding {
  url: string;
  risk_score: number;
  threats: string[];
  is_shortened: boolean;
  is_ip_based: boolean;
  is_homograph: boolean;
  is_typosquatting: boolean;
  suspicious_tld: boolean;
  decoded_url?: string;
}

interface Props {
  findings: URLFinding[];
}

export function URLAnalysis({ findings }: Props) {
  if (!findings || findings.length === 0) {
    return (
      <div className="text-center py-8 text-slate-500 text-sm">
        No URLs found in this email.
      </div>
    );
  }

  const sorted = [...findings].sort((a, b) => b.risk_score - a.risk_score);

  return (
    <div className="space-y-2">
      {sorted.map((finding, i) => {
        const pct = Math.round(finding.risk_score * 100);
        const color = pct >= 65 ? '#ef4444' : pct >= 40 ? '#f59e0b' : '#22c55e';
        const truncated = finding.url.length > 40 ? finding.url.slice(0, 40) + '…' : finding.url;

        return (
          <div key={i} className="glass-card p-3">
            <div className="flex items-start justify-between gap-2 mb-2">
              <code className="text-xs text-slate-300 font-mono break-all leading-relaxed flex-1">
                {truncated}
              </code>
              <span className="text-sm font-bold flex-shrink-0" style={{ color }}>
                {pct}%
              </span>
            </div>

            {finding.threats.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {finding.threats.map((threat) => (
                  <span
                    key={threat}
                    className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700"
                  >
                    {threat.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            )}

            {/* Threat badges */}
            <div className="flex gap-1.5 mt-2 flex-wrap">
              {finding.is_ip_based && <ThreatTag label="IP URL" />}
              {finding.is_shortened && <ThreatTag label="Shortened" />}
              {finding.is_homograph && <ThreatTag label="Homograph" color="#dc2626" />}
              {finding.is_typosquatting && <ThreatTag label="Typosquat" color="#dc2626" />}
              {finding.suspicious_tld && <ThreatTag label="Bad TLD" />}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ThreatTag({ label, color = '#f59e0b' }: { label: string; color?: string }) {
  return (
    <span
      className="text-[10px] px-1.5 py-0.5 rounded font-semibold"
      style={{ color, background: `${color}22`, border: `1px solid ${color}44` }}
    >
      {label}
    </span>
  );
}
