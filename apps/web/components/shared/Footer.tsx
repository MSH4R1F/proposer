import { AlertTriangle } from 'lucide-react';

export function Footer() {
  return (
    <footer className="border-t bg-muted/40">
      <div className="container py-4">
        <div className="flex items-start gap-2 text-xs text-muted-foreground">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <p>
            <strong>Important:</strong> This service provides legal information
            based on analysis of tribunal decisions, not legal advice. Results
            are predictions and may not reflect the outcome of your specific
            case. Always consult a qualified legal professional for advice
            specific to your situation.
          </p>
        </div>
      </div>
    </footer>
  );
}
