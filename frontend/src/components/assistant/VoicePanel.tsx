import { Pause, Play, Square, Volume2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { testVoice, useVoiceStatus, useVoiceVoices, type VoiceCheck } from '@/api/assistant';
import { ApiRequestError } from '@/api/client';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Segmented } from '@/components/ui/segmented';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { playAudio, type Playback } from '@/lib/voicePlayer';

import { useAssistantUi } from './AssistantContext';
import { VoiceVolume } from './VoiceVolume';
import { PersonaPicker, usePersona } from './persona';

/**
 * The persona and its voices: the Azure voice configured for each language (Al Mulhim
 * ar-OM-AbdullahNeural / en-GB-RyanNeural, Ilham ar-OM-AyshaNeural / en-GB-SoniaNeural), whether
 * the speech service actually lists it, and a fixed test sentence with play, pause and stop.
 * Without the service it says so plainly; it never presents a browser voice as the Azure voice.
 * Nothing plays until the person presses Test voice, and the microphone is not involved here.
 */
function VerifiedBadge({ check }: { check: VoiceCheck | undefined }) {
  const { t } = useTranslation();
  if (!check) return null;
  return check.verified === true ? <Badge variant="verified" data-testid="voice-verified">{t('voicePanel.verified')}</Badge>
    : check.verified === false ? <Badge variant="accent" data-testid="voice-not-listed">{t('voicePanel.notListed')}</Badge>
      : <Badge variant="muted" data-testid="voice-unchecked">{t('voicePanel.unchecked')}</Badge>;
}

export function VoicePanel({ showPicker = true }: { showPicker?: boolean }) {
  const { t } = useTranslation();
  const appLanguage = useAppLanguage();
  const { persona } = usePersona();
  const status = useVoiceStatus();
  const voices = useVoiceVoices();
  const { setActivity, reportError } = useAssistantUi();
  const [language, setLanguage] = useState<'en' | 'ar'>(appLanguage);
  const [state, setState] = useState<'idle' | 'loading' | 'playing' | 'paused'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<string | null>(null);
  const playback = useRef<Playback | null>(null);
  const aborter = useRef<AbortController | null>(null);
  const configured = Boolean(status.data?.configured);
  const mine = voices.data?.personas.find((p) => p.code === persona.code);

  const stop = () => {
    aborter.current?.abort();
    playback.current?.stop();
    playback.current = null;
    setState('idle');
  };
  useEffect(() => () => {
    aborter.current?.abort();
    playback.current?.stop();
  }, []);
  useEffect(() => setActivity('speaking', state === 'playing'), [state, setActivity]);

  const play = () => {
    stop();
    setError(null);
    const controller = new AbortController();
    aborter.current = controller;
    setState('loading');
    setTranscript(null);
    testVoice(persona.code, language, controller.signal)
      .then(({ audio, transcript: words }) => {
        if (controller.signal.aborted) return;
        setTranscript(words);
        playback.current = playAudio(audio, {
          onStart: () => setState('playing'),
          onLevel: (level) => document.documentElement.style.setProperty('--assistant-voice', level.toFixed(3)),
          onEnd: () => setState('idle'),
          onError: () => { setState('idle'); setError(t('voice.notice.playback')); reportError(); },
          onPause: (paused) => setState(paused ? 'paused' : 'playing'),
        });
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setState('idle');
        const code = e instanceof ApiRequestError ? e.code : '';
        setError(code === 'speech_not_configured' ? t('voicePanel.notConfigured') : t('voicePanel.failed', { message: e instanceof Error ? e.message : String(e) }));
        reportError();
      });
  };

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border bg-card p-3" aria-labelledby="voice-panel-heading" data-testid="voice-panel"
      data-configured={configured ? 'true' : 'false'}>
      <h3 id="voice-panel-heading" className="flex items-center gap-1.5 text-sm font-semibold"><Volume2 aria-hidden="true" className="size-4" />{t('voicePanel.heading')}</h3>
      {showPicker ? <PersonaPicker compact /> : null}
      {configured ? (
        <p className="text-xs"><Badge variant="verified">{t('voicePanel.configured')}</Badge></p>
      ) : (
        <div className="rounded-md border border-dashed border-border-strong/60 p-2 text-xs" role="status" data-testid="voice-not-configured">
          <p className="font-semibold">{t('voicePanel.notConfigured')}</p>
          <p className="mt-1 text-muted-foreground">{t('voicePanel.setupShort')}</p>
        </div>
      )}
      <ul className="flex flex-col gap-1 text-xs" data-testid="voice-list">
        {(['ar', 'en'] as const).map((lang) => (
          <li key={lang} className="flex flex-wrap items-center gap-1.5" data-language={lang}>
            <span className="font-medium">{t('voicePanel.voiceFor', { language: t(`voicePanel.languages.${lang}`) })}:</span>
            <span dir="ltr" className="font-mono" data-testid={`voice-name-${lang}`}>{mine?.voices[lang].name ?? status.data?.personas.find((p) => p.code === persona.code)?.voices[lang] ?? '—'}</span>
            {configured ? <VerifiedBadge check={mine?.voices[lang]} /> : null}
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">{t('voicePanel.english')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented label={t('assistant.language')} value={language} onChange={(v) => setLanguage(v === 'ar' ? 'ar' : 'en')}
          options={[{ value: 'ar', label: 'العربية' }, { value: 'en', label: 'English' }]} testId="voice-test-language" />
        <Button type="button" size="sm" onClick={play} disabled={!configured || state === 'loading'} data-testid="voice-test">
          <Play aria-hidden="true" />{state === 'loading' ? t('voicePanel.testing') : t('voicePanel.test')}
        </Button>
        {state === 'playing' ? (
          <Button type="button" size="sm" variant="outline" onClick={() => playback.current?.pause()} data-testid="voice-test-pause">
            <Pause aria-hidden="true" />{t('voicePanel.pause')}
          </Button>
        ) : null}
        {state === 'paused' ? (
          <Button type="button" size="sm" variant="outline" onClick={() => playback.current?.resume()} data-testid="voice-test-resume">
            <Play aria-hidden="true" />{t('voicePanel.resume')}
          </Button>
        ) : null}
        {state === 'playing' || state === 'paused' || state === 'loading' ? (
          <Button type="button" size="sm" variant="ghost" onClick={stop} data-testid="voice-test-stop">
            <Square aria-hidden="true" />{t('voicePanel.stop')}
          </Button>
        ) : null}
        <VoiceVolume />
      </div>
      <p className="text-xs" role="status" data-testid="voice-test-state" data-state={state}>{error ? <span className="text-destructive">{error}</span> : null}</p>
      {transcript ? (
        <p className="rounded-md bg-muted/60 p-2 text-xs" dir="auto" lang={language} data-testid="voice-transcript">
          <span className="font-semibold">{t('voicePanel.transcript')}: </span>{transcript}
        </p>
      ) : null}
      <ul className="flex list-disc flex-col gap-0.5 ps-4 text-xs text-muted-foreground">
        <li>{t('voicePanel.microphone')}</li>
        <li>{t('voicePanel.written')}</li>
        <li>{t('voicePanel.portrait')}</li>
      </ul>
    </section>
  );
}
