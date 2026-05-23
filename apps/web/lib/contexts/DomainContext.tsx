'use client';

import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import type { DomainCatalogItem } from '@/lib/types/domain';
import { domainsApi } from '@/lib/api/domains';

const STORAGE_KEY = 'proposer:selected-domain-id';

interface DomainContextValue {
  catalog: DomainCatalogItem[];
  loading: boolean;
  error: string | null;
  selected: DomainCatalogItem | null;
  selectDomain: (id: string) => void;
  clearDomain: () => void;
}

const DomainContext = createContext<DomainContextValue | null>(null);

export function DomainProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<DomainCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    domainsApi
      .list()
      .then((items) => setCatalog(items))
      .catch((e) => setError(e?.message ?? 'Failed to load domains'))
      .finally(() => setLoading(false));
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) setSelectedId(saved);
    } catch {}
  }, []);

  const selectDomain = (id: string) => {
    setSelectedId(id);
    try { localStorage.setItem(STORAGE_KEY, id); } catch {}
  };
  const clearDomain = () => {
    setSelectedId(null);
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
  };

  const selected = catalog.find((d) => d.id === selectedId) ?? null;

  return (
    <DomainContext.Provider
      value={{ catalog, loading, error, selected, selectDomain, clearDomain }}
    >
      {children}
    </DomainContext.Provider>
  );
}

export function useDomain(): DomainContextValue {
  const ctx = useContext(DomainContext);
  if (!ctx) throw new Error('useDomain must be used within DomainProvider');
  return ctx;
}
