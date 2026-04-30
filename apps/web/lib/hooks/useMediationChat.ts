'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { mediationApi } from '@/lib/api/mediation';
import { useAutoScroll } from './useAutoScroll';
import type {
  MediationMessage,
  StructuredOffer,
} from '@/lib/types/mediation';

interface UseMediationChatState {
  messages: MediationMessage[];
  offers: StructuredOffer[];
  isLoading: boolean;
  error: string | null;
  lastUpdated: string | null;
}

export function useMediationChat(
  disputeId: string,
  sessionId: string,
  currentRole?: string
) {
  const [state, setState] = useState<UseMediationChatState>({
    messages: [],
    offers: [],
    isLoading: false,
    error: null,
    lastUpdated: null,
  });

  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const messagesContainerRef = useAutoScroll<HTMLDivElement>([
    state.messages,
  ]);

  const fetchSession = useCallback(async () => {
    try {
      const session = await mediationApi.getSession(disputeId);
      setState((prev) => ({
        ...prev,
        messages: session.messages,
        offers: session.offers,
        lastUpdated: new Date().toISOString(),
        error: null,
      }));
      return session;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Failed to fetch mediation session';
      setState((prev) => ({
        ...prev,
        error: errorMessage,
      }));
      return null;
    }
  }, [disputeId]);

  // Initialize mediation session and load messages + offers on mount.
  // startMediation is idempotent for existing sessions, so calling it here
  // covers the case where the user lands on the chat page before the
  // expectation step has explicitly started mediation. Then we read the
  // authoritative state via getSession so both messages and offers arrive
  // together (message-only fetches lose offers on page reload).
  useEffect(() => {
    if (!disputeId || !sessionId) return;

    let cancelled = false;
    setState((prev) => ({ ...prev, isLoading: true }));

    // startMediation is idempotent for existing sessions; calling it here
    // covers the case where the user lands on chat before /expectation
    // explicitly starts mediation. Then read authoritative state via
    // getSession so messages and offers arrive together.
    mediationApi
      .startMediation(disputeId, sessionId)
      .catch(() => {
        // Session may already exist or prediction missing — continue to load anyway
      })
      .then(() => mediationApi.getSession(disputeId))
      .then((session) => {
        if (cancelled || !session) return;
        setState((prev) => ({
          ...prev,
          messages: session.messages ?? [],
          offers: session.offers ?? [],
          isLoading: false,
          lastUpdated: new Date().toISOString(),
          error: null,
        }));
      })
      .catch((error) => {
        if (cancelled) return;
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to load session';
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error: errorMessage,
        }));
      });

    return () => {
      cancelled = true;
    };
  }, [disputeId, sessionId]);

  // Polling for new messages/offers every 10 seconds
  useEffect(() => {
    if (!disputeId || !sessionId) return;

    pollingIntervalRef.current = setInterval(() => {
      fetchSession();
    }, 10000);

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, [disputeId, sessionId, fetchSession]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!disputeId || !sessionId || !content.trim()) return;
      if (!currentRole) {
        setState((prev) => ({
          ...prev,
          error: 'Cannot send message without a known role.',
        }));
        return null;
      }

      const optimisticId = `optimistic-${Date.now()}`;
      const optimisticMessage: MediationMessage = {
        id: optimisticId,
        sender_role: currentRole,
        content,
        message_type: 'text',
        timestamp: new Date().toISOString(),
      };

      setState((prev) => ({
        ...prev,
        messages: [...prev.messages, optimisticMessage],
        error: null,
      }));

      try {
        const response = await mediationApi.sendMessage(
          disputeId,
          sessionId,
          content
        );

        setState((prev) => ({
          ...prev,
          messages: [
            ...prev.messages.filter((m) => m.id !== optimisticId),
            response.user_message,
            response.ai_response,
          ],
          lastUpdated: new Date().toISOString(),
          error: null,
        }));

        return response;
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to send message';
        setState((prev) => ({
          ...prev,
          messages: prev.messages.filter((m) => m.id !== optimisticId),
          error: errorMessage,
        }));
        return null;
      }
    },
    [disputeId, sessionId, currentRole]
  );

  const submitOffer = useCallback(
    async (amount: number) => {
      if (!disputeId || !sessionId) return;
      if (!currentRole) {
        setState((prev) => ({
          ...prev,
          error: 'Cannot submit offer without a known role.',
        }));
        return null;
      }

      const stamp = Date.now();
      const optimisticOfferId = `optimistic-offer-${stamp}`;
      const optimisticMessageId = `optimistic-msg-${stamp}`;
      const role = currentRole;
      const optimisticOffer: StructuredOffer = {
        id: optimisticOfferId,
        amount,
        proposed_by_role: role,
        status: 'pending',
        proposed_at: new Date().toISOString(),
      };
      const optimisticMessage: MediationMessage = {
        id: optimisticMessageId,
        sender_role: role,
        content: `Offered £${amount.toFixed(2)}`,
        message_type: 'offer',
        timestamp: new Date().toISOString(),
        offer_id: optimisticOfferId,
      };

      setState((prev) => ({
        ...prev,
        offers: [...prev.offers, optimisticOffer],
        messages: [...prev.messages, optimisticMessage],
        error: null,
      }));

      try {
        const offer = await mediationApi.submitOffer(
          disputeId,
          sessionId,
          amount
        );

        setState((prev) => ({
          ...prev,
          offers: [
            ...prev.offers.filter((o) => o.id !== optimisticOfferId),
            offer,
          ],
          messages: prev.messages.map((m) =>
            m.id === optimisticMessageId ? { ...m, offer_id: offer.id } : m
          ),
          lastUpdated: new Date().toISOString(),
          error: null,
        }));

        // Pull authoritative messages and offers so the optimistic placeholders
        // are replaced by the real server records. Failures here must NOT
        // revert the offer that already succeeded — keep the confirmed state.
        try {
          const fresh = await mediationApi.getSession(disputeId);
          setState((prev) => ({
            ...prev,
            messages: fresh.messages ?? [],
            offers: fresh.offers ?? [],
            lastUpdated: new Date().toISOString(),
          }));
        } catch {
          // Reconciliation failed; the next poll will catch up.
        }

        return offer;
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to submit offer';
        setState((prev) => ({
          ...prev,
          offers: prev.offers.filter((o) => o.id !== optimisticOfferId),
          messages: prev.messages.filter((m) => m.id !== optimisticMessageId),
          error: errorMessage,
        }));
        return null;
      }
    },
    [disputeId, sessionId, currentRole]
  );

  const respondToOffer = useCallback(
    async (
      offerId: string,
      action: 'accept' | 'reject' | 'counter',
      counterAmount?: number
    ) => {
      if (!disputeId || !sessionId) return;

      try {
        const response = await mediationApi.respondToOffer(
          disputeId,
          sessionId,
          offerId,
          action,
          counterAmount
        );

        setState((prev) => ({
          ...prev,
          offers: response.new_offer
            ? [
                ...prev.offers.map((o) =>
                  o.id === offerId ? response.offer : o
                ),
                response.new_offer,
              ]
            : prev.offers.map((o) => (o.id === offerId ? response.offer : o)),
          messages: [...prev.messages, ...response.messages],
          lastUpdated: new Date().toISOString(),
          error: null,
        }));

        return response;
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to respond to offer';
        setState((prev) => ({
          ...prev,
          error: errorMessage,
        }));
        return null;
      }
    },
    [disputeId, sessionId]
  );

  const refresh = useCallback(() => {
    return fetchSession();
  }, [fetchSession]);

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  return {
    ...state,
    messagesContainerRef,
    sendMessage,
    submitOffer,
    respondToOffer,
    refresh,
    clearError,
  };
}
