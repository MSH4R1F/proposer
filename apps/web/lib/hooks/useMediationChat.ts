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

  // Fetch messages. Without `since`, replaces the list (initial load).
  // With `since`, merges any new messages into the existing list (polling).
  const fetchMessages = useCallback(async (since?: string) => {
    try {
      const fetched = await mediationApi.getMessages(disputeId, since);
      setState((prev) => {
        if (since === undefined) {
          return {
            ...prev,
            messages: fetched,
            lastUpdated: new Date().toISOString(),
            error: null,
          };
        }
        const existingIds = new Set(prev.messages.map((m) => m.id));
        const additions = fetched.filter((m) => !existingIds.has(m.id));
        if (additions.length === 0) {
          return { ...prev, error: null };
        }
        return {
          ...prev,
          messages: [...prev.messages, ...additions],
          lastUpdated: new Date().toISOString(),
          error: null,
        };
      });
      return fetched;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Failed to fetch messages';
      setState((prev) => ({
        ...prev,
        error: errorMessage,
      }));
      return null;
    }
  }, [disputeId]);

  // Initialize messages and offers on mount via the session endpoint so that
  // both arrays are authoritative — message-only fetches lose the offers list
  // on page reload.
  useEffect(() => {
    if (!disputeId || !sessionId) return;

    let cancelled = false;
    setState((prev) => ({ ...prev, isLoading: true }));

    mediationApi
      .getSession(disputeId)
      .then((session) => {
        if (cancelled) return;
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

  // Polling for new messages every 10 seconds
  useEffect(() => {
    if (!disputeId || !sessionId) return;

    pollingIntervalRef.current = setInterval(() => {
      const lastMessageTime = state.messages[state.messages.length - 1]?.timestamp;
      fetchMessages(lastMessageTime);
    }, 10000);

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, [disputeId, sessionId, state.messages, fetchMessages]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!disputeId || !sessionId || !content.trim()) return;

      const optimisticId = `optimistic-${Date.now()}`;
      const optimisticMessage: MediationMessage = {
        id: optimisticId,
        sender_role: currentRole || 'tenant',
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

      const stamp = Date.now();
      const optimisticOfferId = `optimistic-offer-${stamp}`;
      const optimisticMessageId = `optimistic-msg-${stamp}`;
      const role = currentRole || 'tenant';
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
        // are replaced by the real server records (which carry the real ids and
        // any AI follow-up).
        const fresh = await mediationApi.getSession(disputeId);
        setState((prev) => ({
          ...prev,
          messages: fresh.messages ?? [],
          offers: fresh.offers ?? [],
          lastUpdated: new Date().toISOString(),
        }));

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
          offers: prev.offers.map((o) =>
            o.id === offerId ? response.offer : o
          ),
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
    return fetchMessages();
  }, [fetchMessages]);

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
