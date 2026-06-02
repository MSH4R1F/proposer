'use client';

import { useState, useCallback } from 'react';
import { predictionsApi } from '@/lib/api/predictions';
import type { PredictionResult } from '@/lib/types/prediction';

interface UsePredictionState {
  prediction: PredictionResult | null;
  isLoading: boolean;
  error: string | null;
}

// Generation can exceed the hosting load balancer's ~60s response timeout.
// When the connection is cut the request rejects ("Failed to fetch") even
// though the backend still completes and persists the prediction. Poll the
// per-case list for a newly-written prediction before surfacing an error.
const RECOVERY_POLL_ATTEMPTS = 24;
const RECOVERY_POLL_INTERVAL_MS = 3000;

async function recoverPersistedPrediction(
  caseId: string,
  priorIds: Set<string>
): Promise<PredictionResult | null> {
  for (let attempt = 0; attempt < RECOVERY_POLL_ATTEMPTS; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, RECOVERY_POLL_INTERVAL_MS));
    try {
      const list = await predictionsApi.listForCase(caseId);
      const fresh = (list?.predictions ?? []).filter(
        (p) => !priorIds.has(p.prediction_id)
      );
      if (fresh.length > 0) {
        const newest = fresh.reduce((a, b) => (a.timestamp > b.timestamp ? a : b));
        return await predictionsApi.get(newest.prediction_id);
      }
    } catch {
      // Keep polling — a transient list/get failure shouldn't abort recovery.
    }
  }
  return null;
}

export function usePrediction() {
  const [state, setState] = useState<UsePredictionState>({
    prediction: null,
    isLoading: false,
    error: null,
  });

  const generatePrediction = useCallback(
    async (caseId: string, includeReasoning: boolean = true) => {
      setState({ prediction: null, isLoading: true, error: null });

      // Snapshot existing predictions so timeout-recovery can distinguish a
      // freshly-generated prediction from a stale one for the same case.
      let priorIds = new Set<string>();
      try {
        const existing = await predictionsApi.listForCase(caseId);
        priorIds = new Set((existing?.predictions ?? []).map((p) => p.prediction_id));
      } catch {
        // Ignore — proceed to generate even if the pre-check fails.
      }

      try {
        const prediction = await predictionsApi.generate({
          case_id: caseId,
          include_reasoning: includeReasoning,
        });

        setState({
          prediction,
          isLoading: false,
          error: null,
        });

        return prediction;
      } catch (error) {
        // The backend may have completed and persisted the prediction even
        // though the long request was cut at the load balancer's ~60s
        // timeout. Recover the persisted result before surfacing an error.
        const recovered = await recoverPersistedPrediction(caseId, priorIds);
        if (recovered) {
          setState({ prediction: recovered, isLoading: false, error: null });
          return recovered;
        }

        const errorMessage =
          error instanceof Error ? error.message : 'Failed to generate prediction';
        setState({
          prediction: null,
          isLoading: false,
          error: errorMessage,
        });
        return null;
      }
    },
    []
  );

  const fetchPrediction = useCallback(async (predictionId: string) => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const prediction = await predictionsApi.get(predictionId);

      setState({
        prediction,
        isLoading: false,
        error: null,
      });

      return prediction;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Failed to fetch prediction';
      setState({
        prediction: null,
        isLoading: false,
        error: errorMessage,
      });
      return null;
    }
  }, []);

  const clearPrediction = useCallback(() => {
    setState({ prediction: null, isLoading: false, error: null });
  }, []);

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  return {
    ...state,
    generatePrediction,
    fetchPrediction,
    clearPrediction,
    clearError,
  };
}
