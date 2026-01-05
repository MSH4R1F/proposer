import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { IssuePredictionCard } from './IssuePredictionCard';
import { ListChecks } from 'lucide-react';
import type { IssuePrediction } from '@/lib/types/prediction';

interface IssuePredictionListProps {
  predictions: IssuePrediction[];
}

export function IssuePredictionList({ predictions }: IssuePredictionListProps) {
  if (!predictions || predictions.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-lg">
          <ListChecks className="h-5 w-5" />
          Issue Breakdown ({predictions.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {predictions.map((prediction, index) => (
          <IssuePredictionCard
            key={`${prediction.issue_type}-${index}`}
            prediction={prediction}
          />
        ))}
      </CardContent>
    </Card>
  );
}
