import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatIssueType, formatOutcome, formatCurrency } from '@/lib/utils/formatters';
import { ConfidenceGauge } from './ConfidenceGauge';
import { CitationCard } from './CitationCard';
import type { IssuePrediction } from '@/lib/types/prediction';

interface IssuePredictionCardProps {
  prediction: IssuePrediction;
  className?: string;
}

const outcomeColors = {
  tenant_favored: 'border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950',
  landlord_favored: 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950',
  split: 'border-yellow-200 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-950',
  uncertain: 'border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-950',
};

export function IssuePredictionCard({
  prediction,
  className,
}: IssuePredictionCardProps) {
  return (
    <Card className={cn(outcomeColors[prediction.predicted_outcome], className)}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <CardTitle className="text-lg">
              {formatIssueType(prediction.issue_type)}
            </CardTitle>
            {prediction.issue_description && (
              <p className="text-sm text-muted-foreground">
                {prediction.issue_description}
              </p>
            )}
          </div>
          <ConfidenceGauge confidence={prediction.confidence} size="sm" showLabel={false} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <Badge
            variant={
              prediction.predicted_outcome === 'tenant_favored'
                ? 'success'
                : prediction.predicted_outcome === 'landlord_favored'
                ? 'destructive'
                : 'secondary'
            }
          >
            {formatOutcome(prediction.predicted_outcome)}
          </Badge>
          {prediction.predicted_amount !== undefined && (
            <span className="text-sm font-medium">
              {formatCurrency(prediction.predicted_amount)}
            </span>
          )}
        </div>

        <p className="text-sm text-muted-foreground">{prediction.reasoning}</p>

        {prediction.key_factors && prediction.key_factors.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs font-medium text-muted-foreground">Key Factors</h4>
            <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
              {prediction.key_factors.map((factor, index) => (
                <li key={index}>{factor}</li>
              ))}
            </ul>
          </div>
        )}

        {prediction.supporting_cases && prediction.supporting_cases.length > 0 && (
          <div className="space-y-2 pt-2">
            <h4 className="text-xs font-medium text-muted-foreground">
              Supporting Cases
            </h4>
            <div className="space-y-2">
              {prediction.supporting_cases.slice(0, 2).map((citation, index) => (
                <CitationCard
                  key={`${citation.case_reference}-${index}`}
                  citation={citation}
                />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
