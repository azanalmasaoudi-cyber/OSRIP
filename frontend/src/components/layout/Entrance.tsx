import { useEffect, useRef, type RefObject } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { WelcomeFooter, WelcomeStage, WelcomeTopBar } from './WelcomeChrome';
import { usePersona } from '@/components/assistant/persona';
import { PersonaImage } from '@/components/assistant/PersonaImage';
import { SectorArtwork } from '@/components/brand/SectorArtwork';
import type { Sector } from '@/components/brand/SectorIllustration';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * The welcome screen (the owner's design, welcome.css): the platform's name in both languages,
 * Enter platform and Skip introduction, and the four sectors as image cards that open their
 * pages. It stays until the visitor chooses; nothing closes it on a timer.
 *
 * - Shown once per browser session, on the home page only (AppShell): a direct link to any other
 *   page, sign-in included, is never interrupted. Settings can turn the automatic showing off in
 *   this browser; Settings, the footer and "Back to introduction" on the sign-in page show it again.
 * - Enter platform, Skip introduction and Escape close it onto the home page (guests stay guests:
 *   nobody is sent to sign in); a sector card opens that sector. Focus goes to the main content.
 * - A native modal <dialog>: the page behind keeps loading its data. The only movement is a hover
 *   lift, and none under reduced motion. Nothing is sent to the server.
 */

/** sessionStorage: shown in this browser session. */
const SESSION_KEY = 'osrip.entrance';
const SHOWN = 'shown';
/** localStorage: the person turned the automatic showing off in this browser (Settings). */
const AUTOPLAY_KEY = 'osrip.intro.autoplay';

export type EntranceAction = 'enter' | 'skip' | 'dismiss' | 'sector';

const SECTORS: readonly { sector: Sector; path: string }[] = [
  { sector: 'electricity', path: '/energy/electricity' },
  { sector: 'water', path: '/energy/water' },
  { sector: 'food', path: '/food-security' },
  { sector: 'trade', path: '/trade' },
];

/** Whether the home page should open with the welcome now: not yet shown in this browser
 * session, and the automatic showing not turned off. Storage blocked: never (nobody is trapped
 * behind an overlay that cannot be remembered). */
export function introDue(): boolean {
  try {
    return window.sessionStorage.getItem(SESSION_KEY) !== SHOWN && window.localStorage.getItem(AUTOPLAY_KEY) !== 'off';
  } catch {
    return false;
  }
}

function markShown(): void {
  try {
    window.sessionStorage.setItem(SESSION_KEY, SHOWN);
  } catch {
    // Storage blocked: introDue() is already false.
  }
}

/** The Settings switch: open the home page with the welcome once per session (default). */
export function introAutoplay(): boolean {
  try {
    return window.localStorage.getItem(AUTOPLAY_KEY) !== 'off';
  } catch {
    return false;
  }
}

export function setIntroAutoplay(on: boolean): void {
  try {
    if (on) window.localStorage.removeItem(AUTOPLAY_KEY);
    else window.localStorage.setItem(AUTOPLAY_KEY, 'off');
  } catch {
    // Storage blocked: nothing to remember.
  }
}

export function Entrance({ open, onClose }: { open: boolean; onClose: (action: EntranceAction) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const firstRef = useRef<HTMLButtonElement>(null);
  const focusAfter = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // Counted as shown as soon as it opens, so a reload never shows it again in this session.
      markShown();
      returnTo.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
      dialog.scrollTop = 0;
      firstRef.current?.focus({ preventScroll: true });
    }
    if (!open && dialog.open) {
      dialog.close();
      // After the dialog's own focus restoration, so the chosen place keeps the focus.
      focusAfter.current?.focus({ preventScroll: true });
      focusAfter.current = null;
    }
  }, [open]);

  const close = (action: EntranceAction) => {
    // Back where the visitor was when it was shown again (a Settings or footer button), otherwise
    // the page's main content (a sector card's page gets its own focus when it opens).
    const previous = returnTo.current;
    focusAfter.current = action === 'sector' ? null
      : previous && previous !== document.body && document.contains(previous) ? previous : document.getElementById('main');
    onClose(action);
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby="entrance-title"
      onCancel={(event) => { event.preventDefault(); close('dismiss'); }}
      className="welcome-dialog m-0 h-dvh max-h-none w-screen max-w-none overflow-x-hidden overflow-y-auto p-0"
      data-testid="entrance"
    >
      {/* Mounted per showing, so a replay starts from the top. */}
      {open ? <WelcomeBody firstRef={firstRef} onClose={close} /> : null}
    </dialog>
  );
}

