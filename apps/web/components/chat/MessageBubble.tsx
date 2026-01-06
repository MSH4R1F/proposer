import { cn } from '@/lib/utils';
import { User, Scale } from 'lucide-react';
import type { Message } from '@/lib/types/chat';

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div
      className={cn(
        'flex gap-4 px-4 py-3 animate-fade-in',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-muted-foreground'
        )}
      >
        {isUser ? (
          <User className="h-4 w-4" />
        ) : (
          <Scale className="h-4 w-4" />
        )}
      </div>
      
      {/* Message content */}
      <div
        className={cn(
          'flex flex-col gap-1 max-w-[85%] sm:max-w-[75%]',
          isUser ? 'items-end' : 'items-start'
        )}
      >
        {/* Sender name */}
        <span className={cn(
          'text-xs font-medium',
          isUser ? 'text-muted-foreground' : 'text-primary'
        )}>
          {isUser ? 'You' : 'Proposer'}
        </span>
        
        {/* Message bubble */}
        <div
          className={cn(
            'rounded-2xl px-4 py-2.5',
            isUser
              ? 'bg-primary text-primary-foreground rounded-tr-sm'
              : 'bg-muted rounded-tl-sm'
          )}
        >
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {message.content}
          </p>
        </div>
        
        {/* Timestamp */}
        {message.timestamp && (
          <span className="text-[10px] text-muted-foreground/50 tabular-nums px-1">
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        )}
      </div>
    </div>
  );
}
