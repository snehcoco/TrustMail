/**
 * RiskMeter — Circular SVG gauge showing overall risk score
 * ===========================================================
 * Animated circular progress ring with color coded by risk level.
 * Shows percentage score in the center.
 */

import { motion } from 'framer-motion';

interface RiskMeterProps {
  score: number;       // [0, 1]
  riskLevel: string;
  size?: number;
}

const RISK_COLORS: Record<string, string> = {
  safe: '#22c55e',
  low_risk: '#84cc16',
  suspicious: '#f59e0b',
  phishing: '#ef4444',
  highly_dangerous: '#dc2626',
};

export function RiskMeter({ score, riskLevel, size = 72 }: RiskMeterProps) {
  const color = RISK_COLORS[riskLevel] ?? '#6b7280';
  const radius = (size - 10) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.round(score * 100);
  const strokeDashoffset = circumference - (score * circumference);
  const cx = size / 2;
  const cy = size / 2;

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background track */}
        <circle
          cx={cx} cy={cy} r={radius}
          strokeWidth={6}
          stroke="rgba(255,255,255,0.08)"
          fill="none"
        />
        {/* Progress arc */}
        <motion.circle
          cx={cx} cy={cy} r={radius}
          strokeWidth={6}
          stroke={color}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          style={{ filter: `drop-shadow(0 0 6px ${color}88)` }}
        />
      </svg>
      {/* Center label */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-lg font-bold leading-none" style={{ color }}>
          {pct}%
        </span>
        <span className="text-[9px] text-slate-500 uppercase tracking-wide">Risk</span>
      </div>
    </div>
  );
}
