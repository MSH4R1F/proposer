'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { usePrediction } from '@/lib/hooks/usePrediction';
import { PredictionCard } from '@/components/prediction/PredictionCard';
import { PredictionSkeleton } from '@/components/prediction/PredictionSkeleton';
import { ErrorMessage } from '@/components/shared/ErrorMessage';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Scale, Sparkles, Brain, AlertTriangle } from 'lucide-react';
import { ROUTES } from '@/lib/constants/routes';

interface PredictionPageProps {
  params: {
    caseId: string;
  };
}

export default function PredictionPage({ params }: PredictionPageProps) {
  const { caseId } = params;
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
        
        <div className="ml-4">
          <Button 
            variant="ghost" 
            size="sm"
            onClick={handleBack} 
            className="gap-2 text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Chat
          </Button>
        </div>
        
        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5" />
          <span>Prediction Results</span>
        </div>
      </header>
      
      {/* Main content - scrollable */}
      <main className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="max-w-4xl mx-auto px-4 py-8">
          {/* Error state */}
          {error && (
            <div className="mb-6">
              <div className="flex items-center gap-3 p-4 rounded-xl bg-destructive/10 border border-destructive/20">
                <AlertTriangle className="h-5 w-5 text-destructive shrink-0" />
                <div className="flex-1">
                  <p className="font-medium text-destructive">Prediction Failed</p>
                  <p className="text-sm text-muted-foreground">{error}</p>
                </div>
                <Button variant="outline" size="sm" onClick={handleRetry}>
                  Retry
                </Button>
                <Button variant="ghost" size="sm" onClick={clearError}>
                  Dismiss
                </Button>
              </div>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="space-y-6">
              <div className="flex items-center gap-4 p-4 rounded-xl bg-primary/5 border border-primary/10">
                <div className="p-3 rounded-xl bg-primary/10">
                  <Brain className="h-6 w-6 text-primary animate-pulse" />
                </div>
                <div>
                  <h3 className="font-semibold">Analyzing Your Case</h3>
                  <p className="text-sm text-muted-foreground">
                    Comparing against 500+ tribunal decisions...
                  </p>
                </div>
              </div>
              <PredictionSkeleton />
            </div>
          )}

          {/* Prediction results */}
          {prediction && !isLoading && (
            <PredictionCard prediction={prediction} />
          )}

          {/* Empty state */}
          {!prediction && !isLoading && !error && (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="p-4 rounded-2xl bg-primary/10 mb-6">
                <Sparkles className="h-8 w-8 text-primary" />
              </div>
              <h3 className="text-xl font-semibold mb-2">
                No prediction available yet
              </h3>
              <p className="text-muted-foreground mb-6 max-w-md">
                Click below to generate a prediction based on your case details.
              </p>
              <Button 
                onClick={() => generatePrediction(caseId)}
                className="gap-2"
              >
                <Sparkles className="h-4 w-4" />
                Generate Prediction
              </Button>
            </div>
          )}
        </div>
        
        {/* Footer disclaimer */}
        <div className="border-t border-border/40 py-4 mt-8">
          <p className="text-center text-[11px] text-muted-foreground/60 max-w-2xl mx-auto px-4">
            This prediction is based on analysis of similar tribunal decisions and does not constitute legal advice. 
            Always consult a qualified legal professional for advice specific to your situation.
          </p>
        </div>
      </main>
    </div>
  );
}
