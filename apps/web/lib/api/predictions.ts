import { api } from './client';
import type {
  PredictionResult,
  GeneratePredictionRequest,
  PredictionListResponse,
  CaseReadinessResult,
} from '@/lib/types/prediction';

export const predictionsApi = {
  checkReady: (caseId: string) =>
    api.get<CaseReadinessResult>(`/predictions/check/${caseId}`),

  generate: (request: GeneratePredictionRequest) =>
    api.post<PredictionResult>('/predictions/generate', request),

  get: (predictionId: string) =>
    api.get<PredictionResult>(`/predictions/${predictionId}`),

  listForCase: (caseId: string) =>
    api.get<PredictionListResponse>(`/predictions/case/${caseId}`),
};
