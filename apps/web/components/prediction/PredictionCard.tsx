'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { OutcomeDisplay } from './OutcomeDisplay';
import { SettlementRange } from './SettlementRange';
import { StrengthsWeaknesses } from './StrengthsWeaknesses';
import { IssuePredictionList } from './IssuePredictionList';
import { ReasoningTrace } from './ReasoningTrace';
import { LegalDisclaimer } from './LegalDisclaimer';
import { Badge } from '@/components/ui/badge';
import { FileText, Calendar, Hash, Scale } from 'lucide-react';
import type { PredictionResult } from '@/lib/types/prediction';

interface PredictionCardProps {
  prediction: PredictionResult;
}

export function PredictionCard({ prediction }: PredictionCardProps) {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-xl bg-primary/10">
              <Scale className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
                Prediction Results
              </h1>
              {prediction.timestamp && (
                <div className="flex items-center gap-2 mt-1 text-sm text-muted-foreground">
                  <Calendar className="h-3.5 w-3.5" />
                  <span>Generated {new Date(prediction.timestamp).toLocaleDateString('en-GB', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                  })}</span>
                </div>
              )}
            </div>
          </div>
          <Badge 
            variant="outline" 
            className="self-start sm:self-center sm:ml-auto font-mono text-xs"
          >
            <Hash className="h-3 w-3 mr-1" />
            {prediction.prediction_id.slice(0, 8)}
          </Badge>
        </div>
      </div>

      {/* Legal Disclaimer - Prominent at top */}
      <LegalDisclaimer disclaimer={prediction.disclaimer} />

      {/* Overall Outcome */}
      <OutcomeDisplay
        outcome={prediction.overall_outcome}
        confidence={prediction.overall_confidence}
      />

      {/* Summary */}
      {prediction.outcome_summary && (
        <Card className="border-0 shadow-soft">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-3 text-lg">
              <div className="p-2 rounded-lg bg-blue-500/10">
                <FileText className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              </div>
              Summary
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground leading-relaxed">
              {prediction.outcome_summary}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Financial Summary */}
      <SettlementRange
        range={prediction.predicted_settlement_range}
        tenantRecovery={prediction.tenant_recovery_amount}
        landlordRecovery={prediction.landlord_recovery_amount}
        depositAtStake={prediction.deposit_at_stake}
      />

      {/* Strengths & Weaknesses */}
      <StrengthsWeaknesses
        strengths={prediction.key_strengths}
        weaknesses={prediction.key_weaknesses}
        uncertainties={prediction.uncertainties}
      />

      <Separator className="my-8" />

      {/* Per-Issue Breakdown */}
      {prediction.issue_predictions && prediction.issue_predictions.length > 0 && (
        <IssuePredictionList predictions={prediction.issue_predictions} />
      )}

      {/* Reasoning Trace */}
      {prediction.reasoning_trace && prediction.reasoning_trace.length > 0 && (
        <ReasoningTrace
          steps={prediction.reasoning_trace}
          totalCases={prediction.total_cases_analyzed}
        />
      )}

      {/* Retrieved Cases */}
      {prediction.retrieved_cases && prediction.retrieved_cases.length > 0 && (
        <Card className="border-0 shadow-soft">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Cases Referenced</CardTitle>
            <p className="text-sm text-muted-foreground">
              These tribunal decisions informed our prediction
            </p>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {prediction.retrieved_cases.map((caseRef, index) => (
                <Badge 
                  key={index} 
                  variant="secondary"
                  className="font-mono text-xs bg-muted/50"
                >
                  {caseRef}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
