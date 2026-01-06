'use client';

import { use } from 'react';
import { ChatContainer } from '@/components/chat/ChatContainer';

interface SessionPageProps {
  params: Promise<{
    sessionId: string;
  }>;
}

export default function SessionPage({ params }: SessionPageProps) {
  const { sessionId } = use(params);

  return <ChatContainer sessionId={sessionId} />;
}
