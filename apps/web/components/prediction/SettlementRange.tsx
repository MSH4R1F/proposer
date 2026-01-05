import { formatCurrency, formatSettlementRange } from '@/lib/utils/formatters';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Banknote } from 'lucide-react';

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
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Banknote className="h-5 w-5" />
          Financial Summary
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {depositAtStake !== undefined && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Deposit at Stake</span>
            <span className="font-semibold">{formatCurrency(depositAtStake)}</span>
          </div>
        )}

        {range && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Predicted Settlement</span>
            <span className="font-semibold">{formatSettlementRange(range)}</span>
          </div>
        )}

        {tenantRecovery !== undefined && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Tenant May Recover</span>
            <span className="font-semibold text-green-600">
              {formatCurrency(tenantRecovery)}
            </span>
          </div>
        )}

        {landlordRecovery !== undefined && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Landlord May Recover</span>
            <span className="font-semibold text-red-600">
              {formatCurrency(landlordRecovery)}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
