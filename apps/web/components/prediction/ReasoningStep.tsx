import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { CitationCard } from './CitationCard';
import type { ReasoningStep as ReasoningStepType } from '@/lib/types/prediction';

interface ReasoningStepProps {
  step: ReasoningStepType;
  className?: string;
}

const categoryLabels: Record<string, string> = {
  issue_analysis: 'Issue Analysis',
  evidence_review: 'Evidence Review',
  precedent_comparison: 'Precedent Comparison',
  legal_principle: 'Legal Principle',
  conclusion: 'Conclusion',
  uncertainty: 'Uncertainty',
};

export function ReasoningStep({ step, className }: ReasoningStepProps) {
  const categoryLabel = categoryLabels[step.category] || step.category;
  const confidencePercentage = Math.round(step.confidence * 100);

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-medium text-primary-foreground">
            {step.step_number}
          </span>
          <h4 className="font-medium">{step.title}</h4>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {categoryLabel}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {confidencePercentage}%
          </span>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">{step.content}</p>

      {step.citations && step.citations.length > 0 && (
        <div className="space-y-2 pt-2">
          <h5 className="text-xs font-medium text-muted-foreground">
            Supporting Cases ({step.citations.length})
          </h5>
          <div className="space-y-2">
            {step.citations.map((citation, index) => (
              <CitationCard
                key={`${citation.case_reference}-${index}`}
                citation={citation}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
