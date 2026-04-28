'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { mediationApi } from '@/lib/api/mediation';
import { ROUTES } from '@/lib/constants/routes';
import { Handshake, MessageSquare, Loader2 } from 'lucide-react';

interface AcceptancePromptProps {
  disputeId: string;
  sessionId: string;
  role: string;
}

export function AcceptancePrompt({ disputeId, sessionId, role }: AcceptancePromptProps) {
  const router = useRouter();
  const [isSettling, setIsSettling] = useState(false);
  const [settleError, setSettleError] = useState<string | null>(null);

  const handleAcceptAndSettle = async () => {
    setIsSettling(true);
    setSettleError(null);
    try {
      await mediationApi.startMediation(disputeId, sessionId);
      router.push(ROUTES.MEDIATION_SETTLEMENT(disputeId));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to start mediation';
      setSettleError(message);
      setIsSettling(false);
    }
  };

  const handleNegotiate = () => {
    router.push(ROUTES.MEDIATION_CHAT(disputeId) + '?session=' + sessionId + '&role=' + role);
  };

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="text-center space-y-4">
          <div>
            <h3 className="font-semibold text-base">How would you like to proceed?</h3>
            <p className="text-sm text-muted-foreground mt-1">
              Choose to settle at the predicted amount or negotiate directly with the other party.
            </p>
          </div>

          {settleError && (
            <p className="text-sm text-destructive">{settleError}</p>
          )}

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Button
              onClick={handleAcceptAndSettle}
              disabled={isSettling}
              className="gap-2"
            >
              {isSettling ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Handshake className="h-4 w-4" />
              )}
              Accept & Settle
            </Button>

            <Button
              variant="outline"
              onClick={handleNegotiate}
              disabled={isSettling}
              className="gap-2"
            >
              <MessageSquare className="h-4 w-4" />
              Negotiate
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
