'use client';

import { ChatContainer } from '@/components/chat/ChatContainer';

interface SessionPageProps {
  params: {
    sessionId: string;
  };
}

export default function SessionPage({ params }: SessionPageProps) {
  const { sessionId } = params;

  return <ChatContainer sessionId={sessionId} />;
}
