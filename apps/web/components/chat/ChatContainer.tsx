'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useChat } from '@/lib/hooks/useChat';
import { ChatHeader } from './ChatHeader';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { RoleSelector } from './RoleSelector';
import { DisputeEntrySelector } from './DisputeEntrySelector';
import { DomainPicker } from './DomainPicker';
import { useDomain } from '@/lib/contexts/DomainContext';
import { BulkPasteForm } from './BulkPasteForm';
import { IntakeSidebar } from './IntakeSidebar';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/constants/routes';
import { isValidSessionId } from '@/lib/utils/storage';
import { ArrowRight, Sparkles, PartyPopper, AlertTriangle, MessageSquare, ClipboardPaste } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { PartyRole } from '@/lib/types/chat';

interface ChatContainerProps {
  sessionId?: string;
}

type EntryMode = 'select' | 'new' | 'join';
type IntakeMode = 'select' | 'guided' | 'paste';

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
    startBulkSession,
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
    hasRecommendedMissing,
    missingRecommended,
  } = useChat(sessionId);

  const { selected: selectedDomain, selectDomain } = useDomain();

  const [entryMode, setEntryMode] = useState<EntryMode>(
    inviteCodeFromUrl ? 'join' : 'select'
  );
  const [pendingInviteCode, setPendingInviteCode] = useState<string | null>(
    inviteCodeFromUrl
  );
  const [intakeMode, setIntakeMode] = useState<IntakeMode>('select');
  const [selectedRole, setSelectedRole] = useState<PartyRole | null>(null);
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

  // For resumed / legacy sessions that have no domain selected, default to the
  // housing deposit domain so the resumed path still works without a picker step.
  useEffect(() => {
    if (sessionId && !selectedDomain) {
      selectDomain('housing.deposit.v1');
    }
  }, [sessionId, selectedDomain, selectDomain]);

  const handleStartNew = () => {
    setEntryMode('new');
  };

  const handleJoinExisting = async (inviteCode: string) => {
    setPendingInviteCode(inviteCode);
    setEntryMode('join');
  };

  const handleRoleSelect = async (role: PartyRole) => {
    if (currentSessionId) {
      await setRole(role);
    } else {
      setSelectedRole(role);
      setIntakeMode('select');
    }
  };

  const handleIntakeModeSelect = async (mode: 'guided' | 'paste') => {
    if (mode === 'guided' && selectedRole) {
      startingNewSessionRef.current = true;
      const options = pendingInviteCode
        ? { inviteCode: pendingInviteCode, createDispute: false, domainId: selectedDomain?.id }
        : { createDispute: true, domainId: selectedDomain?.id };

      const newSessionId = await startSession(selectedRole, options);
      if (newSessionId) {
        lastSessionIdRef.current = newSessionId;
        router.replace(ROUTES.CHAT_SESSION(newSessionId));
      }
    } else if (mode === 'paste') {
      setIntakeMode('paste');
    }
  };

  const handleBulkSubmit = async (caseText: string) => {
    if (!selectedRole) return;

    startingNewSessionRef.current = true;
    const options = pendingInviteCode
      ? { inviteCode: pendingInviteCode, createDispute: false, domainId: selectedDomain?.id }
      : { createDispute: true, domainId: selectedDomain?.id };

    const newSessionId = await startBulkSession(selectedRole, caseText, options);
    if (newSessionId) {
      lastSessionIdRef.current = newSessionId;
      router.replace(ROUTES.CHAT_SESSION(newSessionId));
    }
  };

  const handleValidateCode = async (code: string) => {
    const result = await validateInviteCode(code);
    return result;
  };

  const handleGeneratePrediction = () => {
    if (caseFile?.case_id && dispute?.dispute_id) {
      const params = new URLSearchParams();
      params.set('session', currentSessionId || '');
      params.set('dispute', dispute.dispute_id);
      router.push(ROUTES.PREDICTION(caseFile.case_id) + '?' + params.toString());
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

  const noActiveSession = !sessionId && !currentSessionId;
  const showEntrySelector = noActiveSession && entryMode === 'select' && !selectedRole;
  const showDomainPicker = noActiveSession && entryMode === 'new' && !selectedDomain && !selectedRole;
  const showRoleSelectorForNew = noActiveSession && entryMode === 'new' && !!selectedDomain && !selectedRole;
  const showRoleSelectorForJoin = noActiveSession && entryMode === 'join' && pendingInviteCode && !selectedRole;
  const showIntakeModeSelector = noActiveSession && selectedRole && intakeMode === 'select';
  const showBulkPasteForm = noActiveSession && selectedRole && intakeMode === 'paste';

  return (
    <div className="flex flex-col h-full">
      <ChatHeader
        stage={stage}
        completeness={completeness}
        sessionId={currentSessionId}
        caseId={caseFile?.case_id}
        disputeId={dispute?.dispute_id}
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
      ) : showDomainPicker ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <DomainPicker onSelect={(id) => selectDomain(id)} />
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
            <RoleSelector roles={selectedDomain?.party_roles ?? []} onSelect={handleRoleSelect} disabled={isLoading} />
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
      ) : showIntakeModeSelector ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <div className="w-full max-w-2xl mx-auto space-y-6">
            <div className="text-center space-y-2">
              <h1 className="text-2xl font-semibold">How would you like to proceed?</h1>
              <p className="text-muted-foreground">
                Choose how you'd like to provide your case details
              </p>
            </div>

            <div className="grid sm:grid-cols-2 gap-3 max-w-xl mx-auto">
              <button
                onClick={() => handleIntakeModeSelect('guided')}
                disabled={isLoading}
                className={cn(
                  'group relative flex items-center gap-4 p-4 rounded-xl border-2 border-border/50',
                  'bg-background hover:bg-muted/50 hover:border-primary/30',
                  'transition-all duration-200',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                  'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50'
                )}
              >
                <div className="p-3 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 transition-transform group-hover:scale-110">
                  <MessageSquare className="h-6 w-6" />
                </div>
                <div className="flex-1 text-left">
                  <span className="block font-semibold">Guided Q&A</span>
                  <span className="block text-xs text-muted-foreground">
                    Answer questions step by step
                  </span>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>

              <button
                onClick={() => handleIntakeModeSelect('paste')}
                disabled={isLoading}
                className={cn(
                  'group relative flex items-center gap-4 p-4 rounded-xl border-2 border-border/50',
                  'bg-background hover:bg-muted/50 hover:border-primary/30',
                  'transition-all duration-200',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                  'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50'
                )}
              >
                <div className="p-3 rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400 transition-transform group-hover:scale-110">
                  <ClipboardPaste className="h-6 w-6" />
                </div>
                <div className="flex-1 text-left">
                  <span className="block font-semibold">Paste All Details</span>
                  <span className="block text-xs text-muted-foreground">
                    Describe everything at once
                  </span>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>
            </div>

            <div className="text-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { setSelectedRole(null); setIntakeMode('select'); }}
                className="text-muted-foreground"
              >
                ← Back to role selection
              </Button>
            </div>
          </div>
        </div>
      ) : showBulkPasteForm ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8 overflow-y-auto">
          <BulkPasteForm
            onSubmit={handleBulkSubmit}
            onBack={() => setIntakeMode('select')}
            isLoading={isLoading}
          />
        </div>
      ) : showRoleSelector ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <div className="max-w-xl text-center space-y-6">
            <h1 className="text-2xl font-semibold">Welcome to Proposer</h1>
            <p className="text-muted-foreground">
              I'm here to help you understand your tenancy deposit dispute.
              First, please tell me which party you are:
            </p>
            <RoleSelector roles={selectedDomain?.party_roles ?? []} onSelect={handleRoleSelect} disabled={isLoading} />
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
        {(isComplete || canGeneratePrediction) && (
          <div className="max-w-3xl mx-auto px-4 pt-3 pb-2 space-y-2">
            <div className={`flex items-center gap-3 p-3 rounded-lg ${
              (isWaitingForOtherParty || isWaitingForOtherPartyToComplete)
                ? 'bg-amber-500/5 border border-amber-500/20'
                : !isComplete
                  ? 'bg-blue-500/5 border border-blue-500/20'
                  : hasRecommendedMissing
                    ? 'bg-blue-500/5 border border-blue-500/20'
                    : 'bg-success/5 border border-success/20'
            }`}>
              <div className={`p-1.5 rounded-md ${
                (isWaitingForOtherParty || isWaitingForOtherPartyToComplete) 
                  ? 'bg-amber-500/10'
                  : !isComplete
                    ? 'bg-blue-500/10'
                    : hasRecommendedMissing
                      ? 'bg-blue-500/10'
                      : 'bg-success/10'
              }`}>
                <PartyPopper className={`h-4 w-4 ${
                  (isWaitingForOtherParty || isWaitingForOtherPartyToComplete) 
                    ? 'text-amber-500'
                    : !isComplete
                      ? 'text-blue-500'
                      : hasRecommendedMissing
                        ? 'text-blue-500'
                        : 'text-success'
                }`} />
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${
                  (isWaitingForOtherParty || isWaitingForOtherPartyToComplete) 
                    ? 'text-amber-600'
                    : !isComplete
                      ? 'text-blue-600'
                      : hasRecommendedMissing
                        ? 'text-blue-600'
                        : 'text-success'
                }`}>
                  {isWaitingForOtherParty 
                    ? 'Your Intake Complete!' 
                    : isWaitingForOtherPartyToComplete
                      ? 'Waiting for Other Party'
                      : !isComplete
                        ? 'Enough info for an early prediction'
                        : hasRecommendedMissing
                          ? 'Ready — but more details would help'
                          : 'All Required Info Collected!'}
                </p>
                <p className="text-xs text-muted-foreground">
                  {isWaitingForOtherParty
                    ? 'Share invite code with other party'
                    : isWaitingForOtherPartyToComplete
                      ? 'Other party still completing their intake'
                      : !isComplete
                        ? 'You can generate now or keep adding details for better accuracy'
                        : hasRecommendedMissing
                          ? `Adding ${missingRecommended.join(', ')} would improve accuracy`
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
                : canGeneratePrediction
                ? 'Keep adding details or generate an early prediction above...'
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
