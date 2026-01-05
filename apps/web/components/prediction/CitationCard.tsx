import { cn } from '@/lib/utils';
import { ExternalLink, FileText } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { Citation } from '@/lib/types/prediction';

interface CitationCardProps {
  citation: Citation;
  className?: string;
}

export function CitationCard({ citation, className }: CitationCardProps) {
  const similarityPercentage = Math.round(citation.similarity_score * 100);

  return (
    <div
      className={cn(
        'rounded-lg border bg-muted/50 p-4 space-y-2',
        className
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
          <span className="font-medium text-sm">{citation.case_reference}</span>
        </div>
        <div className="flex items-center gap-2">
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
        <span className="text-xs font-medium">
          {similarityPercentage}% similar
        </span>
      </div>
    </div>
  );
}
