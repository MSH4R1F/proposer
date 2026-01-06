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
    startSessionWithRole,
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
  // Prevent duplicate session creation in React StrictMode (dev) and during redirects
  const startingNewSessionRef = useRef(false);
  const redirectingToSessionRef = useRef<string | null>(null);

  // Debug: Log key state on each render
  if (process.env.NODE_ENV !== 'production') {
    // eslint-disable-next-line no-console
    console.debug('[ChatContainer] Render', {
      sessionIdFromProps: sessionId,
      currentSessionId,
      stage,
      completeness,
      isLoading,
      error,
      roleSelected,
      isComplete,
      canGeneratePrediction,
      showRoleSelector,
      messagesCount: messages.length,
      caseFileId: caseFile?.case_id,
    });
  }

  // Start or resume session on mount
  useEffect(() => {
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.debug('[ChatContainer] useEffect: sessionId change or mount', {
        sessionIdFromProps: sessionId,
        initialized: initializedRef.current,
        lastSessionId: lastSessionIdRef.current,
      });
    }
    // If we've already kicked off a "start new session" flow and we're still on `/chat`
    // (i.e. no sessionId in the URL yet), do not start another one.
    // This commonly happens in dev because React StrictMode runs effects twice.
    if (startingNewSessionRef.current && !sessionId) {
      if (process.env.NODE_ENV !== 'production') {
        // eslint-disable-next-line no-console
        console.debug('[ChatContainer] New session start already in-flight, waiting for redirect...');
      }
      return;
    }

    // Only initialize once, or when sessionId from URL changes
    if (initializedRef.current && lastSessionIdRef.current === sessionId) {
      if (process.env.NODE_ENV !== 'production') {
        // eslint-disable-next-line no-console
        console.debug('[ChatContainer] Already initialized for this sessionId, skipping...');
      }
      return;
    }

    const initializeSession = async () => {
      if (process.env.NODE_ENV !== 'production') {
        // eslint-disable-next-line no-console
        console.debug('[ChatContainer] initializeSession called', { sessionId });
      }
      if (sessionId) {
        // Mark as initialized for this sessionId
        initializedRef.current = true;
        lastSessionIdRef.current = sessionId;

        // Validate session ID format first
        if (!isValidSessionId(sessionId)) {
          if (process.env.NODE_ENV !== 'production') {
            // eslint-disable-next-line no-console
            console.debug('[ChatContainer] Invalid sessionId in URL, redirecting to /chat for role selection');
          }
          // Invalid session ID - redirect to /chat to show role selector
          router.replace(ROUTES.CHAT);
          return;
        }

        // Try to resume the valid-looking session ID
        const success = await resumeSession(sessionId);

        if (process.env.NODE_ENV !== 'production') {
          // eslint-disable-next-line no-console
          console.debug('[ChatContainer] Attempted to resume session', { sessionId, success });
        }

        // If resuming fails, redirect to /chat for role selection
        if (!success) {
          if (process.env.NODE_ENV !== 'production') {
            // eslint-disable-next-line no-console
            console.debug('[ChatContainer] Session resume failed. Redirecting to /chat for role selection');
          }
          router.replace(ROUTES.CHAT);
        }
      } else {
        // No sessionId in URL - just show role selector, don't start session yet
        // Session will be created when user selects a role
        initializedRef.current = true;
        if (process.env.NODE_ENV !== 'production') {
          // eslint-disable-next-line no-console
          console.debug('[ChatContainer] No sessionId in URL, waiting for role selection...');
        }
      }
    };

    initializeSession();
  }, [sessionId, resumeSession, startSession, router]);

  // Handle role selection - creates session if needed
  const handleRoleSelect = async (role: 'tenant' | 'landlord') => {
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.debug('[ChatContainer] Role selected', { role, hasSession: !!currentSessionId });
    }

    if (currentSessionId) {
      // Session already exists (e.g., resumed), just set the role
      await setRole(role);
    } else {
      // No session yet - create one and set role in one flow
      startingNewSessionRef.current = true;
      const newSessionId = await startSessionWithRole(role);
      if (newSessionId) {
        redirectingToSessionRef.current = newSessionId;
        lastSessionIdRef.current = newSessionId;
        router.replace(ROUTES.CHAT_SESSION(newSessionId));
        if (process.env.NODE_ENV !== 'production') {
          // eslint-disable-next-line no-console
          console.debug('[ChatContainer] Session created with role, redirecting', { newSessionId, role });
        }
      }
    }
  };

  const handleGeneratePrediction = () => {
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.debug('[ChatContainer] handleGeneratePrediction called', { caseFile });
    }
    if (caseFile?.case_id) {
      router.push(ROUTES.PREDICTION(caseFile.case_id));
      if (process.env.NODE_ENV !== 'production') {
        // eslint-disable-next-line no-console
        console.debug('[ChatContainer] Navigated to prediction route', { caseId: caseFile.case_id });
      }
    }
  };

  // Show loading only when we have a sessionId but are loading (resuming session)
  // Don't show loading when no session - show role selector instead
  if (sessionId && !currentSessionId && isLoading) {
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.debug('[ChatContainer] Resuming session...');
    }
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center space-y-4 animate-fade-in">
          <LoadingSpinner size="lg" />
          <p className="text-muted-foreground font-medium">Loading your session...</p>
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

      {/* Show role selector as main content before chat starts */}
      {showRoleSelector ? (
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
        <>
          {/* Messages area - takes all available space */}
          <div className="flex-1 overflow-hidden">
            <MessageList messages={messages} isLoading={isLoading} />
          </div>
        </>
      )}

      {/* Bottom section - input OR completion card */}
      <div className="shrink-0 border-t bg-background">

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
