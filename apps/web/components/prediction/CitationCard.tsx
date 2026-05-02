import { cn } from '@/lib/utils';
import { ExternalLink, FileText } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { Citation } from '@/lib/types/prediction';
import { forumLabelFor, sourceKindLabelFor } from '@/lib/types/domain';

interface CitationCardProps {
  citation: Citation;
  className?: string;
}

export function CitationCard({ citation, className }: CitationCardProps) {
  const similarityPercentage =
    citation.similarity_score > 0
      ? Math.round(citation.similarity_score * 100)
      : null;
  // SHA-20 Phase 9: render plain-English forum + source-kind labels.
  // The raw enum values (e.g. `first_tier_tribunal_property_chamber`)
  // never reach the DOM.
  const forumLabel = forumLabelFor(citation.forum ?? null);
  const sourceKindLabel = sourceKindLabelFor(citation.source_kind ?? null);

  return (
    <div
      className={cn(
        'rounded-lg border bg-muted/50 p-4 space-y-2',
        className
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
          {citation.source_url ? (
            <a
              href={citation.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-sm inline-flex items-center gap-1 text-primary hover:underline truncate"
              title={`Open ${citation.case_reference} in BAILII`}
            >
              <span className="truncate">{citation.case_reference}</span>
              <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
            </a>
          ) : (
            <span
              className="font-medium text-sm text-muted-foreground truncate"
              title="Source unavailable"
            >
              {citation.case_reference}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {citation.verified === false && (
            <Badge variant="destructive" className="text-xs">
              Removed
            </Badge>
          )}
          {sourceKindLabel && (
            <Badge variant="outline" className="text-xs">
              {sourceKindLabel}
            </Badge>
          )}
          {forumLabel && (
            <Badge variant="secondary" className="text-xs">
              {forumLabel}
            </Badge>
          )}
          {citation.year && (
            <Badge variant="outline" className="text-xs">
              {citation.year}
            </Badge>
          )}
          {citation.region && (
            <Badge variant="secondary" className="text-xs">
              {citation.region}
            </Badge>
          )}
        </div>
      </div>

      {citation.quote && (
        <blockquote className="border-l-2 border-primary/50 pl-3 text-sm italic text-muted-foreground">
          "{citation.quote}"
        </blockquote>
      )}

      {citation.paragraph && (
        <p className="text-xs text-muted-foreground">
          Reference: {citation.paragraph}
        </p>
      )}

      <div className="flex items-center justify-between pt-1">
        <p className="text-xs text-muted-foreground">{citation.relevance}</p>
        {similarityPercentage !== null ? (
          <span className="text-xs font-medium">
            {similarityPercentage}% similar
          </span>
        ) : (
          <span className="text-xs font-medium text-muted-foreground">
            Cited precedent
          </span>
        )}
      </div>
    </div>
  );
}
