'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useChat } from '@/lib/hooks/useChat';
import { ChatHeader } from './ChatHeader';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { RoleSelector } from './RoleSelector';
import { ErrorMessage } from '@/components/shared/ErrorMessage';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/constants/routes';
import { isValidSessionId } from '@/lib/utils/storage';
import { ArrowRight, Sparkles, PartyPopper, CheckCircle2, AlertTriangle } from 'lucide-react';

interface ChatContainerProps {
  sessionId?: string;
}

export function ChatContainer({ sessionId }: ChatContainerProps) {
  const router = useRouter();
  const {
    sessionId: currentSessionId,
    messages,
    stage,
    completeness,
    isLoading,
    error,
    roleSelected,
    caseFile,
    startSession,
    setRole,
    sendMessage,
    resumeSession,
    clearError,
    showRoleSelector,
    isComplete,
    canGeneratePrediction,
  } = useChat(sessionId);

  // Track if we've already initialized to prevent infinite loops
  const initializedRef = useRef(false);
  const lastSessionIdRef = useRef<string | undefined>(undefined);

  // Start or resume session on mount
  useEffect(() => {
    // Only initialize once, or when sessionId from URL changes
    if (initializedRef.current && lastSessionIdRef.current === sessionId) {
      return;
    }

    const initializeSession = async () => {
      if (sessionId) {
        // Mark as initialized for this sessionId
        initializedRef.current = true;
        lastSessionIdRef.current = sessionId;

        // Validate session ID format first
        if (!isValidSessionId(sessionId)) {
          // Invalid session ID in URL, start a new session
          const newSessionId = await startSession();
          if (newSessionId) {
            lastSessionIdRef.current = newSessionId;
            router.replace(ROUTES.CHAT_SESSION(newSessionId));
          }
          return;
        }

        // Try to resume the valid-looking session ID
        const success = await resumeSession(sessionId);

        // If resuming fails, start new session
        if (!success) {
          const newSessionId = await startSession();
          if (newSessionId) {
            lastSessionIdRef.current = newSessionId;
            router.replace(ROUTES.CHAT_SESSION(newSessionId));
          }
        }
      } else if (!initializedRef.current) {
        // No sessionId in URL, start a new session (only once)
        initializedRef.current = true;

        const newSessionId = await startSession();
        if (newSessionId) {
          // Update ref to prevent re-initialization after redirect
          lastSessionIdRef.current = newSessionId;
          // Navigate to the session-specific URL
          router.replace(ROUTES.CHAT_SESSION(newSessionId));
        }
      }
    };

    initializeSession();
  }, [sessionId, resumeSession, startSession, router]);

  const handleGeneratePrediction = () => {
    if (caseFile?.case_id) {
      router.push(ROUTES.PREDICTION(caseFile.case_id));
    }
  };

  // Initial loading state - centered in full viewport
  if (!currentSessionId && isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center space-y-4 animate-fade-in">
          <LoadingSpinner size="lg" />
          <p className="text-muted-foreground font-medium">Starting your session...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Compact progress header */}
      <ChatHeader
        stage={stage}
        completeness={completeness}
        sessionId={currentSessionId}
      />

      {/* Error banner if any */}
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

      {/* Messages area - takes all available space */}
      <div className="flex-1 overflow-hidden">
        <MessageList messages={messages} isLoading={isLoading} />
      </div>

      {/* Bottom section - role selector OR input OR completion card */}
      <div className="shrink-0 border-t bg-background">
        {showRoleSelector && (
          <RoleSelector onSelect={setRole} disabled={isLoading} />
        )}

        {isComplete && canGeneratePrediction && (
          <div className="max-w-3xl mx-auto p-4">
            <div className="flex items-center gap-4 p-4 rounded-xl bg-success/5 border border-success/20">
              <div className="p-2 rounded-lg bg-success/10">
                <PartyPopper className="h-5 w-5 text-success" />
              </div>
              <div className="flex-1">
                <p className="font-medium text-success">Intake Complete!</p>
                <p className="text-sm text-muted-foreground">All information collected successfully</p>
              </div>
              <Button 
                onClick={handleGeneratePrediction} 
                className="gap-2"
              >
                <Sparkles className="h-4 w-4" />
                Generate Prediction
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {!isComplete && roleSelected && (
          <ChatInput
            onSend={sendMessage}
            disabled={!roleSelected || stage === 'complete'}
            isLoading={isLoading}
            placeholder={
              stage === 'confirmation'
                ? 'Type "yes" to confirm or describe any changes...'
                : 'Type your response...'
            }
          />
        )}

        {/* Disclaimer footer - compact */}
        <div className="px-4 py-2 text-center border-t border-border/40">
          <p className="text-[11px] text-muted-foreground/60">
            This service provides legal information, not legal advice. Results are predictions based on similar tribunal cases.
          </p>
        </div>
      </div>
    </div>
  );
}
