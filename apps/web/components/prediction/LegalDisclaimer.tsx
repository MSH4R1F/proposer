import { AlertTriangle } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

interface LegalDisclaimerProps {
  disclaimer?: string;
}

const DEFAULT_DISCLAIMER = `This prediction is based on analysis of similar First-tier Tribunal (Property Chamber) decisions and is provided for informational purposes only. It does not constitute legal advice. Actual outcomes may vary based on specific circumstances, evidence presented, and judicial discretion. Always consult a qualified legal professional for advice specific to your situation.`;

export function LegalDisclaimer({ disclaimer }: LegalDisclaimerProps) {
  return (
    <Alert variant="warning" className="mt-6">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>Important Legal Notice</AlertTitle>
      <AlertDescription className="text-sm">
        {disclaimer || DEFAULT_DISCLAIMER}
      </AlertDescription>
    </Alert>
  );
}
