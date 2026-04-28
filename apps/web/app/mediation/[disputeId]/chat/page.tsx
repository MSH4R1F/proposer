'use client';

import { use, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useMediationChat } from '@/lib/hooks/useMediationChat';
import { MediationChat } from '@/components/mediation/MediationChat';
import { Loader2, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ChatPageProps {
  params: Promise<{ disputeId: string }>;
}

function ChatContent({ disputeId }: { disputeId: string }) {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get('session') || '';
  const currentRole = searchParams.get('role') || '';

  const {
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
  } = useMediationChat(disputeId, sessionId, currentRole);

  if (isLoading && messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground">Loading mediation chat...</p>
      </div>
    );
  }

  if (error && messages.length === 0) {
    return (
      <div className="max-w-xl mx-auto py-12">
        <div className="flex items-start gap-3 p-4 rounded-xl bg-destructive/10 border border-destructive/20">
          <AlertTriangle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium text-destructive">
              Failed to load mediation chat
            </p>
            <p className="text-sm text-muted-foreground mt-1">{error}</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={refresh}>
              Retry
            </Button>
            <Button variant="ghost" size="sm" onClick={clearError}>
              Dismiss
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto h-[calc(100vh-12rem)]">
      <MediationChat
        disputeId={disputeId}
        sessionId={sessionId}
        messages={messages}
        offers={offers}
        isLoading={isLoading}
        error={error}
        lastUpdated={lastUpdated}
        messagesContainerRef={messagesContainerRef}
        sendMessage={sendMessage}
        submitOffer={submitOffer}
        respondToOffer={respondToOffer}
        refresh={refresh}
        clearError={clearError}
        currentRole={currentRole}
      />
    </div>
  );
}

export default function ChatPage({ params }: ChatPageProps) {
  const { disputeId } = use(params);

  return (
    <Suspense
      fallback={
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
          <p className="text-muted-foreground">Loading...</p>
        </div>
      }
    >
      <ChatContent disputeId={disputeId} />
    </Suspense>
  );
}
