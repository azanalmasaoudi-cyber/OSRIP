import { CircleHelp, PhoneOff, X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Link, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useVoiceStatus } from '@/api/assistant';
import { useAssistantUi } from '@/components/assistant/AssistantContext';
import { AssistantAvatar, ORB_STATE_KEY } from '@/components/assistant/AssistantAvatar';
import { AssistantChat } from '@/components/assistant/AssistantPanel';
import { PersonaPicker, usePersona } from '@/components/assistant/persona';
import { BrandMark } from '@/components/brand/BrandMark';
import { Button } from '@/components/ui/button';
import { recordingSupported } from '@/lib/recorder';
import { recognitionSupported } from '@/lib/speech';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * Talk: one centred column (at most 900px) for the chosen persona, Al Mulhim or Ilham: the name
 * and live state, a compact still portrait, the persona choice, then the conversation with its
 * message box, Send and Speak. Only the message list scrolls (on phones, the conversation as
 * one column with the message box pinned), so there are no nested scrollbars. The camera is
 * never requested; the microphone only when Speak is pressed. Ending the call (or leaving the
 * page) stops the microphone, any request for speech and any playback.
 *
 * Live avatar mode (a real-time call with a lip-synchronised avatar) is not available, so this
 * is push-to-talk with a still portrait, or text only where no speech is available
 * (`data-mode`). The setup notes for that, and the voice explanations, are in Settings
 * (services and help), linked from the header, not on this page.
 */
export function TalkPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const navigate = useNavigate();
  const to = usePreservedSearch();
  const ui = useAssistantUi();
  const { persona } = usePersona();
  const name = persona.name[language];
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
  // Which fallback this is: speech in and out (server or browser), or text only.
  const serverSpeech = Boolean(voiceStatus.data?.configured);
  const canTalk = (serverSpeech && recordingSupported()) || recognitionSupported();
  const mode = canTalk ? 'push_to_talk' : 'text_only';
  const voice = serverSpeech ? voiceStatus.data?.personas.find((p) => p.code === persona.code)?.voices[language] : undefined;

  // Portalled to <body>: the route transition's transform would otherwise contain a fixed layer.
  return createPortal(
    <div className="fixed inset-0 z-40 flex flex-col bg-background" data-testid="talk-workspace" data-persona={persona.code}
      data-mode={mode} data-voice={voice}>
      <header className="on-nav flex items-center gap-2 bg-nav px-3 py-2 text-nav-foreground sm:px-4 short:py-1">
        <BrandMark className="size-7" />
        <span className="text-sm font-semibold" aria-hidden="true">OSRIP</span>
        <div className="ms-auto flex items-center gap-1.5">
          <Link to={to('/settings')} data-testid="talk-help" title={t('talk.help')}
            className="inline-flex size-9 items-center justify-center rounded-md hover:bg-nav-active">
            <CircleHelp aria-hidden="true" className="size-5" /><span className="sr-only">{t('talk.help')}</span>
          </Link>
          <Button type="button" size="sm" onClick={end} data-testid="talk-end"
            className="bg-destructive text-white hover:bg-destructive/90">
            <PhoneOff aria-hidden="true" />{t('talk.end')}
          </Button>
          <button type="button" onClick={close} data-testid="talk-close"
            className="inline-flex size-9 items-center justify-center rounded-md hover:bg-nav-active">
            <X aria-hidden="true" className="size-5" /><span className="sr-only">{t('talk.close')}</span>
          </button>
        </div>
      </header>

      {/* Short screens (up to 560px tall, e.g. a phone in landscape): no large portrait (the
          persona choice still shows both faces), name and choice on one row, and the conversation
          keeps at least 14rem; if even that does not fit, this column scrolls so the message box
          can always be reached. */}
      <main className="mx-auto flex min-h-0 w-full max-w-[900px] flex-1 flex-col gap-3 px-3 py-3 sm:px-4 sm:py-4 short:gap-2 short:overflow-y-auto short:py-2" data-testid="talk-column">
        <section aria-labelledby="talk-heading" className="flex shrink-0 flex-col items-center gap-2 text-center short:flex-row short:flex-wrap short:justify-center short:gap-x-4" data-testid="talk-identity">
          <div className="flex flex-wrap items-baseline justify-center gap-x-2">
            <h1 id="talk-heading" ref={headingRef} tabIndex={-1} className="text-xl font-semibold outline-none sm:text-2xl" data-testid="talk-persona-name">
              <span className="sr-only">{t('talk.title', { name })}</span><span aria-hidden="true">{name}</span>
            </h1>
            <p className="text-xs font-medium text-muted-foreground" role="status" data-testid="talk-state" data-state={ui.state}>
              <span className="sr-only">{name} · </span>{t(ORB_STATE_KEY[ui.state])}
            </p>
          </div>
          {/* Width sets the height (the portrait keeps its 3:4 shape): 120–160px tall on phones,
              180–220px from the small breakpoint up. */}
          <div className="[--talk-portrait:clamp(90px,14vh,120px)] sm:[--talk-portrait:clamp(135px,16vh,165px)] short:hidden" data-testid="talk-figure">
            <AssistantAvatar state={ui.state} size="var(--talk-portrait)" shape="figure" decorative={false} />
          </div>
          <PersonaPicker compact />
        </section>
        <section aria-label={t('talk.transcript')} data-testid="talk-sheet"
          className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-card short:min-h-56">
          <AssistantChat showIdentity={false} variant="talk" onClose={end} />
        </section>
      </main>
    </div>,
    document.body,
  );
}
