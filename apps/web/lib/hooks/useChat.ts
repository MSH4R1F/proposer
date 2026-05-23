'use client';

import { useState, useCallback, useEffect } from 'react';
import { chatApi } from '@/lib/api/chat';
import { saveSessionId, saveCaseId, getSessionId } from '@/lib/utils/storage';
import type {
  Message,
  ChatState,
  IntakeStage,
  PartyRole,
  CaseFile,
  DisputeInfo,
} from '@/lib/types/chat';
import type { RoutingMetadata } from '@/lib/types/domain';

const initialState: ChatState = {
  sessionId: null,
  messages: [],
  stage: 'greeting',
  completeness: 0,
  isLoading: false,
  error: null,
  roleSelected: false,
  caseFile: null,
  dispute: null,
};

export function useChat(initialSessionId?: string) {
  const [state, setState] = useState<ChatState>({
    ...initialState,
    sessionId: initialSessionId || null,
  });
  // SHA-20 Phase 9: last routing decision returned by the API. The UI
  // surfaces this to render either a clarifier or an "unsupported
  // matter" notice. Internal domain ids never leak; consumers MUST
  // render `routing.matter_label` / `candidate_matter_labels`.
  const [routing, setRouting] = useState<RoutingMetadata | null>(null);

  const startSession = useCallback(async (
    role: PartyRole,
    options?: { inviteCode?: string; createDispute?: boolean; domainId?: string }
  ): Promise<string | null> => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await chatApi.startSession(role, options);

      const assistantMessage: Message = {
        id: `msg_${Date.now()}`,
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
      };

      setState((prev) => ({
        ...prev,
        sessionId: response.session_id,
        messages: [assistantMessage],
        stage: response.stage as IntakeStage,
        completeness: response.completeness,
        roleSelected: true,
        caseFile: response.case_file,
        dispute: response.dispute || null,
        isLoading: false,
      }));

      saveSessionId(response.session_id);
      
      if (response.case_file?.case_id) {
        saveCaseId(response.case_file.case_id);
      }

      return response.session_id;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Failed to start session';
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
      }));
      return null;
    }
  }, []);

  const startBulkSession = useCallback(async (
    role: PartyRole,
    caseText: string,
    options?: { inviteCode?: string; createDispute?: boolean; domainId?: string }
  ): Promise<string | null> => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await chatApi.bulkIntake(role, caseText, options);

      const truncatedText = caseText.length > 200
        ? caseText.slice(0, 200) + '...'
        : caseText;

      const userMessage: Message = {
        id: `msg_${Date.now()}`,
        role: 'user',
        content: truncatedText,
        timestamp: new Date().toISOString(),
      };

      const assistantMessage: Message = {
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
      };

      setState((prev) => ({
        ...prev,
        sessionId: response.session_id,
        messages: [userMessage, assistantMessage],
        stage: response.stage as IntakeStage,
        completeness: response.completeness,
        roleSelected: true,
        caseFile: response.case_file,
        dispute: response.dispute || null,
        isLoading: false,
      }));

      // SHA-20 Phase 9: capture routing metadata if present (only set
      // when DOMAIN_ROUTER_ENABLED=true on the API).
      setRouting(response.routing ?? null);

      saveSessionId(response.session_id);

      if (response.case_file?.case_id) {
        saveCaseId(response.case_file.case_id);
      }

      return response.session_id;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Failed to process case details';
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
      }));
      return null;
    }
  }, []);

  // SHA-20 Phase 9: pre-routing helper. Frontends can call this from a
  // landing page (e.g. "tell us your matter") to decide whether to
  // start a session, ask a clarifier, or surface an unsupported notice
  // — all WITHOUT persisting any session state yet.
  const classifyMatter = useCallback(
    async (text: string): Promise<RoutingMetadata | null> => {
      try {
        const result = await chatApi.route(text);
        setRouting(result.routing ?? null);
        return result.routing ?? null;
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to classify matter';
        setState((prev) => ({ ...prev, error: errorMessage }));
        return null;
      }
    },
    []
  );

  const clearRouting = useCallback(() => setRouting(null), []);

  const setRole = useCallback(
    async (role: PartyRole) => {
      if (!state.sessionId) return;

      setState((prev) => ({ ...prev, isLoading: true, error: null }));

      try {
        const response = await chatApi.setRole(state.sessionId, role);

        const assistantMessage: Message = {
          id: `msg_${Date.now()}`,
          role: 'assistant',
          content: response.response,
          timestamp: new Date().toISOString(),
        };

        setState((prev) => ({
          ...prev,
          messages: [...prev.messages, assistantMessage],
          stage: response.stage as IntakeStage,
          completeness: response.completeness,
          roleSelected: true,
          caseFile: response.case_file,
          isLoading: false,
        }));

        if (response.case_file?.case_id) {
          saveCaseId(response.case_file.case_id);
        }
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to set role';
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error: errorMessage,
        }));
      }
    },
    [state.sessionId]
  );


  // Send a message
  const sendMessage = useCallback(
    async (content: string) => {
      if (!state.sessionId || !content.trim()) return;

      const userMessage: Message = {
        id: `msg_${Date.now()}`,
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
      };

      setState((prev) => ({
        ...prev,
        messages: [...prev.messages, userMessage],
        isLoading: true,
        error: null,
      }));

      try {
        const response = await chatApi.sendMessage(state.sessionId, content);

        const assistantMessage: Message = {
          id: `msg_${Date.now() + 1}`,
          role: 'assistant',
          content: response.response,
          timestamp: new Date().toISOString(),
        };

        setState((prev) => ({
          ...prev,
          messages: [...prev.messages, assistantMessage],
          stage: response.stage as IntakeStage,
          completeness: response.completeness,
          caseFile: response.case_file,
          // CRITICAL: Update dispute status from response (enables prediction button when both parties ready)
          dispute: response.dispute || prev.dispute,
          isLoading: false,
        }));

        if (response.case_file?.case_id) {
          saveCaseId(response.case_file.case_id);
        }
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to send message';
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error: errorMessage,
        }));
      }
    },
    [state.sessionId]
  );

  const resumeSession = useCallback(async (sessionId: string): Promise<boolean> => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await chatApi.getSession(sessionId);

      const restoredMessages: Message[] = (response.messages || []).map((msg, index) => ({
        id: `msg_restored_${index}_${Date.now()}`,
        role: msg.role as 'user' | 'assistant',
        content: msg.content,
        timestamp: msg.timestamp || new Date().toISOString(),
      }));

      const hasRoleSelected = response.stage !== 'greeting';

      setState((prev) => ({
        ...prev,
        sessionId: response.session_id,
        messages: restoredMessages,
        stage: response.stage as IntakeStage,
        completeness: response.completeness,
        caseFile: response.case_file,
        dispute: response.dispute || null,
        roleSelected: hasRoleSelected,
        isLoading: false,
      }));

      saveSessionId(sessionId);
      if (response.case_file?.case_id) {
        saveCaseId(response.case_file.case_id);
      }

      return true;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Failed to resume session';
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
      }));
      return false;
    }
  }, []);

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  const reset = useCallback(() => {
    setState(initialState);
  }, []);

  const validateInviteCode = useCallback(async (inviteCode: string) => {
    try {
      return await chatApi.validateInviteCode(inviteCode);
    } catch (error) {
      return {
        valid: false,
        message: error instanceof Error ? error.message : 'Failed to validate code',
      };
    }
  }, []);

  const otherPartyJoinedButNotComplete = state.dispute !== null && 
    state.dispute.has_both_parties && 
    !state.dispute.is_ready_for_prediction;

  const hasAllRequiredInfo = Array.isArray(state.caseFile?.missing_info) 
    && state.caseFile.missing_info.length === 0;

  const meetsMinimumCompleteness = state.completeness >= 0.5;

  const disputeReady = state.dispute === null || 
    state.dispute === undefined || 
    state.dispute.is_ready_for_prediction === true;
  
  const canGenerate = meetsMinimumCompleteness && disputeReady;

  const missingRecommended: string[] = [];
  if (state.caseFile) {
    if (!state.caseFile.property?.address) missingRecommended.push('property address');
    if (!state.caseFile.tenancy?.start_date) missingRecommended.push('tenancy start date');
    if (!state.caseFile.tenancy?.deposit_amount) missingRecommended.push('deposit amount');
    if (state.caseFile.tenancy?.deposit_protected == null) missingRecommended.push('deposit protection status');
  }

  const hasRecommendedMissing = hasAllRequiredInfo && missingRecommended.length > 0;

  return {
    ...state,
    startSession,
    startSessionWithRole: startSession,
    startBulkSession,
    setRole,
    sendMessage,
    resumeSession,
    clearError,
    reset,
    validateInviteCode,
    classifyMatter,
    clearRouting,
    routing,
    matterLabel: routing?.matter_label ?? null,
    isComplete: hasAllRequiredInfo,
    canGeneratePrediction: canGenerate,
    showRoleSelector: (!state.sessionId && !state.roleSelected) ||
      (state.stage === 'greeting' && !state.roleSelected),
    hasDispute: state.dispute !== null && state.dispute !== undefined,
    isWaitingForOtherParty: state.dispute !== null && state.dispute !== undefined && !state.dispute.has_both_parties,
    isWaitingForOtherPartyToComplete: otherPartyJoinedButNotComplete,
    hasRecommendedMissing,
    missingRecommended,
  };
}
