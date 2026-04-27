'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Sparkles } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ProgressIndicator } from './ProgressIndicator';
import { getStageLabel } from '@/lib/constants/stages';
import { ROUTES } from '@/lib/constants/routes';
import type { IntakeStage } from '@/lib/types/chat';

interface ChatHeaderProps {
  stage: IntakeStage;
  completeness: number;
  sessionId?: string | null;
  caseId?: string | null;
  disputeId?: string | null;
}

export function ChatHeader({ stage, completeness, sessionId, caseId, disputeId }: ChatHeaderProps) {
  const searchParams = useSearchParams();
  const percentage = Math.round(completeness * 100);
  
  const buildPredictionUrl = () => {
    if (!caseId) return '';
    const params = new URLSearchParams();
    if (sessionId) params.set('session', sessionId);
    if (disputeId) params.set('dispute', disputeId);
    const queryString = params.toString();
    return ROUTES.PREDICTION(caseId) + (queryString ? '?' + queryString : '');
  };
  
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

        <div className="flex items-center gap-3">
          {caseId && (
            <Button asChild variant="outline" size="sm" className="gap-1.5 h-7 text-xs">
              <Link href={buildPredictionUrl()}>
                <Sparkles className="h-3 w-3" />
                View Prediction
              </Link>
            </Button>
          )}
          <ProgressIndicator currentStage={stage} className="hidden sm:flex" />
        </div>
      </div>
    </div>
  );
}
