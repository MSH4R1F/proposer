export type OutcomeType = 'tenant_favored' | 'landlord_favored' | 'split' | 'uncertain';

export interface Citation {
  case_reference: string;
  year: number;
  region?: string;
  paragraph?: string;
  quote: string;
  relevance: string;
  similarity_score: number;
}

export interface ReasoningStep {
  step_number: number;
  category: string;
  title: string;
  content: string;
  citations: Citation[];
  confidence: number;
}

export interface IssuePrediction {
  issue_type: string;
  issue_description?: string;
  predicted_outcome: OutcomeType;
  predicted_amount?: number;
  amount_range?: [number, number];
  confidence: number;
  reasoning: string;
  key_factors: string[];
  supporting_cases?: Citation[];
}

export interface PredictionResult {
  case_id: string;
  prediction_id: string;
  timestamp?: string;
  overall_outcome: OutcomeType;
  overall_confidence: number;
  outcome_summary: string;
  tenant_recovery_amount?: number;
  landlord_recovery_amount?: number;
  predicted_settlement_range?: [number, number];
  deposit_at_stake?: number;
  issue_predictions: IssuePrediction[];
  reasoning_trace: ReasoningStep[];
  key_strengths: string[];
  key_weaknesses: string[];
  uncertainties: string[];
  missing_information?: string[];
  assumptions_made?: string[];
  retrieved_cases: string[];
  total_cases_analyzed: number;
  model_version?: string;
  rag_confidence?: number;
  retrieval_quality?: string;
  disclaimer: string;
}

export interface GeneratePredictionRequest {
  case_id: string;
  include_reasoning?: boolean;
}

export interface PredictionSummary {
  prediction_id: string;
  timestamp: string;
  overall_outcome: OutcomeType;
  overall_confidence: number;
}

export interface PredictionListResponse {
  case_id: string;
  predictions: PredictionSummary[];
}
