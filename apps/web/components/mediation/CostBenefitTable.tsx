'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CheckCircle2, Clock, AlertCircle } from 'lucide-react';
import type { ExpectationData } from '@/lib/types/mediation';

interface CostBenefitTableProps {
  expectationData: ExpectationData;
}

function formatCost(cost: number | [number, number]): string {
  if (Array.isArray(cost)) {
    return `£${formatAmount(cost[0])}–£${formatAmount(cost[1])}`;
  }
  return `£${formatAmount(cost)}`;
}

function formatAmount(amount: number): string {
  return amount.toLocaleString('en-GB', {
    maximumFractionDigits: 0,
  });
}

export function CostBenefitTable({ expectationData }: CostBenefitTableProps) {
  const { cost_benefit, tribunal_costs } = expectationData;
  const { settlement_option, tribunal_option } = cost_benefit;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Settle Now vs. Go to Tribunal</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          {/* Settle Now column */}
          <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-primary" />
              <h3 className="font-semibold text-sm">Settle Now</h3>
            </div>

            <div>
              <p className="text-xl font-bold text-primary">
                £{formatAmount(settlement_option.amount)}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">{settlement_option.description}</p>
            </div>

            <ul className="space-y-1.5 text-xs text-muted-foreground">
              <li className="flex items-start gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-primary shrink-0 mt-0.5" />
                Quick resolution
              </li>
              <li className="flex items-start gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-primary shrink-0 mt-0.5" />
                No tribunal fees
              </li>
              <li className="flex items-start gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-primary shrink-0 mt-0.5" />
                Certainty of outcome
              </li>
            </ul>
          </div>

          {/* Go to Tribunal column */}
          <div className="rounded-lg border border-muted bg-muted/30 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-muted-foreground" />
              <h3 className="font-semibold text-sm">Go to Tribunal</h3>
            </div>

            <div>
              <p className="text-xl font-bold text-muted-foreground">
                {formatCost(tribunal_option.cost_to_party)} costs
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">{tribunal_option.timeline}</p>
            </div>

            <ul className="space-y-1.5 text-xs text-muted-foreground">
              <li className="flex items-start gap-1.5">
                <AlertCircle className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
                {`${tribunal_costs.timeline_months_min}–${tribunal_costs.timeline_months_max} months to resolve`}
              </li>
              <li className="flex items-start gap-1.5">
                <AlertCircle className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
                Landlord costs: £{formatAmount(tribunal_costs.landlord_costs_min)}–£{formatAmount(tribunal_costs.landlord_costs_max)}
              </li>
              <li className="flex items-start gap-1.5">
                <AlertCircle className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
                {tribunal_option.outcome_uncertainty}
              </li>
            </ul>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
