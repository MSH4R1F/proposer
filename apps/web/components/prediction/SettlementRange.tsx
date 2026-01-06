import { formatCurrency, formatSettlementRange } from '@/lib/utils/formatters';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Banknote, TrendingUp, TrendingDown, Wallet } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SettlementRangeProps {
  range?: [number, number];
  tenantRecovery?: number;
  landlordRecovery?: number;
  depositAtStake?: number;
}

export function SettlementRange({
  range,
  tenantRecovery,
  landlordRecovery,
  depositAtStake,
}: SettlementRangeProps) {
  return (
    <Card className="border-0 shadow-soft overflow-hidden">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-3 text-lg">
          <div className="p-2 rounded-lg bg-emerald-500/10">
            <Banknote className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          Financial Summary
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {depositAtStake !== undefined && (
          <div className="flex items-center justify-between p-4 rounded-xl bg-muted/50">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-background">
                <Wallet className="h-4 w-4 text-muted-foreground" />
              </div>
              <span className="text-sm font-medium text-muted-foreground">Deposit at Stake</span>
            </div>
            <span className="text-lg font-bold tabular-nums">{formatCurrency(depositAtStake)}</span>
          </div>
        )}

        {range && (
          <div className="flex items-center justify-between p-4 rounded-xl bg-primary/5 border border-primary/10">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <TrendingUp className="h-4 w-4 text-primary" />
              </div>
              <div>
                <span className="text-sm font-medium text-muted-foreground block">Predicted Settlement</span>
                <span className="text-xs text-muted-foreground/70">Expected range</span>
              </div>
            </div>
            <span className="text-lg font-bold tabular-nums text-primary">{formatSettlementRange(range)}</span>
          </div>
        )}

        <div className="grid sm:grid-cols-2 gap-3">
          {tenantRecovery !== undefined && (
            <div className="flex items-center justify-between p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/10">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-emerald-500/10">
                  <TrendingUp className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                </div>
                <span className="text-sm font-medium text-muted-foreground">Tenant Recovery</span>
              </div>
              <span className="text-lg font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
                {formatCurrency(tenantRecovery)}
              </span>
            </div>
          )}

          {landlordRecovery !== undefined && (
            <div className="flex items-center justify-between p-4 rounded-xl bg-amber-500/5 border border-amber-500/10">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-amber-500/10">
                  <TrendingDown className="h-4 w-4 text-amber-600 dark:text-amber-400" />
                </div>
                <span className="text-sm font-medium text-muted-foreground">Landlord Recovery</span>
              </div>
              <span className="text-lg font-bold tabular-nums text-amber-600 dark:text-amber-400">
                {formatCurrency(landlordRecovery)}
              </span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
