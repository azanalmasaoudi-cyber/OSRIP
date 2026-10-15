import { useEffect, useReducer, useRef } from 'react';

import { adapterKind } from '@/api/config';
import {
  datasetSchema,
  eventSchema,
  studyEventsUrl,
  TERMINAL,
  type Dataset,
  type StudyCompletion,
  type StudyEvidence,
} from '@/api/studyEvents';

/**
 * One live study, rebuilt from its event stream. The same reducer serves a study in progress
 * and a study the person returns to (the stream replays it from the start), so both look the
 * same. Consistency rules:
 *  - events of another study (a cancelled or superseded one) are ignored;
 *  - events are applied once, in order (``seq``); a repeat after a reconnect is ignored;
 *  - nothing is applied after the study ended, except a new attempt of the same request;
 *  - an older ``result_version`` never replaces a newer one;
 *  - a dataset is kept only if it passes the client-side table checks.
 */

// 'none': the question was answered without a study (an approved greeting reply).
export type StudyStatus = 'idle' | 'connecting' | 'running' | 'completed' | 'cancelled' | 'failed' | 'none';

export interface LiveStudyState {
  studyId: string | null;
  status: StudyStatus;
  attempt: number;
  lastSeq: number;
  version: number;
  mode: string | null;
  language: 'en' | 'ar' | null;
  dataMode: string | null;
  stages: { stage: string; label: { en: string; ar: string }; at: string | null }[];
  evidence: StudyEvidence[];
  searches: { evidence_id: string; status: string; query?: string | null; provider?: string | null; role: string; display_only: boolean }[];
  datasets: Dataset[];
  warnings: { code: string; detail: { en: string; ar: string }; seq: number }[];
  rejected: number;
  completion: StudyCompletion | null;
  failure: string | null;
  ignored: number;
}

export const EMPTY_STUDY: LiveStudyState = {
  studyId: null, status: 'idle', attempt: 0, lastSeq: 0, version: 0, mode: null, language: null, dataMode: null,
  stages: [], evidence: [], searches: [], datasets: [], warnings: [], rejected: 0, completion: null, failure: null, ignored: 0,
};

export type StudyAction =
  | { type: 'open'; studyId: string | null }
  | { type: 'event'; raw: unknown }
  | { type: 'end' }
  | { type: 'stream_error' };

const ignore = (state: LiveStudyState): LiveStudyState => ({ ...state, ignored: state.ignored + 1 });

export function studyReducer(state: LiveStudyState, action: StudyAction): LiveStudyState {
  if (action.type === 'open') {
    // Opening (or re-opening after a retry) rebuilds the study from its replayed events.
    return { ...EMPTY_STUDY, studyId: action.studyId, status: action.studyId ? 'connecting' : 'idle' };
  }
  if (action.type === 'end') {
    return state.status === 'connecting' && state.lastSeq === 0 ? { ...state, status: 'none' } : state;
  }
  if (action.type === 'stream_error') {
    return state.status === 'connecting' || state.status === 'running' ? { ...state, failure: state.failure ?? 'stream' } : state;
  }
  const parsed = eventSchema.safeParse(action.raw);
  if (!parsed.success) return { ...ignore(state), rejected: state.rejected + 1 };
  const e = parsed.data;
  if (e.study_id !== state.studyId) return ignore(state); // a cancelled or superseded study
  if (e.seq <= state.lastSeq) return ignore(state); // already applied (a reconnect replays)
  const ended = state.status === 'completed' || state.status === 'cancelled' || state.status === 'failed';
  if (e.type === 'study.started') {
    if (ended && e.payload.attempt <= state.attempt) return ignore(state);
    // A new attempt of the same question starts again from nothing.
    return {
      ...EMPTY_STUDY, studyId: state.studyId, status: 'running', attempt: e.payload.attempt, lastSeq: e.seq,
      version: e.result_version, mode: e.payload.mode, language: e.payload.language, dataMode: e.payload.data_mode,
    };
  }
  if (ended) return ignore(state); // nothing follows the end of a study
  const next: LiveStudyState = { ...state, lastSeq: e.seq, status: 'running', failure: null };
  switch (e.type) {
    case 'stage':
      return { ...next, stages: [...state.stages, { stage: e.payload.stage, label: e.payload.label, at: e.at ?? null }] };
    case 'search':
      return { ...next, searches: [...state.searches, e.payload] };
    case 'evidence':
      return state.evidence.some((x) => x.evidence_id === e.payload.evidence_id) ? next : { ...next, evidence: [...state.evidence, e.payload] };
    case 'warning':
      return { ...next, warnings: [...state.warnings, { ...e.payload, seq: e.seq }] };
    case 'dataset': {
      if (e.result_version < state.version) return { ...next, ignored: state.ignored + 1 };
      const ds = datasetSchema.safeParse(e.payload);
      if (!ds.success) {
        // Never drawn: the reason is shown as a warning instead.
        return {
          ...next, rejected: state.rejected + 1,
          warnings: [...state.warnings, { code: 'dataset_rejected_client', detail: { en: ds.error.issues[0]?.message ?? '', ar: ds.error.issues[0]?.message ?? '' }, seq: e.seq }],
        };
      }
      const datasets = [...state.datasets.filter((d) => d.dataset_id !== ds.data.dataset_id), ds.data];
      return { ...next, version: e.result_version, datasets };
    }
    case 'study.completed': {
      const final = new Set(e.payload.final_datasets);
      return {
        ...next, status: 'completed', version: Math.max(state.version, e.result_version), completion: e.payload,
        datasets: state.datasets.map((d) => ({ ...d, provisional: !final.has(d.dataset_id) })),
      };
    }
    case 'study.cancelled':
      return { ...next, status: 'cancelled' };
    case 'study.failed':
      return { ...next, status: 'failed', failure: e.payload.code };
  }
}

/**
 * Follows one study's server-sent events. ``studyId`` null: nothing is open. Changing the
 * study closes the previous stream first, and late events of the old one are ignored.
 */
export function useLiveStudy(studyId: string | null, guest: boolean, epoch = 0) {
  const [state, dispatch] = useReducer(studyReducer, EMPTY_STUDY);
  const current = useRef<string | null>(null);
  // ``epoch`` changes when the same question is retried (same id): the stream is reopened.
  useEffect(() => {
    current.current = studyId;
    dispatch({ type: 'open', studyId });
    if (!studyId || adapterKind !== 'http' || typeof EventSource === 'undefined') return undefined;
    const source = new EventSource(studyEventsUrl(studyId, guest), { withCredentials: true });
    const onEvent = (message: MessageEvent<string>) => {
      if (current.current !== studyId) return; // superseded: never applied
      let raw: unknown;
      try {
        raw = JSON.parse(message.data);
      } catch {
        return;
      }
      dispatch({ type: 'event', raw });
      if (TERMINAL.has(message.type)) source.close();
    };
    const types = ['study.started', 'stage', 'search', 'evidence', 'dataset', 'warning', 'study.completed', 'study.cancelled', 'study.failed'];
    for (const t of types) source.addEventListener(t, onEvent as EventListener);
    source.addEventListener('end', () => {
      source.close();
      if (current.current === studyId) dispatch({ type: 'end' });
    });
    source.onerror = () => {
      // The browser reconnects by itself (resuming after the last event id); only report it.
      if (source.readyState === EventSource.CLOSED) dispatch({ type: 'stream_error' });
    };
    return () => {
      source.close();
    };
  }, [studyId, guest, epoch]);
  return state;
}
