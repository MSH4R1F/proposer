// Enums as string union types (matches backend Python str enums)
export type MediationStatus =
  | 'expectation_adjustment'
  | 'active_negotiation'
  | 'settled'
  | 'escalated';

export type OfferStatus =
  | 'pending'
  | 'accepted'
  | 'rejected'
  | 'countered'
  | 'expired';

export type MediationMessageType =
  | 'text'
  | 'offer'
  | 'system'
  | 'ai_mediator';

export interface MediationMessage {
  id: string;
  sender_role: string; // 'tenant' | 'landlord' | 'ai_mediator'
  content: string;
  message_type: MediationMessageType;
  timestamp: string;
  metadata?: Record<string, unknown>;
  offer_id?: string;
}

export interface StructuredOffer {
  id: string;
  amount: number;
  proposed_by_role: string; // 'tenant' | 'landlord'
  status: OfferStatus;
  proposed_at: string;
  responded_at?: string;
  counter_amount?: number;
}

export interface MediationSession {
  mediation_id: string;
  dispute_id: string;
  status: MediationStatus;
  messages: MediationMessage[];
  offers: StructuredOffer[];
  started_at: string;
  updated_at: string;
  settled_at?: string;
  settlement_amount?: number;
  escalated_at?: string;
}

export interface TribunalCostComparison {
  tenant_costs: number; // 0 for tenants
  landlord_costs_min: number; // 200
  landlord_costs_max: number; // 500
  timeline_months_min: number; // 6
  timeline_months_max: number; // 12
  stress_description: string;
  risks_of_proceeding: string[];
}

export interface ExpectationData {
  party_role: string;
  prediction_summary: {
    overall_outcome: string;
    overall_confidence: number;
    suggested_amount: number;
    settlement_range: [number, number];
    key_strengths: string[];
    key_weaknesses: string[];
  };
  party_framing: string; // Role-specific framing text
  cost_benefit: {
    settlement_option: {
      amount: number;
      description: string;
    };
    tribunal_option: {
      cost_to_party: number | [number, number];
      timeline: string;
      outcome_uncertainty: string;
    };
  };
  tribunal_costs: TribunalCostComparison;
}

export interface SettlementSummary {
  dispute_id: string;
  mediation_id: string;
  agreed_amount: number;
  parties: {
    tenant_session_id?: string;
    landlord_session_id?: string;
  };
  property?: {
    address?: string;
    postcode?: string;
  };
  deposit_amount?: number;
  settled_at: string;
  disclaimer: string;
}

// Request/Response types for API calls
export interface StartMediationResponse {
  mediation_id: string;
  dispute_id: string;
  status: MediationStatus;
  initial_message?: MediationMessage;
  messages: MediationMessage[];
  offers: StructuredOffer[];
}

export interface SendMessageResponse {
  user_message: MediationMessage;
  ai_response: MediationMessage;
}

export interface OfferActionResponse {
  offer: StructuredOffer;
  new_offer?: StructuredOffer;
  mediation_status: MediationStatus;
  settlement_amount?: number;
  messages: MediationMessage[];
}
