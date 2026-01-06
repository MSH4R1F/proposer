'use client';

import { Scale } from 'lucide-react';

export function TypingIndicator() {
  return (
    <div className="flex gap-4 px-4 py-3 animate-fade-in">
      {/* Avatar */}
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Scale className="h-4 w-4" />
      </div>
      
      {/* Typing indicator */}
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-primary">Proposer</span>
        <div className="rounded-2xl rounded-tl-sm bg-muted px-4 py-3">
          <div className="flex items-center gap-1.5">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        </div>
      </div>
    </div>
  );
}
