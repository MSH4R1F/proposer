'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { RefreshCw, Clock } from 'lucide-react';

interface MediationHeaderProps {
  disputeId: string;
  lastUpdated: string | null;
  onRefresh: () => void;
}

export function MediationHeader({ disputeId, lastUpdated, onRefresh }: MediationHeaderProps) {
  const [secondsAgo, setSecondsAgo] = useState<number | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    if (!lastUpdated) return;

    const update = () => {
      const diff = Math.floor((Date.now() - new Date(lastUpdated).getTime()) / 1000);
      setSecondsAgo(diff);
    };

    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [lastUpdated]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="flex items-center justify-between px-4 py-3 border-b bg-background shrink-0">
      <div className="space-y-0.5">
        <p className="text-xs font-medium text-muted-foreground font-mono tracking-wide">
          Dispute <span className="text-foreground">{disputeId}</span>
        </p>
        {secondsAgo !== null && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            <span>Last updated {secondsAgo}s ago</span>
          </div>
        )}
        {!lastUpdated && (
          <p className="text-xs text-muted-foreground">Not yet updated</p>
        )}
      </div>

      <Button
        variant="outline"
        size="sm"
        onClick={handleRefresh}
        disabled={isRefreshing}
        className="gap-1.5 h-8"
      >
        <RefreshCw className={`h-3 w-3 ${isRefreshing ? 'animate-spin' : ''}`} />
        Refresh
      </Button>
    </div>
  );
}
