'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ArrowLeft, ArrowRight, Loader2 } from 'lucide-react';

interface BulkPasteFormProps {
  onSubmit: (caseText: string) => void;
  onBack: () => void;
  isLoading: boolean;
  disabled?: boolean;
}

const MIN_LENGTH = 20;

const PLACEHOLDER = `Describe your dispute in as much detail as possible. For example:

"I rented a 2-bedroom flat at 45 High Street, London E1 4QJ from January 2023 to December 2023. Monthly rent was 1,500 and I paid a deposit of 1,500 which was protected with TDS.

When I moved out, I left the property clean and in good condition. My landlord is now claiming 400 for professional cleaning and 250 for damage to the kitchen floor, which I believe is fair wear and tear. I have photos from when I moved in and moved out, as well as the check-in inventory..."`;

export function BulkPasteForm({ onSubmit, onBack, isLoading, disabled = false }: BulkPasteFormProps) {
  const [text, setText] = useState('');

  const canSubmit = text.length >= MIN_LENGTH && !isLoading && !disabled;

  const handleSubmit = () => {
    if (canSubmit) {
      onSubmit(text);
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold">Paste Your Case Details</h1>
        <p className="text-muted-foreground">
          Describe your dispute below and we'll extract all the relevant details automatically.
        </p>
      </div>

      <div className="space-y-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={PLACEHOLDER}
          disabled={isLoading || disabled}
          rows={10}
          className="w-full rounded-lg border border-border bg-background px-4 py-3 text-sm resize-y min-h-[200px] focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 disabled:opacity-50 disabled:cursor-not-allowed placeholder:text-muted-foreground/60"
        />
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {text.length < MIN_LENGTH
              ? `At least ${MIN_LENGTH - text.length} more characters needed`
              : `${text.length} characters`}
          </span>
        </div>
      </div>

      <div className="flex gap-3">
        <Button
          variant="outline"
          onClick={onBack}
          disabled={isLoading}
          className="gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>

        <Button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="flex-1 gap-2"
        >
          {isLoading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Extracting details...
            </>
          ) : (
            <>
              Submit
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
