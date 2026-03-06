'use client';

import { use } from 'react';
import Link from 'next/link';
import { Scale, ArrowLeft, AlertTriangle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useMediationSettlement } from '@/lib/hooks/useMediationSettlement';
import { SettlementSummary } from '@/components/mediation/SettlementSummary';
import { DownloadButton } from '@/components/mediation/DownloadButton';
import { mediationApi } from '@/lib/api/mediation';
import { ROUTES } from '@/lib/constants/routes';

interface SettlementPageProps {
  params: Promise<{
    disputeId: string;
  }>;
}

export default function SettlementPage({ params }: SettlementPageProps) {
  const { disputeId } = use(params);
  const { settlement, isLoading, error, refresh, clearError } = useMediationSettlement(disputeId);

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
          <span>Settlement Summary</span>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
          {/* Page heading */}
          <div>
            <h2 className="text-2xl font-bold">Settlement Agreement</h2>
            <p className="text-sm text-muted-foreground mt-1">
              A summary of the agreed resolution between both parties.
            </p>
          </div>

          {/* Error state */}
          {error && (
            <div className="flex items-center gap-3 p-4 rounded-xl bg-destructive/10 border border-destructive/20">
              <AlertTriangle className="h-5 w-5 text-destructive shrink-0" />
              <div className="flex-1">
                <p className="font-medium text-destructive">Failed to load settlement</p>
                <p className="text-sm text-muted-foreground">{error}</p>
              </div>
              <Button variant="outline" size="sm" onClick={refresh}>
                Retry
              </Button>
              <Button variant="ghost" size="sm" onClick={clearError}>
                Dismiss
              </Button>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center justify-center py-16">
              <div className="flex flex-col items-center gap-3 text-muted-foreground">
                <Loader2 className="h-8 w-8 animate-spin" />
                <p className="text-sm">Loading settlement details…</p>
              </div>
            </div>
          )}

          {/* Settlement summary */}
          {settlement && !isLoading && (
            <div className="space-y-6">
              <SettlementSummary settlement={settlement} />

              {/* Download PDF */}
              <div className="flex justify-center">
                <DownloadButton
                  href={mediationApi.downloadSettlementPDF(disputeId)}
                  filename={`settlement-${disputeId}.pdf`}
                />
              </div>
            </div>
          )}

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
