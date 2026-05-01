'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { ExpectationData } from '@/lib/types/mediation';

interface ExpectationCardProps {
  expectationData: ExpectationData;
}

function formatCurrency(amount: number): string {
  return amount.toLocaleString('en-GB', {
    maximumFractionDigits: 0,
  });
}

export function ExpectationCard({ expectationData }: ExpectationCardProps) {
  const { party_role, prediction_summary, party_framing } = expectationData;
  const { overall_confidence, suggested_amount, overall_outcome } = prediction_summary;

  const isTenant = party_role === 'tenant';
  const roleFramedAmount = isTenant
    ? `You would likely recover £${formatCurrency(suggested_amount)}`
    : `You would likely pay £${formatCurrency(suggested_amount)}`;

  const confidencePct = Math.round(overall_confidence * 100);
  const isTenantFavored =
    overall_outcome === 'tenant_favored' || overall_outcome === 'tenant_win';
  const isLandlordFavored =
    overall_outcome === 'landlord_favored' || overall_outcome === 'landlord_win';

  const outcomeBadgeVariant =
    isTenantFavored
      ? 'default'
      : isLandlordFavored
        ? 'destructive'
        : 'secondary';

  const outcomeLabel =
    isTenantFavored
      ? 'Tenant Favoured'
      : isLandlordFavored
        ? 'Landlord Favoured'
        : overall_outcome === 'split'
          ? 'Split Decision'
          : 'Uncertain';

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Predicted Outcome</CardTitle>
          <Badge variant={outcomeBadgeVariant}>{outcomeLabel}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Role-framed amount */}
        <div className="p-4 rounded-lg bg-primary/5 border border-primary/10">
          <p className="text-2xl font-bold text-primary">{roleFramedAmount}</p>
          <p className="text-sm text-muted-foreground mt-1">{party_framing}</p>
        </div>

        {/* Confidence meter */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Prediction Confidence</span>
            <span className="text-sm font-semibold text-primary">{confidencePct}%</span>
          </div>
          <div className="h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${confidencePct}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Based on analysis of similar tribunal decisions
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
