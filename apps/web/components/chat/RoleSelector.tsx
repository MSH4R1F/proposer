'use client';

import { Home, User, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { PartyRoleOption } from '@/lib/types/domain';

interface RoleSelectorProps {
  roles: PartyRoleOption[];
  onSelect: (role: string) => void;
  disabled?: boolean;
}

export function RoleSelector({ roles, onSelect, disabled }: RoleSelectorProps) {
  return (
    <div className="max-w-3xl mx-auto p-4">
      <div className="grid sm:grid-cols-2 gap-3">
        {roles.map((role, idx) => (
          <button
            key={role.value}
            onClick={() => onSelect(role.value)}
            disabled={disabled}
            className={cn(
              'group relative flex items-center gap-4 p-4 rounded-xl border-2 border-border/50',
              'bg-background hover:bg-muted/50 hover:border-primary/30 transition-all duration-200',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50'
            )}
          >
            <div
              className={cn(
                'p-3 rounded-xl transition-transform group-hover:scale-110',
                idx === 0
                  ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
                  : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
              )}
            >
              {idx === 0 ? <User className="h-6 w-6" /> : <Home className="h-6 w-6" />}
            </div>
            <div className="flex-1 text-left">
              <span className="block font-semibold">I'm the {role.label}</span>
              {role.blurb && (
                <span className="block text-xs text-muted-foreground">{role.blurb}</span>
              )}
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
          </button>
        ))}
      </div>
    </div>
  );
}
