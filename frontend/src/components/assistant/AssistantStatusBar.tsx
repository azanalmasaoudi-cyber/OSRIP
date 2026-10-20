import { CircleAlert, Loader2, Mic, Search, Sigma, Square, Volume2, VolumeX, PenLine, CheckCircle2 } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useCancelRequest } from '@/api/assistant';
import { Button } from '@/components/ui/button';
import { stopSpeaking } from '@/lib/speech';
import { onPlaybackChange, playingCount, stopAllPlayback } from '@/lib/voicePlayer';
import { cn } from '@/lib/utils';
import type { LiveStudyState } from '@/state/liveStudy';

import { useAssistantUi } from './AssistantContext';

/**
 * What the assistant is doing now, from real events only: the live study's latest stage
 * (searching, calculating, writing), the voice (listening, speaking), the deterministic
 * analysis running, or an error. Two controls stop what is running: the answer being generated
 * (the study ends unanswered and is not counted) and any audio playing on the page.
 */
export type ActivityState = 'idle' | 'searching' | 'calculating' | 'generating' | 'speaking' | 'listening' | 'analysing' | 'error';

const SEARCHING = new Set(['web_search', 'reading']);
const CALCULATING = new Set(['published_data', 'calculating', 'validating_data']);

export function activityOf(study: LiveStudyState | null, orb: string, analysing: boolean, failed: boolean): ActivityState {
  if (failed || orb === 'error' || study?.status === 'failed') return 'error';
  if (orb === 'listening') return 'listening';
  if (orb === 'speaking') return 'speaking';
  if (analysing) return 'analysing';
  if (study && (study.status === 'running' || study.status === 'connecting')) {
    const last = study.stages[study.stages.length - 1]?.stage ?? '';
    if (SEARCHING.has(last)) return 'searching';
    if (CALCULATING.has(last)) return 'calculating';
    return 'generating';
  }
  if (orb === 'processing') return 'generating';
  return 'idle';
}

const ICON: Record<ActivityState, ReactNode> = {
  idle: <CheckCircle2 aria-hidden="true" className="size-4 text-verified-foreground" />,
  searching: <Search aria-hidden="true" className="size-4" />,
  calculating: <Sigma aria-hidden="true" className="size-4" />,
  generating: <PenLine aria-hidden="true" className="size-4" />,
  speaking: <Volume2 aria-hidden="true" className="size-4" />,
  listening: <Mic aria-hidden="true" className="size-4" />,
  analysing: <Sigma aria-hidden="true" className="size-4" />,
  error: <CircleAlert aria-hidden="true" className="size-4" />,
};

export function AssistantStatusBar({ study, analysing = false, failed = false }: {
  study: LiveStudyState | null;
  analysing?: boolean;
  failed?: boolean;
}) {
  const { t } = useTranslation();
  const ui = useAssistantUi();
  const cancel = useCancelRequest();
  const state = activityOf(study, ui.state, analysing, failed);
  const busy = state !== 'idle' && state !== 'error';
  const running = Boolean(study && (study.status === 'running' || study.status === 'connecting'));
  const [audio, setAudio] = useState(playingCount());
  useEffect(() => onPlaybackChange(setAudio), []);
  const speaking = audio > 0 || ui.state === 'speaking';
  return (
    <div className={cn('flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors motion-reduce:transition-none',
      state === 'error' ? 'border-destructive/50 bg-destructive/5' : busy ? 'border-sand/60 bg-sand-subtle/40' : 'border-border bg-card')}
      data-testid="assistant-status-bar" data-state={state}>
      <span className="sr-only">{t('statusBar.label')}: </span>
      <span className="inline-flex min-w-0 flex-1 items-center gap-2 font-medium" role="status" aria-live="polite" data-testid="assistant-activity">
        {busy && state !== 'speaking' && state !== 'listening'
          ? <Loader2 aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" /> : ICON[state]}
        {t(`statusBar.${state}`)}
      </span>
      {running && ui.activeStudy ? (
        <Button type="button" size="sm" variant="outline" disabled={cancel.isPending} data-testid="stop-generation"
          onClick={() => cancel.mutate({ requestId: ui.activeStudy?.id ?? '', guest: ui.activeStudy?.guest ?? true })}>
          <Square aria-hidden="true" />{t('statusBar.stopGeneration')}
        </Button>
      ) : null}
      {speaking ? (
        <Button type="button" size="sm" variant="outline" data-testid="stop-audio" onClick={() => { stopAllPlayback(); stopSpeaking(); }}>
          <VolumeX aria-hidden="true" />{t('statusBar.stopAudio')}
        </Button>
      ) : null}
    </div>
  );
}
