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
  sm: { size: 60, stroke: 5, fontSize: 'text-sm', labelSize: 'text-xs' },
  md: { size: 90, stroke: 7, fontSize: 'text-xl', labelSize: 'text-xs' },
  lg: { size: 140, stroke: 10, fontSize: 'text-3xl', labelSize: 'text-sm' },
};

function getConfidenceColor(confidence: number): { stroke: string; bg: string; text: string } {
  if (confidence >= 0.8) return { 
    stroke: 'text-emerald-500', 
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-600 dark:text-emerald-400'
  };
  if (confidence >= 0.6) return { 
    stroke: 'text-amber-500', 
    bg: 'bg-amber-500/10',
    text: 'text-amber-600 dark:text-amber-400'
  };
  if (confidence >= 0.4) return { 
    stroke: 'text-orange-500', 
    bg: 'bg-orange-500/10',
    text: 'text-orange-600 dark:text-orange-400'
  };
  return { 
    stroke: 'text-red-500', 
    bg: 'bg-red-500/10',
    text: 'text-red-600 dark:text-red-400'
  };
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
  const colors = getConfidenceColor(confidence);

  return (
    <div className={cn('flex flex-col items-center gap-3', className)}>
      <div 
        className={cn('relative rounded-full', colors.bg)}
        style={{ width: config.size + 16, height: config.size + 16 }}
      >
        <div 
          className="absolute inset-2"
          style={{ width: config.size, height: config.size }}
        >
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
              className="text-muted/50"
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
              className={cn('transition-all duration-700 ease-out', colors.stroke)}
              style={{
                filter: `drop-shadow(0 0 6px currentColor)`,
              }}
            />
          </svg>
          {/* Center text */}
          <div className="absolute inset-0 flex items-center justify-center">
            <span className={cn('font-bold tabular-nums', config.fontSize, colors.text)}>
              {percentage}%
            </span>
          </div>
        </div>
      </div>
      {showLabel && (
        <div className="text-center">
          <span className={cn('font-medium', config.labelSize, colors.text)}>
            {formatConfidence(confidence)}
          </span>
          <span className={cn('block text-muted-foreground', config.labelSize)}>
            Confidence
          </span>
        </div>
      )}
    </div>
  );
}
