import { Headphones, Square, Volume2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { seriesTranscript, speakSeries, useVoiceStatus, type SeriesSpeech } from '@/api/assistant';
import { useMe } from '@/api/auth';
import { ApiRequestError } from '@/api/client';
import { usePersona } from '@/components/assistant/persona';
import { VoiceVolume } from '@/components/assistant/VoiceVolume';
import { Button } from '@/components/ui/button';
import { noVoiceForLanguage, speak, stopSpeaking, voiceFor } from '@/lib/speech';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { playAudio, type Playback } from '@/lib/voicePlayer';

/**
 * A short spoken explanation of the applied selection (latest value, change, missing periods,
 * total where valid), built by the server from the same figures as the table, in the chosen
 * persona's Azure voice. Nothing plays until "Listen" is pressed; Stop, the shared volume and
 * the transcript are beside it. Without the server voice, a browser voice is offered only if
 * this browser actually has one for the language, and it is labelled as the browser's voice.
 */
export function SpokenSummary({ selection }: { selection: SeriesSpeech }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { persona } = usePersona();
  const me = useMe();
  const status = useVoiceStatus();
  const configured = Boolean(status.data?.configured);
  const [state, setState] = useState<'idle' | 'loading' | 'playing'>('idle');
  const [transcript, setTranscript] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [browserVoice, setBrowserVoice] = useState(false);
  const playback = useRef<Playback | null>(null);
  const aborter = useRef<AbortController | null>(null);
  const key = JSON.stringify(selection);

  const stop = () => {
    aborter.current?.abort();
    playback.current?.stop();
    playback.current = null;
    if (browserVoice) stopSpeaking();
    setState('idle');
  };
  // A new selection or leaving the page stops what is playing.
  useEffect(() => () => {
    aborter.current?.abort();
    playback.current?.stop();
    stopSpeaking();
  }, [key]);

  const listen = () => {
    stop();
    setError(null);
    const controller = new AbortController();
    aborter.current = controller;
    setState('loading');
    speakSeries(selection, persona.code, language, Boolean(me.data?.authenticated), controller.signal)
      .then(({ audio, transcript: words }) => {
        if (controller.signal.aborted) return;
        setTranscript(words);
        setBrowserVoice(false);
        playback.current = playAudio(audio, {
          onStart: () => setState('playing'),
          onLevel: () => undefined,
          onEnd: () => setState('idle'),
          onError: () => { setState('idle'); setError(t('voice.notice.playback')); },
        });
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setState('idle');
        const code = e instanceof ApiRequestError ? e.code : '';
        setError(code === 'speech_not_configured' ? t('voicePanel.notConfigured') : t('sectorFlow.listenFailed'));
      });
  };

  const listenInBrowser = () => {
    stop();
    setError(null);
    const controller = new AbortController();
    aborter.current = controller;
    setState('loading');
    seriesTranscript(selection, language, controller.signal)
      .then((words) => {
        if (controller.signal.aborted) return;
        setTranscript(words);
        setBrowserVoice(true);
        const started = speak(words, language, persona.gender, {
          onStart: () => setState('playing'),
          onEnd: () => setState('idle'),
          onError: () => { setState('idle'); setError(t('voice.notice.playback')); },
        });
        if (!started) { setState('idle'); setError(t('sectorFlow.noBrowserVoice')); }
      })
      .catch(() => { if (!controller.signal.aborted) { setState('idle'); setError(t('sectorFlow.listenFailed')); } });
  };

  const showTranscript = () => {
    seriesTranscript(selection, language).then(setTranscript).catch(() => setError(t('sectorFlow.listenFailed')));
  };
  const browserAvailable = !configured && typeof window !== 'undefined' && !noVoiceForLanguage(language)
    && voiceFor(language, persona.gender) !== null;

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3" data-testid="sector-listen-block" data-state={state}>
      <div className="flex flex-wrap items-center gap-2">
        {configured ? (
          <Button size="sm" variant="outline" onClick={listen} disabled={state === 'loading'} data-testid="sector-listen">
            <Headphones aria-hidden="true" />{state === 'loading' ? t('sectorFlow.preparing') : t('sectorFlow.listen', { name: persona.name[language] })}
          </Button>
        ) : (
          <>
            <span className="text-xs text-muted-foreground" data-testid="sector-listen-unavailable">{t('sectorFlow.voiceUnavailable')}</span>
            {browserAvailable ? (
              <Button size="sm" variant="outline" onClick={listenInBrowser} disabled={state === 'loading'} data-testid="sector-listen-browser">
                <Volume2 aria-hidden="true" />{t('sectorFlow.listenBrowser')}
              </Button>
            ) : null}
            <Button size="sm" variant="ghost" onClick={showTranscript} data-testid="sector-show-transcript">{t('sectorFlow.showWords')}</Button>
          </>
        )}
        {state !== 'idle' ? (
          <Button size="sm" variant="ghost" onClick={stop} data-testid="sector-listen-stop"><Square aria-hidden="true" />{t('voicePanel.stop')}</Button>
        ) : null}
        <VoiceVolume testId="sector-listen-volume" />
      </div>
      <p className="text-xs text-muted-foreground">{t('sectorFlow.listenNote')}</p>
      {error ? <p role="alert" className="text-xs text-destructive" data-testid="sector-listen-error">{error}</p> : null}
      {transcript ? (
        <p className="rounded-md bg-muted/60 p-2 text-xs" dir="auto" lang={language} data-testid="sector-listen-transcript">
          <span className="font-semibold">{browserVoice ? t('sectorFlow.transcriptBrowser') : t('voicePanel.transcript')}: </span>{transcript}
        </p>
      ) : null}
    </div>
  );
}
