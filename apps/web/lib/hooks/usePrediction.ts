'use client';

import { useState, useCallback } from 'react';
import { predictionsApi } from '@/lib/api/predictions';
import type { PredictionResult } from '@/lib/types/prediction';

interface UsePredictionState {
  prediction: PredictionResult | null;
  isLoading: boolean;
  error: string | null;
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
