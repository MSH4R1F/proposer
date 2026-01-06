'use client';

import { AlertTriangle, Info } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LegalDisclaimerProps {
  disclaimer?: string;
  variant?: 'warning' | 'info';
  className?: string;
}

const defaultDisclaimer = `This prediction is based on analysis of similar tribunal decisions and does not constitute legal advice. 
Actual tribunal outcomes may differ based on specific circumstances, evidence quality, and judicial discretion. 
Always consult a qualified legal professional for advice specific to your situation.`;

export function LegalDisclaimer({ 
  disclaimer = defaultDisclaimer,
  variant = 'warning',
  className 
}: LegalDisclaimerProps) {
  const isWarning = variant === 'warning';
  
  return (
    <div className={cn(
      'relative overflow-hidden rounded-xl p-4 sm:p-5',
      isWarning 
        ? 'bg-warning/5 border border-warning/20' 
        : 'bg-info/5 border border-info/20',
      className
    )}>
      {/* Decorative gradient */}
      <div className={cn(
        'absolute top-0 left-0 right-0 h-1',
        isWarning
          ? 'bg-gradient-to-r from-warning/50 via-warning to-warning/50'
          : 'bg-gradient-to-r from-info/50 via-info to-info/50'
      )} />
      
      <div className="flex items-start gap-4">
        <div className={cn(
          'shrink-0 p-2 rounded-lg',
          isWarning ? 'bg-warning/10' : 'bg-info/10'
        )}>
          {isWarning ? (
            <AlertTriangle className="h-5 w-5 text-warning" />
          ) : (
            <Info className="h-5 w-5 text-info" />
          )}
        </div>
        
        <div className="flex-1 min-w-0">
          <h4 className={cn(
            'font-semibold text-sm mb-1',
            isWarning ? 'text-warning' : 'text-info'
          )}>
            {isWarning ? 'Important Legal Notice' : 'Information'}
          </h4>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {disclaimer}
          </p>
        </div>
      </div>
    </div>
  );
}
