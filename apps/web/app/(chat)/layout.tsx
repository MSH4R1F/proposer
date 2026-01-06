'use client';

import { Scale, Sparkles } from 'lucide-react';
import Link from 'next/link';
import { ROUTES } from '@/lib/constants/routes';

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* Minimal header - Gemini style */}
      <header className="shrink-0 h-14 border-b border-border/40 bg-background/80 backdrop-blur-sm flex items-center px-4">
        <Link 
          href={ROUTES.HOME} 
          className="flex items-center gap-2.5 group"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-transform duration-200 group-hover:scale-105">
            <Scale className="h-4 w-4" />
          </div>
          <span className="font-semibold text-lg">Proposer</span>
        </Link>
        
        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5" />
          <span>AI Legal Analysis</span>
        </div>
      </header>
      
      {/* Full height chat area */}
      <main className="flex-1 overflow-hidden">
        {children}
      </main>
    </div>
  );
}
