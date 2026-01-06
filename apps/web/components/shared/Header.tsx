'use client';

import Link from 'next/link';
import { Scale, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/constants/routes';

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/80 backdrop-blur-xl supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center justify-between">
        {/* Logo */}
        <Link 
          href={ROUTES.HOME} 
          className="flex items-center gap-2.5 group"
        >
          <div className="relative">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-soft transition-transform duration-300 group-hover:scale-105">
              <Scale className="h-5 w-5" />
            </div>
            <div className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full bg-accent border-2 border-background animate-pulse" />
          </div>
          <div className="flex flex-col">
            <span className="font-bold text-lg tracking-tight">Proposer</span>
            <span className="text-[10px] text-muted-foreground -mt-1 font-medium">AI Legal Analysis</span>
          </div>
        </Link>

        {/* Navigation */}
        <nav className="flex items-center gap-2">
          <Link
            href="#how-it-works"
            className="hidden sm:inline-flex px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors link-underline"
          >
            How it works
          </Link>
          <Button 
            asChild 
            size="sm" 
            className="gap-2 shadow-soft hover:shadow-md transition-all duration-300"
          >
            <Link href={ROUTES.CHAT}>
              <Sparkles className="h-4 w-4" />
              <span>Start Case</span>
            </Link>
          </Button>
        </nav>
      </div>
    </header>
  );
}
