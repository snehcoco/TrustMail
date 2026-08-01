/**
 * ConfidenceGauge — Linear progress bar for model confidence
 */

import { motion } from 'framer-motion';

interface ConfidenceGaugeProps {
  confidence: number; // [0, 1]
}

export function ConfidenceGauge({ confidence }: ConfidenceGaugeProps) {
  const pct = Math.round(confidence * 100);
  const color = pct >= 80 ? '#22c55e' : pct >= 60 ? '#f59e0b' : '#6b7280';

  return (
    <div className="w-full">
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-slate-500">Confidence</span>
        <span className="text-xs font-semibold" style={{ color }}>{pct}%</span>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ background: `linear-gradient(90deg, ${color}88, ${color})` }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: 'easeOut', delay: 0.2 }}
        />
      </div>
    </div>
  );
}
