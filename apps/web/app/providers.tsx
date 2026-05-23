'use client';

import { ReactNode } from 'react';
import { DomainProvider } from '@/lib/contexts/DomainContext';

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  return <DomainProvider>{children}</DomainProvider>;
}
