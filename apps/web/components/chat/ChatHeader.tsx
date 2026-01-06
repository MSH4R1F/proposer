'use client';

import { Badge } from '@/components/ui/badge';
import { ProgressIndicator } from './ProgressIndicator';
import { getStageLabel } from '@/lib/constants/stages';
import type { IntakeStage } from '@/lib/types/chat';

interface ChatHeaderProps {
  stage: IntakeStage;
  completeness: number;
  sessionId?: string | null;
}

export function ChatHeader({ stage, completeness, sessionId }: ChatHeaderProps) {
  const percentage = Math.round(completeness * 100);
  
  return (
    <div className="shrink-0 border-b border-border/40 bg-background/50 backdrop-blur-sm">
      {/* Progress bar - full width, minimal */}
      <div className="h-1 bg-muted">
        <div
          className="h-full bg-primary transition-all duration-500 ease-out"
          style={{ width: `${percentage}%` }}
        />
      </div>
      
      {/* Stage info */}
      <div className="flex items-center justify-between px-4 py-2 max-w-3xl mx-auto">
        <div className="flex items-center gap-3">
          <Badge 
            variant="secondary" 
            className="text-xs font-medium px-2.5 py-0.5 bg-primary/10 text-primary border-0"
          >
            {getStageLabel(stage)}
          </Badge>
          <span className="text-xs text-muted-foreground tabular-nums">
            {percentage}% complete
          </span>
        </div>
        
        <ProgressIndicator currentStage={stage} className="hidden sm:flex" />
      </div>
    </div>
  );
}
