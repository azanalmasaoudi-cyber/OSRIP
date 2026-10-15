import type { AppLanguage } from '@/lib/format';

export const SUPPORTED_LANGUAGES: readonly AppLanguage[] = ['en', 'ar'];
export const DEFAULT_LANGUAGE: AppLanguage = 'en';
const STORAGE_KEY = 'osrip.language';

export function directionFor(language: AppLanguage): 'ltr' | 'rtl' {
  return language === 'ar' ? 'rtl' : 'ltr';
}

export function isAppLanguage(value: unknown): value is AppLanguage {
  return value === 'en' || value === 'ar';
}

/** Per-viewer convenience only; storage may be unavailable, so failures are ignored. */
export function readStoredLanguage(): AppLanguage | null {
  try {
    const stored = globalThis.localStorage?.getItem(STORAGE_KEY);
    return isAppLanguage(stored) ? stored : null;
  } catch {
    return null;
  }
}

export function storeLanguage(language: AppLanguage): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, language);
  } catch {
    /* storage blocked: language still switches for this page view */
  }
}
