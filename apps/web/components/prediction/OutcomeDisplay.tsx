'use client';

import { Card, CardContent } from '@/components/ui/card';
import { ConfidenceGauge } from './ConfidenceGauge';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Scale, Sparkles } from 'lucide-react';

interface OutcomeDisplayProps {
  outcome: 'tenant_favored' | 'landlord_favored' | 'split' | 'uncertain';
  confidence: number;
}

const outcomeConfig = {
  tenant_favored: {
    label: 'Tenant Favored',
    description: 'Based on precedent, the tenant is likely to receive a favorable outcome',
    icon: TrendingUp,
    gradient: 'from-emerald-500/20 via-emerald-500/10 to-teal-500/5',
    border: 'border-emerald-500/20',
    iconBg: 'bg-emerald-500/10',
    iconColor: 'text-emerald-600 dark:text-emerald-400',
    textColor: 'text-emerald-700 dark:text-emerald-300',
  },
  landlord_favored: {
    label: 'Landlord Favored',
    description: 'Based on precedent, the landlord is likely to receive a favorable outcome',
    icon: TrendingDown,
    gradient: 'from-amber-500/20 via-amber-500/10 to-orange-500/5',
    border: 'border-amber-500/20',
    iconBg: 'bg-amber-500/10',
    iconColor: 'text-amber-600 dark:text-amber-400',
    textColor: 'text-amber-700 dark:text-amber-300',
  },
  split: {
    label: 'Split Decision Likely',
    description: 'Both parties may receive partial compensation based on the evidence',
    icon: Scale,
    gradient: 'from-blue-500/20 via-blue-500/10 to-indigo-500/5',
    border: 'border-blue-500/20',
    iconBg: 'bg-blue-500/10',
    iconColor: 'text-blue-600 dark:text-blue-400',
    textColor: 'text-blue-700 dark:text-blue-300',
  },
  uncertain: {
    label: 'Outcome Uncertain',
    description: 'More information may be needed to make a confident prediction',
    icon: Sparkles,
    gradient: 'from-purple-500/20 via-purple-500/10 to-pink-500/5',
    border: 'border-purple-500/20',
    iconBg: 'bg-purple-500/10',
    iconColor: 'text-purple-600 dark:text-purple-400',
    textColor: 'text-purple-700 dark:text-purple-300',
  },
};

export function OutcomeDisplay({ outcome, confidence }: OutcomeDisplayProps) {
  const config = outcomeConfig[outcome] || outcomeConfig.uncertain;
  const Icon = config.icon;

  return (
    <Card className={cn(
      'relative overflow-hidden border-0 shadow-soft',
      config.border
    )}>
      {/* Gradient background */}
      <div className={cn(
        'absolute inset-0 bg-gradient-to-br',
        config.gradient
      )} />
      
      <CardContent className="relative p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row items-center gap-6 sm:gap-8">
          {/* Outcome info */}
          <div className="flex-1 text-center sm:text-left">
            <div className="flex items-center justify-center sm:justify-start gap-3 mb-3">
              <div className={cn('p-2.5 rounded-xl', config.iconBg)}>
                <Icon className={cn('h-6 w-6', config.iconColor)} />
              </div>
              <span className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
                Predicted Outcome
              </span>
            </div>
            
            <h2 className={cn(
              'text-2xl sm:text-3xl font-bold tracking-tight mb-2',
              config.textColor
            )}>
              {config.label}
            </h2>
            
            <p className="text-muted-foreground max-w-md">
              {config.description}
            </p>
          </div>
          
          {/* Confidence gauge */}
          <div className="shrink-0">
            <ConfidenceGauge confidence={confidence} size="lg" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
