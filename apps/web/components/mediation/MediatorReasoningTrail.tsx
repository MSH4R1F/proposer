import { cn } from '@/lib/utils';
import type { TraceSummary } from '@/lib/types/trace';

interface MediatorReasoningTrailProps {
  trace: TraceSummary;
}

export function MediatorReasoningTrail({ trace }: MediatorReasoningTrailProps) {
  if (trace.steps.length === 0) return null;

  return (
    <details className="mt-2">
      <summary className="text-xs text-muted-foreground cursor-pointer select-none">
        Reasoning trail ({trace.steps.length} steps)
      </summary>
      <ol role="list" className="mt-1 space-y-0.5 list-none">
        {trace.steps.map((step) => (
          <li
            key={`${trace.trace_id}-${step.index}`}
            className={cn(
              'grid grid-cols-[2rem_6rem_1fr_4rem] gap-x-2 text-xs text-muted-foreground tabular-nums',
              step.is_error && 'text-red-500'
            )}
          >
            <span className="text-right">{step.index}</span>
            <span className="truncate">{step.kind}</span>
            <span className="truncate">{step.name ?? '—'}</span>
            <span className="text-right">{step.duration_ms} ms</span>
          </li>
        ))}
      </ol>
    </details>
  );
}
