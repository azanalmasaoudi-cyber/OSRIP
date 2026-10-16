import { useSyncExternalStore } from 'react';

/**
 * Light, dark or the device's setting, remembered in this browser only. The resolved theme is
 * written to <html data-theme>, which selects the token block in index.css; public/theme-init.js
 * does the same before the first paint (same key and default).
 */
export const THEME_PREFERENCES = ['light', 'dark', 'system'] as const;
export type ThemePreference = (typeof THEME_PREFERENCES)[number];

const STORAGE_KEY = 'osrip.theme';
const DEFAULT_PREFERENCE: ThemePreference = 'dark';
const META_COLOUR = { light: '#f5f5f6', dark: '#09090b' } as const;

function readStored(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return THEME_PREFERENCES.find((p) => p === stored) ?? DEFAULT_PREFERENCE;
  } catch {
    return DEFAULT_PREFERENCE;
  }
}

const systemDark = () => window.matchMedia('(prefers-color-scheme: dark)');
const listeners = new Set<() => void>();
let preference: ThemePreference = readStored();

export function resolveTheme(choice: ThemePreference): 'light' | 'dark' {
  return choice === 'system' ? (systemDark().matches ? 'dark' : 'light') : choice;
}

function apply(): void {
  const theme = resolveTheme(preference);
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', META_COLOUR[theme]);
  listeners.forEach((listener) => listener());
}

export function setThemePreference(next: ThemePreference): void {
  preference = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // Storage blocked: the choice lasts for this visit.
  }
  apply();
}

// Follow the device while "System" is chosen, and other tabs of this browser.
systemDark().addEventListener('change', () => {
  if (preference === 'system') apply();
});
window.addEventListener('storage', (event) => {
  if (event.key !== STORAGE_KEY) return;
  preference = readStored();
  apply();
});
apply();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The chosen preference (not the resolved theme) and a setter. */
export function useThemePreference(): [ThemePreference, (next: ThemePreference) => void] {
  return [useSyncExternalStore(subscribe, () => preference), setThemePreference];
}
