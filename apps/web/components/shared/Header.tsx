'use client';

import Link from 'next/link';
import { Scale } from 'lucide-react';
import { ROUTES } from '@/lib/constants/routes';

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 items-center">
        <Link href={ROUTES.HOME} className="flex items-center space-x-2">
          <Scale className="h-6 w-6 text-primary" />
          <span className="font-bold text-xl">Proposer</span>
        </Link>
        <div className="flex flex-1 items-center justify-end space-x-4">
          <nav className="flex items-center space-x-2">
            <Link
              href={ROUTES.CHAT}
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Start Case
            </Link>
          </nav>
        </div>
      </div>
    </header>
  );
}
