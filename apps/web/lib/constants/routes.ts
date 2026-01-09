export const ROUTES = {
  HOME: '/',
  CHAT: '/chat',
  CHAT_SESSION: (sessionId: string) => `/chat/${sessionId}`,
  PREDICTION: (caseId: string) => `/prediction/${caseId}`,
  ADMIN: '/admin',
} as const;
