'use client';

import { useState, useCallback, useEffect } from 'react';
import { mediationApi } from '@/lib/api/mediation';
import type { SettlementSummary } from '@/lib/types/mediation';

interface UseMediationSettlementState {
  settlement: SettlementSummary | null;
  isLoading: boolean;
  error: string | null;
}

export function useMediationSettlement(disputeId: string) {
  const [state, setState] = useState<UseMediationSettlementState>({
    settlement: null,
    isLoading: false,
    error: null,
  });

  const fetchSettlement = useCallback(async () => {
    setState({ settlement: null, isLoading: true, error: null });

    try {
      const data = await mediationApi.getSettlement(disputeId);

      setState({
        settlement: data,
        isLoading: false,
        error: null,
      });

      return data;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Failed to fetch settlement';
      setState({
        settlement: null,
        isLoading: false,
        error: errorMessage,
      });
      return null;
    }
  }, [disputeId]);

  useEffect(() => {
    if (disputeId) {
      fetchSettlement();
    }
  }, [disputeId, fetchSettlement]);

  const refresh = useCallback(() => {
    return fetchSettlement();
  }, [fetchSettlement]);

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  return {
    ...state,
    refresh,
    clearError,
  };
}
