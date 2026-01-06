'use client';

import { cn } from '@/lib/utils';
import { CheckCircle2, Circle } from 'lucide-react';

interface CompletenessBarProps {
  completeness: number;
  className?: string;
}

export function CompletenessBar({ completeness, className }: CompletenessBarProps) {
  const percentage = Math.round(completeness * 100);
  const isComplete = percentage >= 100;

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
          {isComplete ? (
            <CheckCircle2 className="h-4 w-4 text-success" />
          ) : (
            <Circle className="h-4 w-4 text-muted-foreground" />
          )}
          <span className="font-medium text-muted-foreground">
            {isComplete ? 'All information collected' : 'Information gathering'}
          </span>
        </div>
        <span className={cn(
          'font-semibold tabular-nums',
          isComplete ? 'text-success' : 'text-primary'
        )}>
          {percentage}%
        </span>
      </div>
      
      <div className="relative h-2 rounded-full bg-muted overflow-hidden">
        {/* Animated gradient background for incomplete state */}
        {!isComplete && (
          <div className="absolute inset-0 bg-gradient-to-r from-primary/20 via-primary/10 to-primary/20 animate-shimmer" 
               style={{ backgroundSize: '200% 100%' }} />
        )}
        
        {/* Progress bar */}
        <div
          className={cn(
            'h-full rounded-full transition-all duration-500 ease-out',
            isComplete 
              ? 'bg-gradient-to-r from-success to-emerald-400' 
              : 'bg-gradient-to-r from-primary to-primary/80'
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
