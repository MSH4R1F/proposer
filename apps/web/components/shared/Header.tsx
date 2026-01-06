'use client';

import Link from 'next/link';
import { Scale, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/constants/routes';

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full h-14 border-b border-border/40 bg-background/80 backdrop-blur-sm">
      <div className="max-w-5xl mx-auto h-full flex items-center justify-between px-4">
        {/* Logo */}
        <Link 
          href={ROUTES.HOME} 
          className="flex items-center gap-2.5 group"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-transform duration-200 group-hover:scale-105">
            <Scale className="h-4 w-4" />
          </div>
          <span className="font-semibold text-lg">Proposer</span>
        </Link>

        {/* Navigation */}
        <nav className="flex items-center gap-4">
          <Link
            href="#how-it-works"
            className="hidden sm:inline-flex text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            How it works
          </Link>
          <Button asChild size="sm" className="gap-2 h-9">
            <Link href={ROUTES.CHAT}>
              <Sparkles className="h-3.5 w-3.5" />
              <span>Start Case</span>
            </Link>
          </Button>
        </nav>
      </div>
    </header>
  );
}
