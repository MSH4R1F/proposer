'use client';

import { Home, User } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { PartyRole } from '@/lib/types/chat';

interface RoleSelectorProps {
  onSelect: (role: PartyRole) => void;
  disabled?: boolean;
}

export function RoleSelector({ onSelect, disabled }: RoleSelectorProps) {
  return (
    <div className="p-4">
      <Card className="mx-auto max-w-md">
        <CardHeader className="text-center">
          <CardTitle>Who are you in this dispute?</CardTitle>
          <CardDescription>
            Select your role to get started with the intake process
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col sm:flex-row gap-4">
          <Button
            variant="outline"
            className="flex-1 h-auto py-6 flex-col gap-2"
            onClick={() => onSelect('tenant')}
            disabled={disabled}
          >
            <User className="h-8 w-8" />
            <span className="font-semibold">I'm a Tenant</span>
            <span className="text-xs text-muted-foreground font-normal">
              Disputing deductions from my deposit
            </span>
          </Button>
          <Button
            variant="outline"
            className="flex-1 h-auto py-6 flex-col gap-2"
            onClick={() => onSelect('landlord')}
            disabled={disabled}
          >
            <Home className="h-8 w-8" />
            <span className="font-semibold">I'm a Landlord</span>
            <span className="text-xs text-muted-foreground font-normal">
              Seeking to recover costs from deposit
            </span>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
