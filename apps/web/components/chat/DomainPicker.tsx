'use client';

import { Badge } from '@/components/ui/badge';
import { Loader2, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useDomain } from '@/lib/contexts/DomainContext';

interface DomainPickerProps {
  onSelect: (domainId: string) => void;
}

export function DomainPicker({ onSelect }: DomainPickerProps) {
  const { catalog, loading, error } = useDomain();

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading domains…
      </div>
    );
  }
  if (error) {
    return <div className="text-destructive text-sm">Couldn't load domains: {error}</div>;
  }

  return (
    <div className="w-full max-w-3xl mx-auto space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold">What kind of dispute is this?</h1>
        <p className="text-muted-foreground">Choose the area that best matches your situation.</p>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {catalog.map((d) => {
          const disabled = d.availability === 'coming_soon';
          return (
            <button
              key={d.id}
              onClick={() => !disabled && onSelect(d.id)}
              disabled={disabled}
              className={cn(
                'group text-left rounded-xl border-2 border-border/50 p-4 transition-all',
                'hover:border-primary/30 hover:bg-muted/50',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'focus:outline-none focus:ring-2 focus:ring-primary/20'
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold">{d.user_facing_name}</span>
                {d.availability === 'research_beta' && <Badge variant="secondary">Research / beta</Badge>}
                {d.availability === 'coming_soon' && <Badge variant="outline">Coming soon</Badge>}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {d.party_roles.map((r) => r.label).join(' vs ')}
              </p>
              {!disabled && (
                <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity mt-2" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
