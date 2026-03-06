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

export function useMediationChat(disputeId: string, sessionId: string) {
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

  // Fetch initial messages on mount
  const fetchMessages = useCallback(async (since?: string) => {
    try {
      const messages = await mediationApi.getMessages(disputeId, since);
      setState((prev) => ({
        ...prev,
        messages,
        lastUpdated: new Date().toISOString(),
        error: null,
      }));
      return messages;
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

  // Initialize messages on mount
  useEffect(() => {
    if (disputeId && sessionId) {
      setState((prev) => ({ ...prev, isLoading: true }));
      fetchMessages().then(() => {
        setState((prev) => ({ ...prev, isLoading: false }));
      });
    }
  }, [disputeId, sessionId, fetchMessages]);

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

      try {
        const response = await mediationApi.sendMessage(
          disputeId,
          sessionId,
          content
        );

        setState((prev) => ({
          ...prev,
          messages: [...prev.messages, response.user_message, response.ai_response],
          lastUpdated: new Date().toISOString(),
          error: null,
        }));

        return response;
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to send message';
        setState((prev) => ({
          ...prev,
          error: errorMessage,
        }));
        return null;
      }
    },
    [disputeId, sessionId]
  );

  const submitOffer = useCallback(
    async (amount: number) => {
      if (!disputeId || !sessionId) return;

      try {
        const offer = await mediationApi.submitOffer(
          disputeId,
          sessionId,
          amount
        );

        setState((prev) => ({
          ...prev,
          offers: [...prev.offers, offer],
          lastUpdated: new Date().toISOString(),
          error: null,
        }));

        return offer;
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to submit offer';
        setState((prev) => ({
          ...prev,
          error: errorMessage,
        }));
        return null;
      }
    },
    [disputeId, sessionId]
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
