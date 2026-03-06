'use client';

import type { RefObject } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { AlertTriangle, CheckCircle2, Scale } from 'lucide-react';
import { MediationHeader } from './MediationHeader';
import { MediationMessageBubble } from './MediationMessageBubble';
import { OfferCard } from './OfferCard';
import { MediationInput } from './MediationInput';
import { ROUTES } from '@/lib/constants/routes';
import type { MediationMessage, StructuredOffer } from '@/lib/types/mediation';

interface MediationChatProps {
  disputeId: string;
  sessionId: string;
  messages: MediationMessage[];
  offers: StructuredOffer[];
  isLoading: boolean;
  error: string | null;
  lastUpdated: string | null;
  messagesContainerRef: RefObject<HTMLDivElement | null>;
  sendMessage: (content: string) => void;
  submitOffer: (amount: number) => void;
  respondToOffer: (
    offerId: string,
    action: 'accept' | 'reject' | 'counter',
    counterAmount?: number
  ) => void;
  refresh: () => void;
  clearError: () => void;
  currentRole?: string;
}

export function MediationChat({
  disputeId,
  sessionId,
  messages,
  offers,
  isLoading,
  error,
  lastUpdated,
  messagesContainerRef,
  sendMessage,
  submitOffer,
  respondToOffer,
  refresh,
  clearError,
  currentRole = '',
}: MediationChatProps) {
  const isSettled = offers.some((o) => o.status === 'accepted');
  const isEscalated =
    !isSettled &&
    messages.some(
      (m) =>
        m.message_type === 'system' &&
        m.content.toLowerCase().includes('escalat')
    );

  const getOfferById = (offerId: string) =>
    offers.find((o) => o.id === offerId);

  return (
    <div className="flex flex-col h-full border rounded-xl overflow-hidden bg-background">
      {/* Header */}
      <MediationHeader
        disputeId={disputeId}
        lastUpdated={lastUpdated}
        onRefresh={refresh}
      />

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2 mx-4 mt-3 p-3 rounded-lg bg-destructive/10 border border-destructive/20 shrink-0">
          <AlertTriangle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
          <p className="text-sm text-destructive flex-1">{error}</p>
          <button
            onClick={clearError}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Settlement banner */}
      {isSettled && (
        <div className="mx-4 mt-3 p-3 rounded-lg bg-green-50 border border-green-200 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <p className="text-sm font-medium text-green-700">
              Settlement reached!
            </p>
          </div>
          <Button
            asChild
            size="sm"
            className="bg-green-600 hover:bg-green-700 text-white"
          >
            <Link href={ROUTES.MEDIATION_SETTLEMENT(disputeId)}>
              View Settlement
            </Link>
          </Button>
        </div>
      )}

      {/* Escalation banner */}
      {isEscalated && (
        <div className="mx-4 mt-3 p-3 rounded-lg bg-amber-50 border border-amber-200 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <Scale className="h-4 w-4 text-amber-600" />
            <p className="text-sm font-medium text-amber-700">
              Case escalated to tribunal
            </p>
          </div>
          <Button
            asChild
            size="sm"
            variant="outline"
            className="border-amber-300 text-amber-700 hover:bg-amber-50"
          >
            <Link href={ROUTES.MEDIATION_ESCALATION(disputeId)}>
              View Options
            </Link>
          </Button>
        </div>
      )}

      {/* Messages */}
      <div
        ref={messagesContainerRef}
        className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0"
      >
        {messages.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center h-full text-center py-12">
            <Scale className="h-8 w-8 text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">
              No messages yet. Start the conversation below.
            </p>
          </div>
        )}

        {messages.map((message) => {
          const linkedOffer = message.offer_id
            ? getOfferById(message.offer_id)
            : undefined;

          return (
            <div key={message.id} className="space-y-2">
              <MediationMessageBubble
                message={message}
                currentSessionId={sessionId}
              />
              {linkedOffer && (
                <OfferCard
                  offer={linkedOffer}
                  currentRole={currentRole}
                  onRespond={respondToOffer}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Input */}
      <MediationInput
        onSendMessage={sendMessage}
        onSubmitOffer={submitOffer}
        isLoading={isLoading}
      />
    </div>
  );
}
