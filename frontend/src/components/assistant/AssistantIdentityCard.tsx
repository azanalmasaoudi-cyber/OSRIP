import { CircleHelp, Play, Settings2, Square, Volume2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useAssistantStatus, useVoiceStatus } from '@/api/assistant';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { clipBlob, useIntroClip } from '@/lib/introClips';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { playAudio, type Playback } from '@/lib/voicePlayer';
import type { LiveStudyState } from '@/state/liveStudy';
import { usePreservedSearch } from '@/state/usePreservedSearch';

import { useAssistantUi } from './AssistantContext';
import { AssistantAvatar } from './AssistantAvatar';
import { AssistantStatusBar } from './AssistantStatusBar';
import { PersonaPicker, usePersona } from './persona';
import { VoicePanel } from './VoicePanel';

/** The answer service in a few words: working, failing (data-based reports meanwhile),
 * set up but untested, or not set up (record lookup). */
export function ServiceChip() {
  const { t } = useTranslation();
  const status = useAssistantStatus();
  if (!status.data) return null;
  const state = !status.data.configured ? 'not_configured' : (status.data.health?.state ?? 'untested');
  const variant = state === 'ok' ? 'verified' : state === 'failing' || state === 'not_configured' ? 'sand' : 'muted';
  return (
    <Badge variant={variant} data-testid="assistant-service" data-state={state}
      title={state === 'failing' && status.data.health?.category ? t(`assistant.health.category.${status.data.health.category}`, { defaultValue: '' }) : undefined}>
      {t(`assistant.health.${state}`)}
    </Badge>
  );
}

/**
 * Under the portrait, only what is needed: who answers (name, AI label, a compact state and
 * service status), the choice between Al Mulhim and Ilham, and the audio controls (stop,
 * the persona's recorded introduction when one is supplied, the voice test in a collapsed
 * panel). Explanations live in the conversation's Help panel and in Settings.
 */
export function AssistantIdentityCard({ study, analysing, failed }: {
  study: LiveStudyState | null;
  analysing: boolean;
  failed: boolean;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const ui = useAssistantUi();
  const { persona } = usePersona();
  const voice = useVoiceStatus();
  const to = usePreservedSearch();
  const clip = useIntroClip(persona.code, 'ar');
  const [intro, setIntro] = useState<'idle' | 'loading' | 'playing'>('idle');
  const [showTranscript, setShowTranscript] = useState(false);
  const playback = useRef<Playback | null>(null);
  const { setActivity } = ui;
  useEffect(() => setActivity('speaking', intro === 'playing'), [intro, setActivity]);
  useEffect(() => () => playback.current?.stop(), []);

  const playIntro = () => {
    if (!clip) return;
    setIntro('loading');
    clipBlob(clip)
      .then((blob) => {
        playback.current = playAudio(blob, {
          onStart: () => setIntro('playing'),
          onLevel: (level) => document.documentElement.style.setProperty('--assistant-voice', level.toFixed(3)),
          onEnd: () => setIntro('idle'),
          onError: () => setIntro('idle'),
        });
      })
      .catch(() => setIntro('idle'));
  };

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4" aria-labelledby="assistant-identity-name"
      data-testid="assistant-identity-card" data-persona={persona.code}>
      <div className="flex flex-wrap items-center gap-4">
        <AssistantAvatar state={ui.state} size="clamp(4rem, 9vw, 7rem)" decorative={false} />
        <div className="flex min-w-0 flex-col gap-1">
          <p className="flex flex-wrap items-center gap-2">
            <span id="assistant-identity-name" className="text-lg font-semibold" data-testid="identity-name">{persona.name[language]}</span>
            <Badge variant="accent">{t('assistant.aiAssistant')}</Badge>
          </p>
          <p className="flex flex-wrap items-center gap-2 text-xs">
            <ServiceChip />
            {voice.data ? (
              <Badge variant={voice.data.configured ? 'verified' : 'muted'} data-testid="identity-voice" data-configured={voice.data.configured ? 'true' : 'false'}>
                <Volume2 aria-hidden="true" />{voice.data.configured ? t('voicePanel.ready') : t('voicePanel.notConfigured')}
              </Badge>
            ) : null}
          </p>
        </div>
      </div>
      <PersonaPicker compact />
      <AssistantStatusBar study={study} analysing={analysing} failed={failed} />
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {clip ? (
          <>
            {intro === 'idle' ? (
              <Button type="button" size="sm" variant="outline" onClick={playIntro} data-testid="intro-play">
                <Play aria-hidden="true" />{t('voicePanel.intro.play')}
              </Button>
            ) : (
              <Button type="button" size="sm" variant="outline" onClick={() => { playback.current?.stop(); setIntro('idle'); }} data-testid="intro-stop">
                <Square aria-hidden="true" />{t('voicePanel.stop')}
              </Button>
            )}
            <Badge variant="muted" data-testid="intro-recorded">{t('voicePanel.intro.recorded')}</Badge>
            {clip.transcript ? (
              <button type="button" className="underline underline-offset-2" aria-expanded={showTranscript} onClick={() => setShowTranscript(!showTranscript)}>
                {t('voicePanel.transcript')}
              </button>
            ) : null}
          </>
        ) : null}
        <Link to={to('/settings')} className="ms-auto inline-flex items-center gap-1 rounded-md px-2 py-1 hover:bg-muted" data-testid="identity-settings">
          <Settings2 aria-hidden="true" className="size-3.5" />{t('nav.settings')}
        </Link>
      </div>
      {clip?.transcript && showTranscript ? (
        <p className="rounded-md bg-muted/60 p-2 text-xs" dir="rtl" lang="ar" data-testid="intro-transcript">{clip.transcript}</p>
      ) : null}
      <details className="text-sm" data-testid="voice-details">
        <summary className="flex cursor-pointer items-center gap-1.5 text-xs font-semibold">
          <CircleHelp aria-hidden="true" className="size-3.5" />{t('voicePanel.details')}
        </summary>
        <div className="mt-2"><VoicePanel showPicker={false} /></div>
      </details>
    </section>
  );
}
