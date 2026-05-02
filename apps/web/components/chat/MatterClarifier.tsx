'use client';

/**
 * SHA-20 Phase 9: clarifier UI for ambiguous routing outcomes.
 *
 * Renders the deterministic-first router's plain-English clarifier
 * text plus a quick-reply button for each candidate matter. Internal
 * domain ids never appear in the rendered DOM — we always go through
 * `matterLabelFor()`.
 *
 * The component is intentionally presentation-only: parents wire the
 * `onSelect` callback to whatever they want to do next (set the
 * session's domain_id, fire a follow-up message, etc.). Use it
 * alongside `MessageBubble` so the clarifier reads as a natural
 * assistant message in the chat.
 */

import { Button } from '@/components/ui/button';
import { Scale } from 'lucide-react';
import { cn } from '@/lib/utils';
import { matterLabelFor } from '@/lib/types/domain';
import type { RoutingMetadata } from '@/lib/types/domain';

interface MatterClarifierProps {
  routing: RoutingMetadata;
  onSelect?: (domainId: string) => void;
  className?: string;
}

export function MatterClarifier({ routing, onSelect, className }: MatterClarifierProps) {
  if (routing.outcome !== 'clarify') return null;

  const candidates = routing.candidate_domains ?? [];
  const labels = routing.candidate_matter_labels ?? candidates.map((id) => matterLabelFor(id));

  return (
    <div className={cn('flex gap-4 px-4 py-3 animate-fade-in', className)}>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Scale className="h-4 w-4" />
      </div>

      <div className="flex flex-col gap-2 max-w-[85%] sm:max-w-[75%]">
        <span className="text-xs font-medium text-primary">Proposer</span>

        <div className="rounded-2xl rounded-tl-sm bg-muted px-4 py-2.5">
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {routing.clarifier_text ??
              'Could you tell me a bit more about which matter you need help with?'}
          </p>
        </div>

        {candidates.length > 0 && (
          <div className="flex flex-wrap gap-2 pt-1">
            {candidates.map((domainId, idx) => (
              <Button
                key={domainId}
                variant="outline"
                size="sm"
                onClick={() => onSelect?.(domainId)}
                className="text-xs"
              >
                {labels[idx] ?? matterLabelFor(domainId)}
              </Button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
