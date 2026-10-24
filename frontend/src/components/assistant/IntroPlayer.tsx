import { Loader2, Play, Square, Volume1 } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { clipBlob, useIntroClip } from '@/lib/introClips';
import { playAudio, type Playback } from '@/lib/voicePlayer';

import { useAssistantUi } from './AssistantContext';
import { usePersona } from './persona';

const VOLUME_KEY = 'osrip.intro.volume';

function readVolume(): number {
  try {
    const v = Number(window.localStorage.getItem(VOLUME_KEY));
    return Number.isFinite(v) && v >= 0 && v <= 100 && window.localStorage.getItem(VOLUME_KEY) !== null ? v : 80;
  } catch {
    return 80;
  }
}

type State = 'idle' | 'loading' | 'playing' | 'load_failed' | 'play_failed';

/**
 * The chosen persona's recorded Arabic introduction (made with Canva AI Voice), when one has
 * been added (public/audio/intro/manifest.json). It is a recording, labelled as such, and only
 * ever plays this fixed welcome: answers are read by the speech service, never by this clip.
 *
 * Nothing plays until the person presses the button. Choosing the other persona stops it, as
 * does any other audio starting (the shared player plays one thing at a time). Stop and a
 * volume control sit beside it; loading and playback failures are said plainly. Without a
 * clip nothing is shown and the rest of the page works as before.
 */
export function IntroPlayer() {
  const { t } = useTranslation();
  const { persona } = usePersona();
  const { setActivity } = useAssistantUi();
  const clip = useIntroClip(persona.code, 'ar');
  const [state, setState] = useState<State>('idle');
  const [volume, setVolumeState] = useState(readVolume);
  const [showTranscript, setShowTranscript] = useState(false);
  const playback = useRef<Playback | null>(null);
  const attempt = useRef(0);
  const volumeId = useId();

  const stop = () => {
    attempt.current += 1; // a clip still loading will not start
    playback.current?.stop();
    playback.current = null;
    setState('idle');
  };
  // A different persona: whatever was playing stops (and nothing starts late); the controls
  // return to their start (state adjusted while rendering, as React recommends).
  const [shownPersona, setShownPersona] = useState(persona.code);
  if (shownPersona !== persona.code) {
    setShownPersona(persona.code);
    setState('idle');
    setShowTranscript(false);
  }
  useEffect(() => {
    attempt.current += 1;
    playback.current?.stop();
    playback.current = null;
  }, [persona.code]);
  useEffect(() => () => playback.current?.stop(), []);
  useEffect(() => setActivity('speaking', state === 'playing'), [state, setActivity]);

  if (!clip) return null;

  const play = () => {
    const mine = ++attempt.current;
    setState('loading');
    clipBlob(clip)
      .then((blob) => {
        if (mine !== attempt.current) return;
        playback.current = playAudio(blob, {
          onStart: () => { if (mine === attempt.current) setState('playing'); },
          onLevel: (level) => document.documentElement.style.setProperty('--assistant-voice', level.toFixed(3)),
          onEnd: () => { if (mine === attempt.current) { playback.current = null; setState('idle'); } },
          onError: () => { if (mine === attempt.current) { playback.current = null; setState('play_failed'); } },
        }, { volume: volume / 100 });
      })
      .catch(() => { if (mine === attempt.current) setState('load_failed'); });
  };

  const setVolume = (v: number) => {
    setVolumeState(v);
    playback.current?.setVolume(v / 100);
    try { window.localStorage.setItem(VOLUME_KEY, String(v)); } catch { /* kept for this visit */ }
  };

  const busy = state === 'loading' || state === 'playing';
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-2.5 text-xs" data-testid="intro-player" data-state={state}
      data-persona={persona.code}>
      <div className="flex flex-wrap items-center gap-2">
        {busy ? (
          <Button type="button" size="sm" variant="outline" onClick={stop} data-testid="intro-stop">
            {state === 'loading' ? <Loader2 aria-hidden="true" className="animate-spin motion-reduce:animate-none" /> : <Square aria-hidden="true" />}
            {t('voicePanel.intro.stop')}
          </Button>
        ) : (
          <Button type="button" size="sm" variant="outline" onClick={play} data-testid="intro-play">
            <Play aria-hidden="true" />{t('voicePanel.intro.play')}
          </Button>
        )}
        <label htmlFor={volumeId} className="inline-flex items-center gap-1.5">
          <Volume1 aria-hidden="true" className="size-3.5" />
          <span className="sr-only">{t('voicePanel.intro.volume')}</span>
          <input id={volumeId} type="range" min={0} max={100} step={5} value={volume} onChange={(e) => setVolume(Number(e.target.value))}
            className="w-24 accent-primary" data-testid="intro-volume" aria-valuetext={`${volume}%`} title={t('voicePanel.intro.volume')} />
        </label>
        <span role="status" className="min-w-0" data-testid="intro-status">
          {state === 'loading' ? t('voicePanel.intro.loading') : state === 'playing' ? t('voicePanel.intro.playing') : ''}
        </span>
      </div>
      {state === 'load_failed' || state === 'play_failed' ? (
        <p role="alert" className="text-destructive" data-testid="intro-error">{t(`voicePanel.intro.${state === 'load_failed' ? 'loadFailed' : 'playFailed'}`)}</p>
      ) : null}
      <p className="flex flex-wrap items-center gap-2 text-muted-foreground">
        <Badge variant="muted" data-testid="intro-recorded">{t('voicePanel.intro.recorded')}</Badge>
        {clip.transcript ? (
          <button type="button" className="underline underline-offset-2" aria-expanded={showTranscript} onClick={() => setShowTranscript(!showTranscript)}
            data-testid="intro-transcript-toggle">
            {t('voicePanel.transcript')}
          </button>
        ) : null}
      </p>
      {clip.transcript && showTranscript ? (
        <p className="rounded-md bg-muted/60 p-2" dir="rtl" lang="ar" data-testid="intro-transcript">{clip.transcript}</p>
      ) : null}
    </div>
  );
}
