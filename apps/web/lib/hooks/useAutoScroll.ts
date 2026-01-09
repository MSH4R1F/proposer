'use client';

import { useEffect, useRef, RefObject } from 'react';

export function useAutoScroll<T extends HTMLElement>(
  dependency: unknown[]
): RefObject<T | null> {
  const ref = useRef<T>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTo({
        top: ref.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, dependency);

  return ref;
}
