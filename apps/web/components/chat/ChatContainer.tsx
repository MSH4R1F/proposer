'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useChat } from '@/lib/hooks/useChat';
import { ChatHeader } from './ChatHeader';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { RoleSelector } from './RoleSelector';
import { DisputeEntrySelector } from './DisputeEntrySelector';
import { IntakeSidebar } from './IntakeSidebar';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/constants/routes';
import { isValidSessionId } from '@/lib/utils/storage';
import { ArrowRight, Sparkles, PartyPopper, AlertTriangle } from 'lucide-react';

interface ChatContainerProps {
  sessionId?: string;
}

type EntryMode = 'select' | 'new' | 'join';

export function ChatContainer({ sessionId }: ChatContainerProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inviteCodeFromUrl = searchParams.get('invite');
  
  const {
    sessionId: currentSessionId,
    messages,
    stage,
    completeness,
    isLoading,
    error,
    roleSelected,
    caseFile,
    dispute,
    startSession,
    setRole,
    sendMessage,
    resumeSession,
    clearError,
    validateInviteCode,
    showRoleSelector,
    isComplete,
    canGeneratePrediction,
    isWaitingForOtherParty,
    isWaitingForOtherPartyToComplete,
  } = useChat(sessionId);

  const [entryMode, setEntryMode] = useState<EntryMode>(
    inviteCodeFromUrl ? 'join' : 'select'
  );
  const [pendingInviteCode, setPendingInviteCode] = useState<string | null>(
    inviteCodeFromUrl
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const initializedRef = useRef(false);
  const lastSessionIdRef = useRef<string | undefined>(undefined);
  const startingNewSessionRef = useRef(false);

  useEffect(() => {
    if (startingNewSessionRef.current && !sessionId) {
      return;
    }

    if (initializedRef.current && lastSessionIdRef.current === sessionId) {
      return;
    }

    const initializeSession = async () => {
      if (sessionId) {
        initializedRef.current = true;
        lastSessionIdRef.current = sessionId;

        if (!isValidSessionId(sessionId)) {
          router.replace(ROUTES.CHAT);
          return;
        }

        const success = await resumeSession(sessionId);
        if (!success) {
          router.replace(ROUTES.CHAT);
        }
      } else {
        initializedRef.current = true;
      }
    };

    initializeSession();
  }, [sessionId, resumeSession, router]);

  const handleStartNew = () => {
    setEntryMode('new');
  };

  const handleJoinExisting = async (inviteCode: string) => {
    setPendingInviteCode(inviteCode);
    setEntryMode('join');
  };

  const handleRoleSelect = async (role: 'tenant' | 'landlord') => {
    if (currentSessionId) {
      await setRole(role);
    } else {
      startingNewSessionRef.current = true;
      const options = pendingInviteCode
        ? { inviteCode: pendingInviteCode, createDispute: false }
        : { createDispute: true };
      
      const newSessionId = await startSession(role, options);
      if (newSessionId) {
        lastSessionIdRef.current = newSessionId;
        router.replace(ROUTES.CHAT_SESSION(newSessionId));
      }
    }
  };

  const handleValidateCode = async (code: string) => {
    const result = await validateInviteCode(code);
    return result;
  };

  const handleGeneratePrediction = () => {
    if (caseFile?.case_id) {
      router.push(ROUTES.PREDICTION(caseFile.case_id));
    }
  };

  if (sessionId && !currentSessionId && isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center space-y-4 animate-fade-in">
          <LoadingSpinner size="lg" />
          <p className="text-muted-foreground font-medium">Loading your session...</p>
        </div>
      </div>
    );
  }

  const showEntrySelector = !sessionId && !currentSessionId && entryMode === 'select';
  const showRoleSelectorForNew = !sessionId && !currentSessionId && entryMode === 'new';
  const showRoleSelectorForJoin = !sessionId && !currentSessionId && entryMode === 'join' && pendingInviteCode;

  return (
    <div className="flex flex-col h-full">
      <ChatHeader
        stage={stage}
        completeness={completeness}
        sessionId={currentSessionId}
      />

      {error && (
        <div className="shrink-0 px-4 py-2 bg-destructive/10 border-b border-destructive/20">
          <div className="max-w-3xl mx-auto flex items-center gap-3">
            <AlertTriangle className="h-4 w-4 text-destructive shrink-0" />
            <p className="text-sm text-destructive flex-1">{error}</p>
            <Button variant="ghost" size="sm" onClick={clearError}>
              Dismiss
            </Button>
          </div>
        </div>
      )}

      {showEntrySelector ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <DisputeEntrySelector
            onStartNew={handleStartNew}
            onJoinExisting={handleJoinExisting}
            onValidateCode={handleValidateCode}
            isLoading={isLoading}
          />
        </div>
      ) : (showRoleSelectorForNew || showRoleSelectorForJoin) ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <div className="max-w-xl text-center space-y-6">
            <h1 className="text-2xl font-semibold">
              {pendingInviteCode ? 'Join Dispute' : 'Start New Dispute'}
            </h1>
            <p className="text-muted-foreground">
              {pendingInviteCode
                ? 'Please confirm your role in this dispute:'
                : 'First, please tell me which party you are:'}
            </p>
            <RoleSelector onSelect={handleRoleSelect} disabled={isLoading} />
            {!pendingInviteCode && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setEntryMode('select')}
                className="text-muted-foreground"
              >
                ← Back to options
              </Button>
            )}
          </div>
        </div>
      ) : showRoleSelector ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <div className="max-w-xl text-center space-y-6">
            <h1 className="text-2xl font-semibold">Welcome to Proposer</h1>
            <p className="text-muted-foreground">
              I'm here to help you understand your tenancy deposit dispute.
              First, please tell me which party you are:
            </p>
            <RoleSelector onSelect={handleRoleSelect} disabled={isLoading} />
          </div>
        </div>
      ) : (
        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 overflow-hidden">
            <MessageList messages={messages} isLoading={isLoading} />
          </div>
          <IntakeSidebar
            currentStage={stage}
            caseFile={caseFile}
            completeness={completeness}
            isCollapsed={sidebarCollapsed}
            onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
            dispute={dispute}
            userRole={caseFile?.user_role}
          />
        </div>
      )}

      <div className="shrink-0 border-t bg-background">
        {/* Completion Status Banner - Compact and non-blocking */}
        {isComplete && (
          <div className="max-w-3xl mx-auto px-4 pt-3 pb-2">
            <div className={`flex items-center gap-3 p-3 rounded-lg ${
              (isWaitingForOtherParty || isWaitingForOtherPartyToComplete)
                ? 'bg-amber-500/5 border border-amber-500/20' 
                : 'bg-success/5 border border-success/20'
            }`}>
              <div className={`p-1.5 rounded-md ${
                (isWaitingForOtherParty || isWaitingForOtherPartyToComplete) 
                  ? 'bg-amber-500/10' 
                  : 'bg-success/10'
              }`}>
                <PartyPopper className={`h-4 w-4 ${
                  (isWaitingForOtherParty || isWaitingForOtherPartyToComplete) 
                    ? 'text-amber-500' 
                    : 'text-success'
                }`} />
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${
                  (isWaitingForOtherParty || isWaitingForOtherPartyToComplete) 
                    ? 'text-amber-600' 
                    : 'text-success'
                }`}>
                  {isWaitingForOtherParty 
                    ? 'Your Intake Complete!' 
                    : isWaitingForOtherPartyToComplete
                      ? 'Waiting for Other Party'
                      : 'All Required Info Collected!'}
                </p>
                <p className="text-xs text-muted-foreground">
                  {isWaitingForOtherParty
                    ? 'Share invite code with other party'
                    : isWaitingForOtherPartyToComplete
                      ? 'Other party still completing their intake'
                      : 'Ready to generate prediction'}
                </p>
              </div>
              {canGeneratePrediction && (
                <Button onClick={handleGeneratePrediction} size="sm" className="gap-2 shrink-0">
                  <Sparkles className="h-3.5 w-3.5" />
                  Generate
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
          </div>
        )}

        {/* Chat Input - Always visible when role is selected, even if required fields complete */}
        {roleSelected && (
          <ChatInput
            onSend={sendMessage}
            disabled={!roleSelected || isLoading}
            isLoading={isLoading}
            placeholder={
              isComplete
                ? 'Add more details or generate prediction above...'
                : stage === 'confirmation'
                ? 'Type "yes" to confirm or describe any changes...'
                : 'Type your response...'
            }
          />
        )}

        <div className="px-4 py-2 text-center border-t border-border/40">
          <p className="text-[11px] text-muted-foreground/60">
            This service provides legal information, not legal advice. Results are predictions based on similar tribunal cases.
          </p>
        </div>
      </div>
    </div>
  );
}
