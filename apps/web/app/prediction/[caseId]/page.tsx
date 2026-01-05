'use client';

import { useEffect, use } from 'react';
import { useRouter } from 'next/navigation';
import { usePrediction } from '@/lib/hooks/usePrediction';
import { PredictionCard } from '@/components/prediction/PredictionCard';
import { PredictionSkeleton } from '@/components/prediction/PredictionSkeleton';
import { ErrorMessage } from '@/components/shared/ErrorMessage';
import { Header } from '@/components/shared/Header';
import { Footer } from '@/components/shared/Footer';
import { Button } from '@/components/ui/button';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { ROUTES } from '@/lib/constants/routes';

interface PredictionPageProps {
  params: Promise<{
    caseId: string;
  }>;
}

export default function PredictionPage({ params }: PredictionPageProps) {
  const { caseId } = use(params);
  const router = useRouter();
  const { prediction, isLoading, error, generatePrediction, clearError } =
    usePrediction();

  useEffect(() => {
    if (caseId && !prediction && !isLoading) {
      generatePrediction(caseId);
    }
  }, [caseId, prediction, isLoading, generatePrediction]);

  const handleRetry = () => {
    clearError();
    generatePrediction(caseId);
  };

  const handleBack = () => {
    router.push(ROUTES.CHAT);
  };

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1 container max-w-4xl py-6">
        <div className="mb-6">
          <Button variant="ghost" onClick={handleBack} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Back to Chat
          </Button>
        </div>

        {error && (
          <div className="mb-6">
            <ErrorMessage
              title="Prediction Failed"
              message={error}
              onRetry={handleRetry}
              onDismiss={clearError}
            />
          </div>
        )}

        {isLoading && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-muted-foreground">
              <RefreshCw className="h-4 w-4 animate-spin" />
              <span>Generating prediction based on similar tribunal cases...</span>
            </div>
            <PredictionSkeleton />
          </div>
        )}

        {prediction && !isLoading && <PredictionCard prediction={prediction} />}

        {!prediction && !isLoading && !error && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <p className="text-muted-foreground mb-4">
              No prediction available for this case yet.
            </p>
            <Button onClick={() => generatePrediction(caseId)}>
              Generate Prediction
            </Button>
          </div>
        )}
      </main>
      <Footer />
    </div>
  );
}
