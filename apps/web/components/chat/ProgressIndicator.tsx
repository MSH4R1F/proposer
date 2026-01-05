'use client';

import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { INTAKE_STAGES, getStageIndex } from '@/lib/constants/stages';
import type { IntakeStage } from '@/lib/types/chat';

interface ProgressIndicatorProps {
  currentStage: IntakeStage;
  className?: string;
}

export function ProgressIndicator({
  currentStage,
  className,
}: ProgressIndicatorProps) {
  const currentIndex = getStageIndex(currentStage);

  // Show only a subset of stages for mobile
  const visibleStages = INTAKE_STAGES.filter(
    (_, index) => index <= Math.min(currentIndex + 2, INTAKE_STAGES.length - 1)
  ).slice(-5);

  return (
    <div className={cn('flex items-center gap-1', className)}>
      {visibleStages.map((stage, index) => {
        const stageIndex = getStageIndex(stage.key);
        const isComplete = stageIndex < currentIndex;
        const isCurrent = stageIndex === currentIndex;

        return (
          <div key={stage.key} className="flex items-center">
            {index > 0 && (
              <div
                className={cn(
                  'h-0.5 w-4 sm:w-8',
                  isComplete ? 'bg-primary' : 'bg-muted'
                )}
              />
            )}
            <div
              className={cn(
                'flex h-6 w-6 sm:h-8 sm:w-8 items-center justify-center rounded-full text-xs font-medium transition-colors',
                isComplete && 'bg-primary text-primary-foreground',
                isCurrent && 'bg-primary text-primary-foreground ring-2 ring-primary/30',
                !isComplete && !isCurrent && 'bg-muted text-muted-foreground'
              )}
              title={stage.label}
            >
              {isComplete ? (
                <Check className="h-3 w-3 sm:h-4 sm:w-4" />
              ) : (
                stage.step
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
