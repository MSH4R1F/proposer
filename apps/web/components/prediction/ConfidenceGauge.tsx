'use client';

import { cn } from '@/lib/utils';
import { formatConfidence } from '@/lib/utils/formatters';

interface ConfidenceGaugeProps {
  confidence: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

const sizeConfig = {
  sm: { size: 60, stroke: 6, fontSize: 'text-sm' },
  md: { size: 80, stroke: 8, fontSize: 'text-base' },
  lg: { size: 120, stroke: 10, fontSize: 'text-xl' },
};

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'text-green-500';
  if (confidence >= 0.6) return 'text-yellow-500';
  if (confidence >= 0.4) return 'text-orange-500';
  return 'text-red-500';
}

export function ConfidenceGauge({
  confidence,
  size = 'md',
  showLabel = true,
  className,
}: ConfidenceGaugeProps) {
  const config = sizeConfig[size];
  const radius = (config.size - config.stroke) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - confidence * circumference;
  const percentage = Math.round(confidence * 100);

  return (
    <div className={cn('flex flex-col items-center gap-2', className)}>
      <div className="relative" style={{ width: config.size, height: config.size }}>
        {/* Background circle */}
        <svg
          className="absolute inset-0 -rotate-90"
          width={config.size}
          height={config.size}
        >
          <circle
            cx={config.size / 2}
            cy={config.size / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={config.stroke}
            className="text-muted"
          />
          <circle
            cx={config.size / 2}
            cy={config.size / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={config.stroke}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className={cn('transition-all duration-500', getConfidenceColor(confidence))}
          />
        </svg>
        {/* Center text */}
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={cn('font-bold', config.fontSize)}>
            {percentage}%
          </span>
        </div>
      </div>
      {showLabel && (
        <span className="text-xs text-muted-foreground">
          {formatConfidence(confidence)} Confidence
        </span>
      )}
    </div>
  );
}
