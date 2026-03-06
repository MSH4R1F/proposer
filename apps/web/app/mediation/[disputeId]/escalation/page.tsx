'use client';

import Link from 'next/link';
import { Scale, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { EscalationOptions } from '@/components/mediation/EscalationOptions';
import { ROUTES } from '@/lib/constants/routes';

export default function EscalationPage() {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* Header */}
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
          <span>Escalation Options</span>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
          {/* Page heading */}
          <div>
            <h2 className="text-2xl font-bold">Next Steps: Escalation</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Mediation did not reach a settlement. Here are your options for resolving this
              dispute through formal channels.
            </p>
          </div>

          {/* Escalation options */}
          <EscalationOptions />

          {/* Return to Home */}
          <div className="flex justify-center pt-4">
            <Link href="/">
              <Button variant="ghost" className="gap-2 text-muted-foreground hover:text-foreground">
                <ArrowLeft className="h-4 w-4" />
                Return to Home
              </Button>
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
