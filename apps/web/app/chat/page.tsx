'use client';

import { Suspense } from 'react';
import { ChatContainer } from '@/components/chat/ChatContainer';

function ChatPageContent() {
  return <ChatContainer />;
}

export default function ChatPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-screen">Loading...</div>}>
      <ChatPageContent />
    </Suspense>
  );
}
