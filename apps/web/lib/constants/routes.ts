export const ROUTES = {
  HOME: '/',
  CHAT: '/chat',
  CHAT_SESSION: (sessionId: string) => `/chat/${sessionId}`,
  PREDICTION: (caseId: string) => `/prediction/${caseId}`,
  ADMIN: '/admin',
  MEDIATION_EXPECTATION: (disputeId: string) => `/mediation/${disputeId}/expectation`,
  MEDIATION_CHAT: (disputeId: string) => `/mediation/${disputeId}/chat`,
  MEDIATION_SETTLEMENT: (disputeId: string) => `/mediation/${disputeId}/settlement`,
  MEDIATION_ESCALATION: (disputeId: string) => `/mediation/${disputeId}/escalation`,
} as const;
