import { cn } from '@/lib/utils';
import { formatOutcome } from '@/lib/utils/formatters';
import { TrendingUp, TrendingDown, Scale, HelpCircle } from 'lucide-react';
import type { OutcomeType } from '@/lib/types/prediction';

interface OutcomeDisplayProps {
  outcome: OutcomeType;
  confidence: number;
  className?: string;
}

const outcomeConfig = {
  tenant_win: {
    icon: TrendingUp,
    bgColor: 'bg-green-50 dark:bg-green-950',
    textColor: 'text-green-700 dark:text-green-300',
    borderColor: 'border-green-200 dark:border-green-800',
  },
  landlord_win: {
    icon: TrendingDown,
    bgColor: 'bg-red-50 dark:bg-red-950',
    textColor: 'text-red-700 dark:text-red-300',
    borderColor: 'border-red-200 dark:border-red-800',
  },
  split: {
    icon: Scale,
    bgColor: 'bg-yellow-50 dark:bg-yellow-950',
    textColor: 'text-yellow-700 dark:text-yellow-300',
    borderColor: 'border-yellow-200 dark:border-yellow-800',
  },
  uncertain: {
    icon: HelpCircle,
    bgColor: 'bg-gray-50 dark:bg-gray-900',
    textColor: 'text-gray-700 dark:text-gray-300',
    borderColor: 'border-gray-200 dark:border-gray-800',
  },
};

export function OutcomeDisplay({
  outcome,
  confidence,
  className,
}: OutcomeDisplayProps) {
  const config = outcomeConfig[outcome];
  const Icon = config.icon;
  const percentage = Math.round(confidence * 100);

  return (
    <div
      className={cn(
        'rounded-lg border p-6',
        config.bgColor,
        config.borderColor,
        className
      )}
    >
      <div className="flex items-center gap-4">
        <div
          className={cn(
            'flex h-14 w-14 items-center justify-center rounded-full',
            config.bgColor,
            'border-2',
            config.borderColor
          )}
        >
          <Icon className={cn('h-7 w-7', config.textColor)} />
        </div>
        <div className="flex-1">
          <h2 className={cn('text-xl font-bold', config.textColor)}>
            {formatOutcome(outcome)}
          </h2>
          <p className="text-sm text-muted-foreground">
            {percentage}% confidence based on similar cases
          </p>
        </div>
      </div>
    </div>
  );
}
