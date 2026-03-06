import { cn } from '@/lib/utils';
import type { MediationMessage } from '@/lib/types/mediation';

interface MediationMessageBubbleProps {
  message: MediationMessage;
  currentSessionId: string;
}

const ROLE_CONFIG: Record<
  string,
  { bg: string; border: string; label: string; labelColor: string }
> = {
  tenant: {
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    label: 'Tenant',
    labelColor: 'text-blue-700 bg-blue-100 border-blue-200',
  },
  landlord: {
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    label: 'Landlord',
    labelColor: 'text-amber-700 bg-amber-100 border-amber-200',
  },
  ai_mediator: {
    bg: 'bg-purple-50',
    border: 'border-purple-200',
    label: 'AI Mediator',
    labelColor: 'text-purple-700 bg-purple-100 border-purple-200',
  },
};

const FALLBACK_CONFIG = ROLE_CONFIG.ai_mediator;

export function MediationMessageBubble({
  message,
}: MediationMessageBubbleProps) {
  const config = ROLE_CONFIG[message.sender_role] ?? FALLBACK_CONFIG;

  return (
    <div className={cn('rounded-xl border p-3', config.bg, config.border)}>
      <div className="flex items-center justify-between mb-2">
        <span
          className={cn(
            'text-xs font-medium px-2 py-0.5 rounded-full border',
            config.labelColor
          )}
        >
          {config.label}
        </span>
        <span className="text-[10px] text-muted-foreground tabular-nums">
          {new Date(message.timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      </div>
      <p className="text-sm leading-relaxed whitespace-pre-wrap">
        {message.content}
      </p>
    </div>
  );
}
