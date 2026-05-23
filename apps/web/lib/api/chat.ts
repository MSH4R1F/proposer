import { api } from './client';
import type {
  StartSessionResponse,
  SetRoleResponse,
  ChatMessageResponse,
  SessionStateResponse,
  PartyRole,
  ValidateInviteResponse,
  BulkIntakeResponse,
} from '@/lib/types/chat';
import type { RouteResponse } from '@/lib/types/domain';

export const chatApi = {
  startSession: (role: PartyRole, options?: { inviteCode?: string; createDispute?: boolean; domainId?: string }) =>
    api.post<StartSessionResponse>('/chat/start', {
      role,
      invite_code: options?.inviteCode,
      create_dispute: options?.createDispute ?? true,
      domain_id: options?.domainId,
    }),

  setRole: (sessionId: string, role: PartyRole) =>
    api.post<SetRoleResponse>('/chat/set-role', {
      session_id: sessionId,
      role,
    }),

  sendMessage: (sessionId: string, message: string) =>
    api.post<ChatMessageResponse>('/chat/message', {
      session_id: sessionId,
      message,
    }),

  getSession: (sessionId: string) =>
    api.get<SessionStateResponse>(`/chat/session/${sessionId}`),

  deleteSession: (sessionId: string) =>
    api.delete<{ message: string }>(`/chat/session/${sessionId}`),

  listSessions: () =>
    api.get<{
      sessions: Array<{
        session_id: string;
        case_id: string;
        stage: string;
        is_complete: boolean;
      }>;
    }>('/chat/sessions'),

  validateInviteCode: (inviteCode: string) =>
    api.post<ValidateInviteResponse>('/disputes/validate-invite', { invite_code: inviteCode }),

  bulkIntake: (role: PartyRole, caseText: string, options?: { inviteCode?: string; createDispute?: boolean; domainId?: string }) =>
    api.post<BulkIntakeResponse>('/chat/bulk-intake', {
      role,
      case_text: caseText,
      invite_code: options?.inviteCode,
      create_dispute: options?.createDispute ?? true,
      domain_id: options?.domainId,
    }),

  /**
   * SHA-20 Phase 9: classify a free-form intake message before
   * persisting a session. Returns a deterministic-first routing
   * decision (route / clarify / unsupported / abstain).
   */
  route: (text: string) => api.post<RouteResponse>('/chat/route', { text }),
};
