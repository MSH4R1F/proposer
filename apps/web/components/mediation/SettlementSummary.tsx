'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertTriangle, CheckCircle2, Calendar } from 'lucide-react';
import type { SettlementSummary as SettlementSummaryType } from '@/lib/types/mediation';

interface SettlementSummaryProps {
  settlement: SettlementSummaryType;
}

export function SettlementSummary({ settlement }: SettlementSummaryProps) {
  const formattedDate = new Date(settlement.settled_at).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  return (
    <div className="space-y-4">
      {/* Amount card */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-green-500/10">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
            </div>
            <CardTitle className="text-lg">Settlement Agreed</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Agreed amount */}
          <div className="p-6 rounded-xl bg-primary/5 border border-primary/10 text-center">
            <p className="text-sm text-muted-foreground mb-1">Agreed Settlement Amount</p>
            <p className="text-4xl font-bold text-primary">
              £{settlement.agreed_amount.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>

          {/* Date */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Calendar className="h-4 w-4 shrink-0" />
            <span>
              Agreement reached on <span className="font-medium text-foreground">{formattedDate}</span>
            </span>
          </div>

          {/* Property info if available */}
          {settlement.property?.address && (
            <div className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Property: </span>
              {settlement.property.address}
              {settlement.property.postcode ? `, ${settlement.property.postcode}` : ''}
            </div>
          )}

          {/* Deposit amount if available */}
          {settlement.deposit_amount != null && (
            <div className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Original deposit: </span>
              £{settlement.deposit_amount.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Disclaimer card */}
      <div className="relative overflow-hidden rounded-xl p-4 bg-warning/5 border border-warning/20">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-warning/50 via-warning to-warning/50" />
        <div className="flex items-start gap-3">
          <div className="shrink-0 p-2 rounded-lg bg-warning/10">
            <AlertTriangle className="h-5 w-5 text-warning" />
          </div>
          <div>
            <h4 className="font-semibold text-sm text-warning mb-1">Important Notice</h4>
            <p className="text-sm text-muted-foreground leading-relaxed">
              This document is for informational purposes only and is{' '}
              <strong className="text-foreground">NOT a legally binding contract</strong>.
              {settlement.disclaimer ? ` ${settlement.disclaimer}` : ' Always consult a qualified legal professional for advice specific to your situation.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
