'use client';

import { use, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useMediationExpectation } from '@/lib/hooks/useMediationExpectation';
import { ExpectationCard } from '@/components/mediation/ExpectationCard';
import { CostBenefitTable } from '@/components/mediation/CostBenefitTable';
import { AcceptancePrompt } from '@/components/mediation/AcceptancePrompt';
import { LegalDisclaimer } from '@/components/prediction/LegalDisclaimer';
import { Loader2, AlertTriangle, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ExpectationPageProps {
  params: Promise<{ disputeId: string }>;
}

function ExpectationContent({ disputeId }: { disputeId: string }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const sessionId = searchParams.get('session') || '';

  // Handle missing session ID
  if (!sessionId) {
    return (
      <div className="max-w-xl mx-auto py-12">
        <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-50 border border-amber-200">
          <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium text-amber-900">Missing session information</p>
            <p className="text-sm text-amber-800 mt-1">
              This mediation link requires a valid session ID. Please return to the mediation page and try again.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => router.back()}>
              <ArrowLeft className="h-4 w-4 mr-1" />
              Go Back
            </Button>
            <Button variant="ghost" size="sm" onClick={() => router.push('/')}>
              Home
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const { expectationData, isLoading, error, clearError, refresh } =
    useMediationExpectation(disputeId, sessionId);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground">Loading your expectation data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-xl mx-auto py-12">
        <div className="flex items-start gap-3 p-4 rounded-xl bg-destructive/10 border border-destructive/20">
          <AlertTriangle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium text-destructive">Failed to load expectation data</p>
            <p className="text-sm text-muted-foreground mt-1">{error}</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={refresh}>
              Retry
            </Button>
            <Button variant="ghost" size="sm" onClick={clearError}>
              Dismiss
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (!expectationData) {
    return (
      <div className="max-w-xl mx-auto py-12">
        <div className="flex items-start gap-3 p-4 rounded-xl bg-slate-50 border border-slate-200">
          <AlertTriangle className="h-5 w-5 text-slate-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium text-slate-900">No expectation data found</p>
            <p className="text-sm text-slate-600 mt-1">
              We couldn't retrieve the expectation analysis for this session. Please try again.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={refresh}>
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <ExpectationCard expectationData={expectationData} />
      <CostBenefitTable expectationData={expectationData} />
      <AcceptancePrompt disputeId={disputeId} sessionId={sessionId} role={expectationData.party_role} />
      <LegalDisclaimer
        variant="info"
        disclaimer="This expectation analysis is based on similar tribunal decisions and does not constitute legal advice. Actual outcomes may vary. Always consult a qualified legal professional for advice specific to your situation."
      />
    </div>
  );
}

export default function ExpectationPage({ params }: ExpectationPageProps) {
  const { disputeId } = use(params);

  return (
    <Suspense
      fallback={
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
          <p className="text-muted-foreground">Loading...</p>
        </div>
      }
    >
      <ExpectationContent disputeId={disputeId} />
    </Suspense>
  );
}
