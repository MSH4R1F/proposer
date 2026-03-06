'use client';

import { useState, type KeyboardEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Send, DollarSign, Loader2, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface MediationInputProps {
  onSendMessage: (message: string) => void;
  onSubmitOffer: (amount: number) => void;
  isLoading: boolean;
}

export function MediationInput({
  onSendMessage,
  onSubmitOffer,
  isLoading,
}: MediationInputProps) {
  const [message, setMessage] = useState('');
  const [offerAmount, setOfferAmount] = useState('');
  const [showOfferInput, setShowOfferInput] = useState(false);

  const handleSendMessage = () => {
    if (message.trim() && !isLoading) {
      onSendMessage(message.trim());
      setMessage('');
    }
  };

  const handleSubmitOffer = () => {
    const amount = parseFloat(offerAmount);
    if (!isNaN(amount) && amount > 0 && !isLoading) {
      onSubmitOffer(amount);
      setOfferAmount('');
      setShowOfferInput(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const canSend = message.trim().length > 0 && !isLoading;

  return (
    <div className="border-t p-4 space-y-3 bg-background shrink-0">
      {showOfferInput && (
        <div className="flex gap-2 items-center p-3 rounded-lg bg-muted/50 border">
          <p className="text-sm font-medium shrink-0 text-muted-foreground">
            Make an Offer
          </p>
          <div className="relative flex-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground pointer-events-none">
              £
            </span>
            <Input
              type="number"
              value={offerAmount}
              onChange={(e) => setOfferAmount(e.target.value)}
              placeholder="Enter amount"
              className="pl-7"
              min={0}
              step={0.01}
              disabled={isLoading}
            />
          </div>
          <Button
            size="sm"
            onClick={handleSubmitOffer}
            disabled={isLoading || !offerAmount}
          >
            {isLoading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              'Submit'
            )}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setShowOfferInput(false);
              setOfferAmount('');
            }}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      )}

      <div className="flex gap-2 items-center">
        <Input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          disabled={isLoading}
          className="flex-1"
        />

        <Button
          size="icon"
          onClick={handleSendMessage}
          disabled={!canSend}
          className={cn(
            'h-10 w-10 rounded-xl shrink-0 transition-all',
            canSend
              ? 'bg-primary hover:bg-primary/90'
              : 'bg-muted text-muted-foreground'
          )}
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowOfferInput(!showOfferInput)}
          disabled={isLoading}
          className="gap-1.5 shrink-0 h-10"
        >
          <DollarSign className="h-3 w-3" />
          Make an Offer
        </Button>
      </div>
    </div>
  );
}