function WelcomeBody({ firstRef, onClose }: { firstRef: RefObject<HTMLButtonElement | null>; onClose: (action: EntranceAction) => void }) {
  const { t, i18n } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const { persona } = usePersona();
  // The name in the other language as well, as on the screen's design.
  const other = language === 'ar' ? 'en' : 'ar';
  const tOther = i18n.getFixedT(other);

  return (
    <WelcomeStage data-testid="entrance-body">
      <WelcomeTopBar onHome={() => onClose('enter')} />
      <div className="ow-frame">
        <div className="ow-welcome">
          <div className="ow-hero">
            <p className="ow-eyebrow"><span aria-hidden="true" className="ow-dot" />{t('welcome.eyebrow')}</p>
            <h2 id="entrance-title" className="ow-title" lang="en" dir="ltr" data-testid="entrance-title">OSRIP</h2>
            <p className="ow-name" data-testid="entrance-name">{t('welcome.name')}</p>
            <p className="ow-name-other" lang={other} dir={other === 'ar' ? 'rtl' : 'ltr'} data-testid="entrance-name-other">
              {tOther('welcome.name')}
            </p>
            <p className="ow-lead">{t('welcome.lead')}</p>
            <div className="ow-actions">
              <button ref={firstRef} type="button" className="ow-primary" onClick={() => onClose('enter')} data-testid="entrance-enter">
                {t('welcome.enter')}<span aria-hidden="true" className="ow-arrow">→</span>
              </button>
              <button type="button" className="ow-secondary" onClick={() => onClose('skip')} data-testid="entrance-skip">
                {t('welcome.skip')}
              </button>
            </div>
            <ul className="ow-meta">
              <li><b aria-hidden="true">✧</b>{t('welcome.meta.design')}</li>
              <li><b aria-hidden="true">◎</b>{t('welcome.meta.languages')}</li>
              <li><b aria-hidden="true">◈</b>{t('welcome.meta.domains')}</li>
            </ul>
            {/* The one AI assistant, Al Mulhim: opens the conversation. */}
            <Link to={to('/assistant')} onClick={() => onClose('sector')} className="ow-assistant" data-testid="welcome-assistant"
              data-persona={persona.code}>
              <PersonaImage src={persona.avatar.portrait} alt="" width={40} height={40} draggable={false} />
              <span className="ow-assistant-text">
                <b>{t('welcome.assistant', { name: persona.name[language] })}</b>
                <span>{t('welcome.assistantSub')}</span>
              </span>
              <span aria-hidden="true" className="ow-arrow">→</span>
            </Link>
          </div>
          <div className="ow-art">
            <section className="ow-panel" aria-labelledby="welcome-panel-title" data-testid="welcome-panel">
              <div className="ow-panel-head">
                <div>
                  <h3 id="welcome-panel-title" className="ow-panel-title">{t('welcome.panelTitle')}</h3>
                  <p className="ow-panel-sub">{t('welcome.panelSub')}</p>
                </div>
                <span className="ow-pill" lang="en" dir="ltr">OSRIP / 04</span>
              </div>
              <ul className="ow-cards">
                {SECTORS.map((s) => (
                  <li key={s.sector}>
                    <Link to={to(s.path)} onClick={() => onClose('sector')} className="ow-sector" data-testid="welcome-sector" data-sector={s.sector}>
                      <SectorArtwork sector={s.sector} eager sizes="(min-width: 790px) 290px, 46vw" />
                    </Link>
                  </li>
                ))}
              </ul>
              <div className="ow-panel-bottom">
                <span>{t('welcome.panelBottom')}</span>
                <Link to={to('/overview')} onClick={() => onClose('sector')} data-testid="welcome-explore">
                  {t('welcome.explore')} <span aria-hidden="true" className="ow-arrow">→</span>
                </Link>
              </div>
            </section>
          </div>
        </div>
      </div>
      <WelcomeFooter />
    </WelcomeStage>
  );
}
