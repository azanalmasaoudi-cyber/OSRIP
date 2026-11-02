import { useReducedMotion } from 'motion/react';
import { useEffect, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';

import { useAppLanguage } from '@/lib/useAppLanguage';
import './opening.css';

/**
 * The opening: about three seconds of the platform's name on a deep navy and emerald field.
 * The letters of OSRIP rise into place from depth, a single copper-gold light passes across
 * them, the full name follows in English and Arabic, and the scene fades into the application.
 * Drawn with CSS only (no video, no images, no sound).
 *
 * - Shown once per browser session, on the home page only (AppShell): a direct link to any other
 *   page, sign-in included, is never interrupted. Settings can turn the automatic showing off in
 *   this browser, and Settings and the footer replay it.
 * - Skip works from the first moment and Escape closes; either way the visitor stays on the page
 *   they opened, and focus goes to its main content. Nothing is sent to the server.
 * - A native modal <dialog> for its three seconds: the page behind keeps loading its data.
 * - Reduced motion or a low-power device: a plain fade in and out, no movement.
 */

/** sessionStorage: shown in this browser session. */
const SESSION_KEY = 'osrip.entrance';
const SHOWN = 'shown';
/** localStorage: the person turned the automatic showing off in this browser (Settings). */
const AUTOPLAY_KEY = 'osrip.intro.autoplay';
/** The whole sequence, the fade into the application included (opening.css keeps the same time). */
export const OPENING_MS = 3000;
/** The plain fade for reduced motion and low-power devices. */
export const OPENING_STILL_MS = 2200;

export type EntranceAction = 'done' | 'skip' | 'dismiss';
export type SceneFallback = 'none' | 'reduced-motion' | 'low-power';

// The platform's name, always shown in both languages.
const NAME = { en: 'Oman Smart Resource Intelligence Platform', ar: 'منصة عُمان الذكية لذكاء الموارد' };
const LETTERS = ['O', 'S', 'R', 'I', 'P'] as const;

/** Whether the home page should open with the opening now: not yet shown in this browser
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

/** The Settings switch: open the home page with the opening once per session (default). */
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

/** Data saver, or a device with very few cores or little memory: the plain fade. */
function lowPowerDevice(): boolean {
  const nav = navigator as Navigator & { connection?: { saveData?: boolean }; deviceMemory?: number };
  if (nav.connection?.saveData) return true;
  if (nav.hardwareConcurrency > 0 && nav.hardwareConcurrency <= 2) return true;
  return typeof nav.deviceMemory === 'number' && nav.deviceMemory <= 2;
}

export function Entrance({ open, onClose }: { open: boolean; onClose: (action: EntranceAction) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const skipRef = useRef<HTMLButtonElement>(null);
  const focusAfter = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // Counted as shown as soon as it opens, so a reload never shows it again in this session.
      markShown();
      returnTo.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
      skipRef.current?.focus({ preventScroll: true });
    }
    if (!open && dialog.open) {
      dialog.close();
      // After the dialog's own focus restoration, so the chosen place keeps the focus.
      focusAfter.current?.focus({ preventScroll: true });
      focusAfter.current = null;
    }
  }, [open]);

  const close = (action: EntranceAction) => {
    // Back where the visitor was when it was replayed (a Settings or footer button), otherwise
    // the page's main content.
    const previous = returnTo.current;
    focusAfter.current = previous && previous !== document.body && document.contains(previous)
      ? previous : document.getElementById('main');
    onClose(action);
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby="entrance-title"
      onCancel={(event) => { event.preventDefault(); close('dismiss'); }}
      className="opening-dialog m-0 h-dvh max-h-none w-screen max-w-none overflow-hidden p-0"
      data-testid="entrance"
    >
      {/* Mounted per showing, so a replay starts from the beginning. */}
      {open ? <OpeningBody skipRef={skipRef} onClose={close} /> : null}
    </dialog>
  );
}

function OpeningBody({ skipRef, onClose }: { skipRef: RefObject<HTMLButtonElement | null>; onClose: (action: EntranceAction) => void }) {
  const { t, i18n } = useTranslation();
  const language = useAppLanguage();
  const other = language === 'ar' ? 'en' : 'ar';
  const tOther = i18n.getFixedT(other);
  const reduce = useReducedMotion();
  const [still] = useState<SceneFallback>(() => (reduce ? 'reduced-motion' : lowPowerDevice() ? 'low-power' : 'none'));
  const finish = useRef(onClose);
  useEffect(() => {
    finish.current = onClose;
  });

  useEffect(() => {
    const timer = window.setTimeout(() => finish.current('done'), still === 'none' ? OPENING_MS : OPENING_STILL_MS);
    return () => window.clearTimeout(timer);
  }, [still]);

  return (
    <div className="opening" data-testid="entrance-body" data-mode={still === 'none' ? 'play' : 'static'} data-fallback={still}>
      <div aria-hidden="true" className="opening-light" />
      <button ref={skipRef} type="button" onClick={() => onClose('skip')} data-testid="entrance-skip" className="opening-skip">
        {t('entrance.skip')}<span lang={other} className="opening-skip-other"> · {tOther('entrance.skip')}</span>
      </button>
      <div className="opening-centre">
        <h2 id="entrance-title" className="opening-mark" lang="en" dir="ltr" aria-label="OSRIP" data-testid="entrance-title">
          {LETTERS.map((letter, i) => (
            <span key={letter} aria-hidden="true" className="opening-letter" style={{ '--i': i } as React.CSSProperties}>{letter}</span>
          ))}
          <span aria-hidden="true" className="opening-sweep" />
        </h2>
        <span aria-hidden="true" className="opening-rule" />
        <p className="opening-name-en" lang="en" dir="ltr" data-testid="entrance-name-en">{NAME.en}</p>
        <p className="opening-name-ar" lang="ar" dir="rtl" data-testid="entrance-name-ar">{NAME.ar}</p>
      </div>
    </div>
  );
}
