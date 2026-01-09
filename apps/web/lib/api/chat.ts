import { api } from './client';
import type {
  StartSessionResponse,
  SetRoleResponse,
  ChatMessageResponse,
  SessionStateResponse,
  PartyRole,
  ValidateInviteResponse,
} from '@/lib/types/chat';

interface StartSessionOptions {
  role: PartyRole;
  inviteCode?: string;
  createDispute?: boolean;
}

export const chatApi = {
  startSession: (role: PartyRole, options?: { inviteCode?: string; createDispute?: boolean }) =>
    api.post<StartSessionResponse>('/chat/start', {
      role,
      invite_code: options?.inviteCode,
      create_dispute: options?.createDispute ?? true,
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
};
