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

  const startSession = useCallback(async (
    role: PartyRole,
    options?: { inviteCode?: string; createDispute?: boolean }
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

  // Set user role (tenant/landlord) - requires existing session
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

  // Check if other party has joined but not completed their intake
  const otherPartyJoinedButNotComplete = state.dispute !== null && 
    state.dispute.has_both_parties && 
    !state.dispute.is_ready_for_prediction;

  // Check if ALL required fields are present (strict validation)
  // Note: missing_info is an array - check if it exists AND has length 0
  const hasAllRequiredInfo = Array.isArray(state.caseFile?.missing_info) 
    && state.caseFile.missing_info.length === 0;

  // Determine if we can generate prediction
  // For single-party: just need all required info
  // For multi-party: need all required info AND both parties ready
  const disputeReady = state.dispute === null || 
    state.dispute === undefined || 
    state.dispute.is_ready_for_prediction === true;
  
  const canGenerate = hasAllRequiredInfo && disputeReady;

  // Debug logging (can remove later)
  if (hasAllRequiredInfo && !canGenerate) {
    console.log('[useChat] Has all required info but cannot generate:', {
      hasAllRequiredInfo,
      disputeExists: state.dispute !== null && state.dispute !== undefined,
      disputeReady: state.dispute?.is_ready_for_prediction,
      dispute: state.dispute,
    });
  }

  return {
    ...state,
    startSession,
    startSessionWithRole: startSession,
    setRole,
    sendMessage,
    resumeSession,
    clearError,
    reset,
    validateInviteCode,
    // STRICT: Only complete if ALL required fields are present
    isComplete: hasAllRequiredInfo,
    // Can only generate prediction when ALL required info collected AND dispute ready (if applicable)
    canGeneratePrediction: canGenerate,
    showRoleSelector: (!state.sessionId && !state.roleSelected) ||
      (state.stage === 'greeting' && !state.roleSelected),
    hasDispute: state.dispute !== null && state.dispute !== undefined,
    isWaitingForOtherParty: state.dispute !== null && state.dispute !== undefined && !state.dispute.has_both_parties,
    isWaitingForOtherPartyToComplete: otherPartyJoinedButNotComplete,
  };
}
