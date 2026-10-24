import { useCallback, useSyncExternalStore } from 'react';

import { VIEWS, type SeriesView } from '@/api/series';
import type { DataMode, SectionCode } from '@/domain/types';

/**
 * Each sector's selection, kept apart from every other sector's: what is being chosen (the
 * draft) and what the shown results belong to (the applied selection). Changing the
 * electricity dates never touches water or trade. The selections are remembered while the
 * person moves around the site (and through a reload of the tab); the chart's visibility is
 * not stored, so returning to a sector never draws a chart by itself.
 */

/** One series (indicator, area and breakdown), its view and range (period start dates). */
export interface SectorSelection {
  indicator: string;
  area: string;
  /** Commodity, partner and flow codes joined by "|" ("" for none). */
  breakdown: string;
  view: SeriesView;
  from: string;
  to: string;
}

export interface SectorFilterState {
  draft: SectorSelection | null;
  applied: SectorSelection | null;
}

const STORAGE_KEY = 'osrip.sector.selections.v1';
const EMPTY: SectorFilterState = { draft: null, applied: null };

function isSelection(v: unknown): v is SectorSelection {
  if (!v || typeof v !== 'object') return false;
  const s = v as Record<string, unknown>;
  return ['indicator', 'area', 'breakdown', 'from', 'to'].every((k) => typeof s[k] === 'string')
    && (VIEWS as readonly unknown[]).includes(s.view);
}

function load(): Record<string, SectorFilterState> {
  try {
    const raw = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) ?? '{}') as Record<string, { draft?: unknown; applied?: unknown }>;
    const out: Record<string, SectorFilterState> = {};
    for (const [key, value] of Object.entries(raw)) {
      out[key] = {
        draft: isSelection(value?.draft) ? value.draft : null,
        applied: isSelection(value?.applied) ? value.applied : null,
      };
    }
    return out;
  } catch {
    return {};
  }
}

let store: Record<string, SectorFilterState> = load();
const listeners = new Set<() => void>();

function update(key: string, next: SectorFilterState): void {
  store = { ...store, [key]: next };
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* storage blocked: kept in memory for this visit */
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function sameSelection(a: SectorSelection | null, b: SectorSelection | null): boolean {
  if (!a || !b) return a === b;
  return a.indicator === b.indicator && a.area === b.area && a.breakdown === b.breakdown
    && a.view === b.view && a.from === b.from && a.to === b.to;
}

/** One sector's draft and applied selection (per data mode, since the data differ). */
export function useSectorSelection(section: SectionCode, mode: DataMode): {
  state: SectorFilterState;
  setDraft: (next: SectorSelection) => void;
  apply: (selection: SectorSelection) => void;
  clear: () => void;
} {
  const key = `${mode}:${section}`;
  const state = useSyncExternalStore(subscribe, () => store[key] ?? EMPTY, () => EMPTY);
  const setDraft = useCallback((next: SectorSelection) => {
    update(key, { ...(store[key] ?? EMPTY), draft: next });
  }, [key]);
  const apply = useCallback((selection: SectorSelection) => {
    update(key, { draft: selection, applied: selection });
  }, [key]);
  const clear = useCallback(() => update(key, EMPTY), [key]);
  return { state, setDraft, apply, clear };
}
