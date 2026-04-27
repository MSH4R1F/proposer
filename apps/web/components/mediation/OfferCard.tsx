'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { CheckCircle, XCircle, RefreshCw, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { StructuredOffer } from '@/lib/types/mediation';

interface OfferCardProps {
  offer: StructuredOffer;
  currentRole: string;
  onRespond: (
    offerId: string,
    action: 'accept' | 'reject' | 'counter',
    counterAmount?: number
  ) => void;
}

const STATUS_STYLES: Record<string, string> = {
  pending: 'text-yellow-700 bg-yellow-100 border-yellow-300',
  accepted: 'text-green-700 bg-green-100 border-green-300',
  rejected: 'text-red-700 bg-red-100 border-red-300',
  countered: 'text-blue-700 bg-blue-100 border-blue-300',
  expired: 'text-gray-600 bg-gray-100 border-gray-300',
};

export function OfferCard({ offer, currentRole, onRespond }: OfferCardProps) {
  const [showCounter, setShowCounter] = useState(false);
  const [counterAmount, setCounterAmount] = useState('');
  const [isResponding, setIsResponding] = useState(false);

  const canRespond =
    currentRole !== offer.proposed_by_role && offer.status === 'pending';

  const handleRespond = async (action: 'accept' | 'reject' | 'counter') => {
    setIsResponding(true);
    try {
      if (action === 'counter') {
        const amount = parseFloat(counterAmount);
        if (!isNaN(amount) && amount > 0) {
          onRespond(offer.id, action, amount);
          setShowCounter(false);
          setCounterAmount('');
        }
      } else {
        onRespond(offer.id, action);
      }
    } finally {
      setIsResponding(false);
    }
  };

  const statusLabel =
    offer.status.charAt(0).toUpperCase() + offer.status.slice(1);

  return (
    <Card className="border-2 border-dashed border-muted-foreground/20">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold">
            Settlement Offer
          </CardTitle>
          <span
            className={cn(
              'text-xs px-2 py-0.5 rounded-full border font-medium',
              STATUS_STYLES[offer.status] ?? STATUS_STYLES.expired
            )}
          >
            {statusLabel}
          </span>
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-4 space-y-3">
        <div>
          <p className="text-2xl font-bold">£{offer.amount.toFixed(2)}</p>
          <p className="text-xs text-muted-foreground capitalize">
            Proposed by {offer.proposed_by_role}
          </p>
          {offer.counter_amount != null && (
            <p className="text-sm text-muted-foreground mt-1">
              Counter:{' '}
              <span className="font-medium">
                £{offer.counter_amount.toFixed(2)}
              </span>
            </p>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            {new Date(offer.proposed_at).toLocaleString()}
          </p>
        </div>

        {canRespond && (
          <div className="space-y-2">
            {!showCounter && (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => handleRespond('accept')}
                  disabled={isResponding}
                  className="gap-1.5 flex-1"
                >
                  {isResponding ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <CheckCircle className="h-3 w-3" />
                  )}
                  Accept
                </Button>

                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowCounter(true)}
                  disabled={isResponding}
                  className="gap-1.5 flex-1"
                >
                  <RefreshCw className="h-3 w-3" />
                  Counter
                </Button>

                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => handleRespond('reject')}
                  disabled={isResponding}
                  className="gap-1.5 flex-1"
                >
                  <XCircle className="h-3 w-3" />
                  Reject
                </Button>
              </div>
            )}

            {showCounter && (
              <div className="flex gap-2 items-center">
                <div className="relative flex-1">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground pointer-events-none">
                    £
                  </span>
                  <Input
                    type="number"
                    value={counterAmount}
                    onChange={(e) => setCounterAmount(e.target.value)}
                    placeholder="Counter amount"
                    className="pl-7"
                    min={0}
                    step={0.01}
                    disabled={isResponding}
                  />
                </div>
                <Button
                  size="sm"
                  onClick={() => handleRespond('counter')}
                  disabled={isResponding || !counterAmount}
                >
                  {isResponding ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    'Submit'
                  )}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setShowCounter(false);
                    setCounterAmount('');
                  }}
                  disabled={isResponding}
                >
                  Cancel
                </Button>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
