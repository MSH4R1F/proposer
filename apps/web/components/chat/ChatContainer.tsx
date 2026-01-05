'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useChat } from '@/lib/hooks/useChat';
import { ChatHeader } from './ChatHeader';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { RoleSelector } from './RoleSelector';
import { ErrorMessage } from '@/components/shared/ErrorMessage';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ROUTES } from '@/lib/constants/routes';
import { ArrowRight, Sparkles } from 'lucide-react';

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

  // Start or resume session on mount
  useEffect(() => {
    if (sessionId) {
      resumeSession(sessionId);
    } else if (!currentSessionId) {
      startSession();
    }
  }, [sessionId, currentSessionId, resumeSession, startSession]);

  const handleGeneratePrediction = () => {
    if (caseFile?.case_id) {
      router.push(ROUTES.PREDICTION(caseFile.case_id));
    }
  };

  // Initial loading state
  if (!currentSessionId && isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" label="Starting session..." />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <ChatHeader
        stage={stage}
        completeness={completeness}
        sessionId={currentSessionId}
      />

      {error && (
        <div className="p-4">
          <ErrorMessage
            message={error}
            onDismiss={clearError}
            onRetry={() => {
              clearError();
              if (!currentSessionId) {
                startSession();
              }
            }}
          />
        </div>
      )}

      <div className="flex-1 overflow-hidden">
        <MessageList messages={messages} isLoading={isLoading} />
      </div>

      {showRoleSelector && (
        <RoleSelector onSelect={setRole} disabled={isLoading} />
      )}

      {isComplete && canGeneratePrediction && (
        <div className="p-4 border-t">
          <Card className="bg-primary/5 border-primary/20">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Sparkles className="h-5 w-5 text-primary" />
                Intake Complete
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">
                Great! We have collected all the information needed. You can now
                generate a prediction based on similar tribunal cases.
              </p>
              <Button onClick={handleGeneratePrediction} className="gap-2">
                Generate Prediction
                <ArrowRight className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
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
    </div>
  );
}
