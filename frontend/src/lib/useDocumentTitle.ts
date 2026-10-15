import { useEffect } from 'react';

/** Sets the browser tab title; it follows the current language. */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = title === 'OSRIP' ? title : `${title} · OSRIP`;
  }, [title]);
}
