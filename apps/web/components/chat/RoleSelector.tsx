'use client';

import { Home, User, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { PartyRole } from '@/lib/types/chat';

interface RoleSelectorProps {
  onSelect: (role: PartyRole) => void;
  disabled?: boolean;
}

export function RoleSelector({ onSelect, disabled }: RoleSelectorProps) {
  return (
    <div className="max-w-3xl mx-auto p-4">
      <div className="grid sm:grid-cols-2 gap-3">
        {/* Tenant button */}
        <button
          onClick={() => onSelect('tenant')}
          disabled={disabled}
          className={cn(
            'group relative flex items-center gap-4 p-4 rounded-xl border-2 border-border/50',
            'bg-background hover:bg-muted/50 hover:border-primary/30',
            'transition-all duration-200',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50'
          )}
        >
          <div className="p-3 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 transition-transform group-hover:scale-110">
            <User className="h-6 w-6" />
          </div>
          <div className="flex-1 text-left">
            <span className="block font-semibold">I'm a Tenant</span>
            <span className="block text-xs text-muted-foreground">
              Disputing deposit deductions
            </span>
          </div>
          <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        </button>
        
        {/* Landlord button */}
        <button
          onClick={() => onSelect('landlord')}
          disabled={disabled}
          className={cn(
            'group relative flex items-center gap-4 p-4 rounded-xl border-2 border-border/50',
            'bg-background hover:bg-muted/50 hover:border-primary/30',
            'transition-all duration-200',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50'
          )}
        >
          <div className="p-3 rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400 transition-transform group-hover:scale-110">
            <Home className="h-6 w-6" />
          </div>
          <div className="flex-1 text-left">
            <span className="block font-semibold">I'm a Landlord</span>
            <span className="block text-xs text-muted-foreground">
              Seeking deposit recovery
            </span>
          </div>
          <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        </button>
      </div>
    </div>
  );
}
