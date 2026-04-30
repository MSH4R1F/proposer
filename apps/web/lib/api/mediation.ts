import { api } from './client';
import type {
  MediationSession,
  ExpectationData,
  MediationMessage,
  StructuredOffer,
  SettlementSummary,
  StartMediationResponse,
  SendMessageResponse,
  OfferActionResponse,
} from '@/lib/types/mediation';

// ============================================================================
// Mapping Helpers: Normalize backend responses to frontend types
// ============================================================================

/**
 * Maps raw backend prediction response to frontend ExpectationData shape.
 * Backend returns: { party_role, prediction, analysis, ... }
 * Frontend expects: { prediction_summary, party_framing, cost_benefit, tribunal_costs }
 */
function mapExpectationResponse(raw: Record<string, any>): ExpectationData {
  const prediction = raw.prediction || {};
  const analysis = raw.analysis || {};
  const tribunalCosts = analysis.tribunal_costs || {};

  // Extract settlement range, ensure it's [number, number]
  const settlementRange = prediction.predicted_settlement_range;
  let normalizedRange: [number, number] = [0, 0];
  if (Array.isArray(settlementRange) && settlementRange.length >= 2) {
    try {
      normalizedRange = [Number(settlementRange[0]), Number(settlementRange[1])];
    } catch {
      normalizedRange = [0, 0];
    }
  }

  // Determine settlement amount: use analysis.settlement_amount or midpoint of range
  const settlementAmount =
    analysis.settlement_amount ||
    (normalizedRange[0] + normalizedRange[1]) / 2 ||
    0;

  // Determine cost_to_party based on role
  const role = raw.party_role || 'tenant';
  let costToParty: number | [number, number] = 0;
  if (role === 'tenant') {
    costToParty = tribunalCosts.tenant_costs || 0;
  } else {
    const min = tribunalCosts.landlord_costs_min || 200;
    const max = tribunalCosts.landlord_costs_max || 500;
    costToParty = [min, max];
  }

  // Build timeline string
  const timelineMin = tribunalCosts.timeline_months_min || 6;
  const timelineMax = tribunalCosts.timeline_months_max || 12;
  const timeline = `${timelineMin}-${timelineMax} months`;

  return {
    party_role: role,
    prediction_summary: {
      overall_outcome: prediction.overall_outcome || 'uncertain',
      overall_confidence: prediction.overall_confidence || 0,
      suggested_amount: settlementAmount,
      settlement_range: normalizedRange,
      key_strengths: prediction.key_strengths || [],
      key_weaknesses: prediction.key_weaknesses || [],
    },
    party_framing: analysis.party_framing || getDefaultPartyFraming(role),
    cost_benefit: {
      settlement_option: {
        amount: settlementAmount,
        description: analysis.settlement_framing || '',
      },
      tribunal_option: {
        cost_to_party: costToParty,
        timeline,
        outcome_uncertainty: analysis.tribunal_framing || '',
      },
    },
    tribunal_costs: {
      tenant_costs: tribunalCosts.tenant_costs || 0,
      landlord_costs_min: tribunalCosts.landlord_costs_min || 200,
      landlord_costs_max: tribunalCosts.landlord_costs_max || 500,
      timeline_months_min: tribunalCosts.timeline_months_min || 6,
      timeline_months_max: tribunalCosts.timeline_months_max || 12,
      stress_description: tribunalCosts.stress_description || '',
      risks_of_proceeding: tribunalCosts.risks_of_proceeding || [],
    },
  };
}

/**
 * Maps raw backend settlement response to frontend SettlementSummary shape.
 * Backend returns: { settlement_amount, status, ... }
 * Frontend expects: { agreed_amount, disclaimer, parties, ... }
 */
function mapSettlementResponse(raw: Record<string, any>): SettlementSummary {
  const LEGAL_DISCLAIMER =
    'This is not legal advice. All information is based on analysis of similar tribunal cases.';

  return {
    dispute_id: raw.dispute_id || '',
    mediation_id: raw.mediation_id || '',
    agreed_amount: raw.settlement_amount || 0,
    parties: raw.parties || { tenant_session_id: undefined, landlord_session_id: undefined },
    property: raw.property || { address: undefined, postcode: undefined },
    deposit_amount: raw.deposit_amount,
    settled_at: raw.settled_at || new Date().toISOString(),
    disclaimer: raw.disclaimer || LEGAL_DISCLAIMER,
  };
}

/**
 * Returns default party framing text based on role.
 */
function getDefaultPartyFraming(role: string): string {
  if (role === 'tenant') {
    return 'Based on similar tribunal cases, here is what you might expect if this dispute went to tribunal.';
  }
  return 'Based on similar tribunal cases, here is what the tribunal might decide.';
}

export const mediationApi = {
  startMediation: (disputeId: string, sessionId: string) =>
    api.post<StartMediationResponse>(`/mediation/${disputeId}/start`, {
      session_id: sessionId,
    }),

  getSession: (disputeId: string) =>
    api.get<MediationSession>(`/mediation/${disputeId}/session`),

  /**
   * Fetch expectation data and normalize backend response to frontend shape.
   * Handles mapping of prediction, analysis, and tribunal costs.
   */
  getExpectationData: async (disputeId: string, sessionId: string) => {
    const response = await api.get<Record<string, any>>(
      `/mediation/${disputeId}/expectation/${sessionId}`
    );
    return mapExpectationResponse(response);
  },

  getMessages: (disputeId: string, since?: string) =>
    api.get<{ messages: MediationMessage[]; offers: StructuredOffer[] }>(
      `/mediation/${disputeId}/messages${
        since ? `?since=${encodeURIComponent(since)}` : ''
      }`
    ),

  sendMessage: (disputeId: string, sessionId: string, content: string) =>
    api.post<SendMessageResponse>(`/mediation/${disputeId}/message`, {
      session_id: sessionId,
      content,
    }),

  submitOffer: (disputeId: string, sessionId: string, amount: number) =>
    api.post<StructuredOffer>(`/mediation/${disputeId}/offer`, {
      session_id: sessionId,
      amount,
    }),

  respondToOffer: (
    disputeId: string,
    sessionId: string,
    offerId: string,
    action: 'accept' | 'reject' | 'counter',
    counterAmount?: number
  ) =>
    api.post<OfferActionResponse>(`/mediation/${disputeId}/respond`, {
      session_id: sessionId,
      offer_id: offerId,
      action,
      counter_amount: counterAmount,
    }),

  settle: (disputeId: string, amount: number) =>
    api.post<{
      dispute_id: string;
      status: MediationSession['status'];
      settlement_amount: number;
      settled_at: string;
    }>(`/mediation/${disputeId}/settle`, {
      amount,
    }),

  escalate: (disputeId: string) =>
    api.post<{
      dispute_id: string;
      mediation_status: MediationSession['status'];
      dispute_status: string;
      escalated_at: string;
      messages: MediationMessage[];
    }>(`/mediation/${disputeId}/escalate`),

  /**
   * Fetch settlement data and normalize backend response to frontend shape.
   * Handles mapping of settlement_amount -> agreed_amount and adds disclaimer.
   */
  getSettlement: async (disputeId: string) => {
    const response = await api.get<Record<string, any>>(
      `/mediation/${disputeId}/settlement`
    );
    return mapSettlementResponse(response);
  },

  downloadSettlementPDF: (disputeId: string): string =>
    `${
      process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    }/mediation/${disputeId}/settlement/pdf`,
};
