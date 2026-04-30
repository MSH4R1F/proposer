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
  partyRole: string;
  suggestedAmount: number;
}

export function AcceptancePrompt({
  disputeId,
  sessionId,
  partyRole,
  suggestedAmount,
}: AcceptancePromptProps) {
  const router = useRouter();
  const [isStarting, setIsStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const chatHref =
    ROUTES.MEDIATION_CHAT(disputeId) +
    `?session=${encodeURIComponent(sessionId)}&role=${encodeURIComponent(partyRole)}`;

  const startAndOpenChat = async () => {
    setIsStarting(true);
    setStartError(null);
    try {
      await mediationApi.startMediation(disputeId, sessionId);
      router.push(chatHref);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Failed to start mediation';
      setStartError(message);
      setIsStarting(false);
    }
  };

  const handleNegotiate = startAndOpenChat;

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="text-center space-y-4">
          <div>
            <h3 className="font-semibold text-base">How would you like to proceed?</h3>
            <p className="text-sm text-muted-foreground mt-1">
              The midpoint estimate is £{suggestedAmount.toLocaleString('en-GB')}.
              You can use it as negotiation context, but settlement requires both
              parties to agree.
            </p>
          </div>

          {startError && (
            <p className="text-sm text-destructive">{startError}</p>
          )}

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Button
              onClick={startAndOpenChat}
              disabled={isStarting}
              className="gap-2"
            >
              {isStarting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Handshake className="h-4 w-4" />
              )}
              Start Mediation
            </Button>

            <Button
              variant="outline"
              onClick={handleNegotiate}
              disabled={isStarting}
              className="gap-2"
            >
              <MessageSquare className="h-4 w-4" />
              Open Chat
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
