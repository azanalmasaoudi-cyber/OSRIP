import { PhoneOff, X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useRealtimeVoiceStatus, useVoiceStatus } from '@/api/assistant';
import { adapterKind } from '@/api/config';
import { useAssistantUi } from '@/components/assistant/AssistantContext';
import { AssistantAvatar, ORB_STATE_KEY } from '@/components/assistant/AssistantAvatar';
import { AssistantChat } from '@/components/assistant/AssistantPanel';
import { PersonaPicker, usePersona } from '@/components/assistant/persona';
import { BrandMark, LatticeBackdrop } from '@/components/brand/BrandMark';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { recordingSupported } from '@/lib/recorder';
import { recognitionSupported } from '@/lib/speech';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * Talk: a full-viewport workspace with the chosen persona (Al Mulhim or Ilham) shown large,
 * the live state, the transcript and results beside it (below it, as a sheet, on phones),
 * the persona choice, language, microphone, mute, stop speaking (interrupt), End call and
 * Close. The camera is never requested; the microphone only when the mic button is pressed.
 *
 * Live avatar mode (a real-time LiveKit call with a lip-synchronised avatar) needs a LiveKit
 * project, the persona's real-time voice and avatar in the profile, and a browser client
 * package that has not been approved, so this workspace always says which fallback it is in:
 * push-to-talk with a still portrait (speak, check the words, send) or text only. Ending the
 * call (or leaving the page) stops the microphone, any request for speech and any playback.
 */
export function TalkPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const navigate = useNavigate();
  const to = usePreservedSearch();
  const ui = useAssistantUi();
  const { persona } = usePersona();
  const name = persona.name[language];
  const realtime = useRealtimeVoiceStatus();
  const voiceStatus = useVoiceStatus();
  const headingRef = useRef<HTMLHeadingElement>(null);
  useDocumentTitle(t('talk.title', { name }));
  useEffect(() => {
    // The app behind the workspace is inert and does not scroll while the call is open.
    const root = document.getElementById('root');
    root?.setAttribute('inert', '');
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    headingRef.current?.focus();
    return () => {
      root?.removeAttribute('inert');
      document.body.style.overflow = overflow;
    };
  }, []);

  const end = () => void navigate(to('/assistant'));
  const close = () => {
    if (window.history.length > 1) void navigate(-1);
    else end();
  };
  const status = realtime.data;
  const realtimeReady = Boolean(status?.configured && status.agent_sdk_installed);
  // Which fallback this is: speech in and out (server or browser), or text only.
  const serverSpeech = Boolean(voiceStatus.data?.configured);
  const canTalk = (serverSpeech && recordingSupported()) || recognitionSupported();
  const mode = canTalk ? 'push_to_talk' : 'text_only';
  const voice = voiceStatus.data?.personas.find((p) => p.code === persona.code)?.voices[language];

  // Portalled to <body>: the route transition's transform would otherwise contain a fixed layer.
  return createPortal(
    <div className="fixed inset-0 z-40 flex flex-col bg-background" data-testid="talk-workspace" data-persona={persona.code}
      data-mode={mode}>
      <header className="on-nav flex flex-wrap items-center gap-3 bg-nav px-4 py-3 text-nav-foreground">
        <BrandMark className="size-8" />
        <h1 ref={headingRef} tabIndex={-1} className="text-lg font-semibold outline-none">{t('talk.title', { name })}</h1>
        <Badge variant="sand" data-testid="talk-mode" data-mode={mode}>
          {mode === 'push_to_talk' ? t('talk.modePushToTalk') : t('talk.modeTextOnly')}
        </Badge>
        <div className="ms-auto flex items-center gap-2">
          <Button type="button" size="sm" onClick={end} data-testid="talk-end"
            className="bg-destructive text-white hover:bg-destructive/90">
            <PhoneOff aria-hidden="true" />{t('talk.end')}
          </Button>
          <button type="button" onClick={close} data-testid="talk-close"
            className="inline-flex size-10 items-center justify-center rounded-md hover:bg-nav-active">
            <X aria-hidden="true" className="size-5" /><span className="sr-only">{t('talk.close')}</span>
          </button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_minmax(24rem,32rem)] lg:grid-rows-1">
        <section aria-labelledby="talk-portrait" className="relative flex flex-col items-center justify-center gap-3 overflow-y-auto px-4 py-4 text-center lg:py-8">
          <LatticeBackdrop className="bg-sand/10" />
          <h2 id="talk-portrait" className="relative text-2xl font-semibold max-lg:sr-only" data-testid="talk-persona-name">{name}</h2>
          <div className="relative max-lg:hidden" data-testid="talk-figure">
            <AssistantAvatar state={ui.state} size="min(19rem, 32vh)" shape="figure" decorative={false} />
          </div>
          <div className="relative flex items-center gap-3 lg:hidden">
            <AssistantAvatar state={ui.state} size="5rem" decorative={false} />
            <span className="text-lg font-semibold" aria-hidden="true">{name}</span>
          </div>
          <p className="relative text-sm font-medium" role="status" data-testid="talk-state" data-state={ui.state}>
            {name} · {t(ORB_STATE_KEY[ui.state])}
          </p>
          <PersonaPicker compact className="relative" />
          {voice && serverSpeech ? (
            <p className="relative text-xs text-muted-foreground" data-testid="talk-voice" dir="ltr">{t('talk.voiceLine', { voice })}</p>
          ) : null}
          {/* Phones: the mode is in the header badge; the explanation needs the larger screen. */}
          <div className="relative max-w-md rounded-md border border-sand/60 bg-sand-subtle/70 p-3 text-start text-xs max-lg:hidden" data-testid="talk-mode-note">
            <p>{mode === 'push_to_talk' ? t('talk.fallbackNote', { name }) : t('talk.textOnlyNote')}</p>
            <p className="mt-1 text-muted-foreground" data-testid="talk-portrait-note">{t('talk.portraitNote')}</p>
          </div>
          {adapterKind === 'http' && status ? (
            <div className="relative max-w-md rounded-md border border-border bg-card/90 p-3 text-start text-xs max-lg:hidden" data-testid="talk-realtime">
              <p>{language === 'ar' ? status.note.ar : status.note.en}</p>
              {realtimeReady ? <p className="mt-1">{t('talk.clientPending')}</p> : null}
              {status.missing.length ? (
                <details className="mt-1">
                  <summary className="cursor-pointer text-muted-foreground">{t('talk.missing')}</summary>
                  <ul className="mt-1 list-disc ps-4 font-mono" dir="ltr">{status.missing.map((m) => <li key={m}>{m}</li>)}</ul>
                </details>
              ) : null}
            </div>
          ) : null}
        </section>
        <section aria-label={t('talk.transcript')}
          className="flex min-h-0 flex-col border-border bg-card max-lg:rounded-t-xl max-lg:border-t max-lg:shadow-raised lg:border-s"
          data-testid="talk-sheet">
          <AssistantChat showIdentity={false} onClose={end} />
        </section>
      </div>
    </div>,
    document.body,
  );
}
