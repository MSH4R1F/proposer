'use client';

import { Badge } from '@/components/ui/badge';
import { ProgressIndicator } from './ProgressIndicator';
import { CompletenessBar } from './CompletenessBar';
import { getStageLabel } from '@/lib/constants/stages';
import type { IntakeStage } from '@/lib/types/chat';

interface ChatHeaderProps {
  stage: IntakeStage;
  completeness: number;
  sessionId?: string | null;
}

export function ChatHeader({ stage, completeness, sessionId }: ChatHeaderProps) {
  return (
    <div className="border-b bg-background p-4 space-y-3">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <h1 className="font-semibold text-lg">Case Intake</h1>
          <Badge variant="secondary">{getStageLabel(stage)}</Badge>
        </div>
        <ProgressIndicator currentStage={stage} className="hidden sm:flex" />
      </div>
      <CompletenessBar completeness={completeness} />
      {sessionId && (
        <p className="text-xs text-muted-foreground">
          Session: {sessionId.slice(0, 8)}...
        </p>
      )}
    </div>
  );
}
