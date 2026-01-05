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
import { FileText } from 'lucide-react';
import type { PredictionResult } from '@/lib/types/prediction';

interface PredictionCardProps {
  prediction: PredictionResult;
}

export function PredictionCard({ prediction }: PredictionCardProps) {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold">Prediction Results</h1>
          <Badge variant="outline">
            ID: {prediction.prediction_id.slice(0, 8)}
          </Badge>
        </div>
        {prediction.timestamp && (
          <p className="text-sm text-muted-foreground">
            Generated on {new Date(prediction.timestamp).toLocaleString()}
          </p>
        )}
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
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-lg">
              <FileText className="h-5 w-5" />
              Summary
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">{prediction.outcome_summary}</p>
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

      <Separator />

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
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Cases Referenced</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {prediction.retrieved_cases.map((caseRef, index) => (
                <Badge key={index} variant="secondary">
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
