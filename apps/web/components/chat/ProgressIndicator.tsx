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

  // Show only a subset of stages
  const visibleStages = INTAKE_STAGES.filter(
    (_, index) => index <= Math.min(currentIndex + 2, INTAKE_STAGES.length - 1)
  ).slice(-4);

  return (
    <div className={cn('flex items-center gap-0.5', className)}>
      {visibleStages.map((stage, index) => {
        const stageIndex = getStageIndex(stage.key);
        const isComplete = stageIndex < currentIndex;
        const isCurrent = stageIndex === currentIndex;

        return (
          <div key={stage.key} className="flex items-center">
            {index > 0 && (
              <div
                className={cn(
                  'h-px w-4',
                  isComplete ? 'bg-primary' : 'bg-border'
                )}
              />
            )}
            <div
              className={cn(
                'flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-medium transition-all',
                isComplete && 'bg-primary text-primary-foreground',
                isCurrent && 'bg-primary text-primary-foreground ring-2 ring-primary/20',
                !isComplete && !isCurrent && 'bg-muted text-muted-foreground'
              )}
              title={stage.label}
            >
              {isComplete ? (
                <Check className="h-2.5 w-2.5" />
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
