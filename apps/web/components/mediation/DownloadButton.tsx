'use client';

import { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DownloadButtonProps {
  href: string;
  filename?: string;
  className?: string;
}

export function DownloadButton({ href, filename = 'settlement.pdf', className }: DownloadButtonProps) {
  const [isDownloading, setIsDownloading] = useState(false);

  const handleClick = () => {
    setIsDownloading(true);
    // Reset after a short delay — the browser handles the actual download
    setTimeout(() => setIsDownloading(false), 2000);
  };

  return (
    <a
      href={href}
      download={filename}
      onClick={handleClick}
      className={cn(
        'inline-flex items-center justify-center gap-2',
        'rounded-md text-sm font-medium transition-colors',
        'bg-primary text-primary-foreground shadow hover:bg-primary/90',
        'h-9 px-4 py-2',
        isDownloading && 'pointer-events-none opacity-70',
        className
      )}
      aria-disabled={isDownloading}
    >
      {isDownloading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Download className="h-4 w-4" />
      )}
      {isDownloading ? 'Downloading…' : 'Download Settlement PDF'}
    </a>
  );
}
