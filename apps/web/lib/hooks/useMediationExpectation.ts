'use client';

import { useState, useCallback, useEffect } from 'react';
import { mediationApi } from '@/lib/api/mediation';
import type { ExpectationData } from '@/lib/types/mediation';

interface UseMediationExpectationState {
  expectationData: ExpectationData | null;
  isLoading: boolean;
  error: string | null;
}

export function useMediationExpectation(
  disputeId: string,
  sessionId: string
) {
  const [state, setState] = useState<UseMediationExpectationState>({
    expectationData: null,
    isLoading: false,
    error: null,
  });

  const fetchExpectationData = useCallback(async () => {
    setState({ expectationData: null, isLoading: true, error: null });

    try {
      const data = await mediationApi.getExpectationData(disputeId, sessionId);

      setState({
        expectationData: data,
        isLoading: false,
        error: null,
      });

      return data;
    } catch (error) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : 'Failed to fetch expectation data';
      setState({
        expectationData: null,
        isLoading: false,
        error: errorMessage,
      });
      return null;
    }
  }, [disputeId, sessionId]);

  useEffect(() => {
    if (disputeId && sessionId) {
      fetchExpectationData();
    }
  }, [disputeId, sessionId, fetchExpectationData]);

  const refresh = useCallback(() => {
    return fetchExpectationData();
  }, [fetchExpectationData]);

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  return {
    ...state,
    refresh,
    clearError,
  };
}
