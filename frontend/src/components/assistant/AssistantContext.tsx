import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

/**
 * Shared assistant UI state: whether the panel is open and what the orb shows. The
 * chat reports real events (microphone open, request in flight, speech playing,
 * failure); the orb only displays them. Priority: error > listening > speaking >
 * processing > idle.
 */
export type OrbState = 'idle' | 'listening' | 'processing' | 'speaking' | 'error';
type Activity = 'listening' | 'processing' | 'speaking';

/** A live study: one question the assistant researched (its request id is the study id). */
export interface StudyRef {
  id: string;
  guest: boolean;
  question: string;
  /** Raised when the same question is retried, so the stream is reopened. */
  epoch: number;
}

interface AssistantUi {
  open: boolean;
  setOpen: (open: boolean) => void;
  state: OrbState;
  setActivity: (activity: Activity, on: boolean) => void;
  reportError: () => void;
  /** The study shown in the workspace, and the studies of this browser session (newest first). */
  activeStudy: StudyRef | null;
  studies: StudyRef[];
  startStudy: (study: Omit<StudyRef, 'epoch'>) => void;
  openStudy: (id: string, guest: boolean, question?: string) => void;
}

const Ctx = createContext<AssistantUi | null>(null);
const ERROR_MS = 4000;
const STUDIES_KEY = 'osrip.assistant.studies';

function readStudies(): StudyRef[] {
  try {
    const raw = window.sessionStorage.getItem(STUDIES_KEY);
    const list: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(list)
      ? list.filter((s): s is StudyRef => typeof s === 'object' && s !== null && typeof (s as StudyRef).id === 'string').slice(0, 20)
      : [];
  } catch {
    return [];
  }
}

export function AssistantUiProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [studies, setStudies] = useState<StudyRef[]>(readStudies);
  const [activeId, setActiveId] = useState<string | null>(() => studies[0]?.id ?? null);
  useEffect(() => {
    try {
      window.sessionStorage.setItem(STUDIES_KEY, JSON.stringify(studies.slice(0, 20)));
    } catch {
      // Storage can be unavailable; the studies stay listed for this page only.
    }
  }, [studies]);
  const startStudy = useCallback((study: Omit<StudyRef, 'epoch'>) => {
    setStudies((prev) => {
      const found = prev.find((s) => s.id === study.id);
      const next = found ? { ...found, epoch: found.epoch + 1 } : { ...study, epoch: 0 };
      return [next, ...prev.filter((s) => s.id !== study.id)].slice(0, 20);
    });
    setActiveId(study.id);
  }, []);
  const openStudy = useCallback((id: string, guest: boolean, question = '') => {
    setStudies((prev) => (prev.some((s) => s.id === id) ? prev : [{ id, guest, question, epoch: 0 }, ...prev].slice(0, 20)));
    setActiveId(id);
  }, []);
  const activeStudy = studies.find((s) => s.id === activeId) ?? null;
  const [active, setActive] = useState<Record<Activity, boolean>>({ listening: false, processing: false, speaking: false });
  const [error, setError] = useState(false);
  const timer = useRef<number | null>(null);

  const setActivity = useCallback((activity: Activity, on: boolean) => {
    setActive((prev) => (prev[activity] === on ? prev : { ...prev, [activity]: on }));
  }, []);
  const reportError = useCallback(() => {
    setError(true);
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setError(false), ERROR_MS);
  }, []);
  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);

  const state: OrbState = error
    ? 'error'
    : active.listening
      ? 'listening'
      : active.speaking
        ? 'speaking'
        : active.processing
          ? 'processing'
          : 'idle';
  const value = useMemo(
    () => ({ open, setOpen, state, setActivity, reportError, activeStudy, studies, startStudy, openStudy }),
    [open, state, setActivity, reportError, activeStudy, studies, startStudy, openStudy],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

const FALLBACK: AssistantUi = {
  open: false,
  setOpen: () => undefined,
  state: 'idle',
  setActivity: () => undefined,
  reportError: () => undefined,
  activeStudy: null,
  studies: [],
  startStudy: () => undefined,
  openStudy: () => undefined,
};

/** Outside the provider (the full assistant page in tests) the orb state is simply idle. */
export function useAssistantUi(): AssistantUi {
  return useContext(Ctx) ?? FALLBACK;
}
