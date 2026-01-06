'use client';

import { useState, KeyboardEvent, useRef, useEffect } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  isLoading?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  disabled,
  isLoading,
  placeholder = 'Type your message...',
}: ChatInputProps) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [input]);

  const handleSend = () => {
    if (input.trim() && !disabled && !isLoading) {
      onSend(input.trim());
      setInput('');
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const canSend = input.trim() && !disabled && !isLoading;

  return (
    <div className="max-w-3xl mx-auto p-4">
      <div className="relative flex items-end gap-2 rounded-2xl border border-border/50 bg-muted/30 p-2 focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/10 transition-all">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isLoading}
          rows={1}
          className={cn(
            'flex-1 resize-none bg-transparent px-3 py-2 text-sm',
            'placeholder:text-muted-foreground/50',
            'focus:outline-none',
            'disabled:cursor-not-allowed disabled:opacity-50',
            'min-h-[40px] max-h-[200px]'
          )}
        />
        
        <Button
          onClick={handleSend}
          disabled={!canSend}
          size="icon"
          className={cn(
            'h-10 w-10 rounded-xl shrink-0 transition-all',
            canSend ? 'bg-primary hover:bg-primary/90' : 'bg-muted text-muted-foreground'
          )}
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
      
      <p className="text-center text-[10px] text-muted-foreground/50 mt-2">
        Press Enter to send · Shift + Enter for new line
      </p>
    </div>
  );
}
