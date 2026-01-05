'use client';

import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface CompletenessBarProps {
  completeness: number;
  className?: string;
}

export function CompletenessBar({ completeness, className }: CompletenessBarProps) {
  const percentage = Math.round(completeness * 100);

  return (
    <div className={cn('space-y-1', className)}>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Case completeness</span>
        <span>{percentage}%</span>
      </div>
      <Progress value={percentage} className="h-2" />
    </div>
  );
}
