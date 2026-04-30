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

export const mediationApi = {
  startMediation: (disputeId: string, sessionId: string) =>
    api.post<StartMediationResponse>(`/mediation/${disputeId}/start`, {
      session_id: sessionId,
    }),

  getSession: (disputeId: string) =>
    api.get<MediationSession>(`/mediation/${disputeId}/session`),

  getExpectationData: (disputeId: string, sessionId: string) =>
    api.get<ExpectationData>(
      `/mediation/${disputeId}/expectation/${sessionId}`
    ),

  getMessages: (disputeId: string, since?: string) =>
    api.get<MediationMessage[]>(
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

  getSettlement: (disputeId: string) =>
    api.get<SettlementSummary>(`/mediation/${disputeId}/settlement`),

  downloadSettlementPDF: (disputeId: string): string =>
    `${
      process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    }/mediation/${disputeId}/settlement/pdf`,
};
