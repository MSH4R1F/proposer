import { api } from './client';
import type { DomainCatalogItem } from '@/lib/types/domain';

export const domainsApi = {
  list: () => api.get<DomainCatalogItem[]>('/domains'),
};
