import { ArrowUpRight, Columns3, Target } from 'lucide-react';
import { useReducedMotion } from 'motion/react';
import { useEffect, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';

import { PersonaImage } from '@/components/assistant/PersonaImage';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * The opening introduction, after the owner's design (docs/OSRIP_Intro_Single_File.html): the
 * two AI assistants, Al Mulhim and Ilham, arrive from the sides and the OSRIP sign is set down
 * between them; then the platform's name in both languages, its three resources (electricity,
 * water, trade) and its three goals, with Explore and Skip. The images are the ones embedded in
 * that file (tools/build_intro_images.py, public/images/intro/).
 *
 * - Shown once per browser session, on the home page only (AppShell): a direct link to any other
 *   page is never interrupted. Settings can turn the automatic showing off in this browser, and
 *   the footer and Settings replay it.
 * - Explore and Skip both enter the dashboard (the Overview); Escape only closes. Nothing is sent
 *   to the server.
 * - A native modal <dialog>: the page behind keeps loading its data but is inert; focus starts on
 *   Explore and returns to where it was. Both buttons work at once.
 * - Reduced motion or a low-power device: the final frame, without movement. A portrait that
 *   cannot load becomes a neutral "AI" badge; everything else works. No sound. Light and dark
 *   themes.
 */

/** sessionStorage: shown in this browser session. */
const SESSION_KEY = 'osrip.entrance';
const SHOWN = 'shown';
/** localStorage: the person turned the automatic showing off in this browser (Settings). */
const AUTOPLAY_KEY = 'osrip.intro.autoplay';

export type EntranceAction = 'explore' | 'skip' | 'dismiss';

// The approved names and goals, always shown in both languages.
const NAME = { en: 'Oman Smart Resource Intelligence Platform', ar: 'منصة عُمان الذكية لمعلومات الموارد' };
const GOALS = [
  { icon: Target, en: 'Understand Oman’s resources', ar: 'افهم موارد عُمان' },
  { icon: Columns3, en: 'Analyse reliable data', ar: 'حلّل البيانات الموثوقة' },
  { icon: ArrowUpRight, en: 'Support informed decisions', ar: 'ادعم القرار بالمعلومة' },
] as const;
const SECTORS = [
  { id: 'electricity', label: 'intro.electricity', alt: 'intro.imageElectricity' },
  { id: 'water', label: 'intro.water', alt: 'intro.imageWater' },
  { id: 'trade', label: 'intro.trade', alt: 'intro.imageTrade' },
] as const;
const PORTRAIT = { width: 600, height: 720 } as const;
const SECTOR = { width: 600, height: 400 } as const;

export type SceneFallback = 'none' | 'reduced-motion' | 'low-power';

/** Whether the home page should open with the introduction now: not yet shown in this browser
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

/** The Settings switch: open the home page with the introduction once per session (default). */
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

/** Data saver, or a device with very few cores or little memory: show the final frame. */
function lowPowerDevice(): boolean {
  const nav = navigator as Navigator & { connection?: { saveData?: boolean }; deviceMemory?: number };
  if (nav.connection?.saveData) return true;
  if (nav.hardwareConcurrency > 0 && nav.hardwareConcurrency <= 2) return true;
  return typeof nav.deviceMemory === 'number' && nav.deviceMemory <= 2;
}

export function Entrance({ open, onClose }: { open: boolean; onClose: (action: EntranceAction) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const exploreRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // Counted as shown as soon as it opens, so a reload never shows it again in this session.
      markShown();
      returnTo.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
      dialog.scrollTop = 0;
      // Focus without scrolling, so a phone starts at the top of the scene.
      exploreRef.current?.focus({ preventScroll: true });
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const close = (action: EntranceAction) => {
    onClose(action);
    // Escape: back to where the visitor was, as the browser would for a dialog (on a first visit,
    // the page's main content). Explore and Skip open the dashboard, which takes the focus.
    const previous = returnTo.current;
    const target = action === 'dismiss' && previous && previous !== document.body && document.contains(previous)
      ? previous : document.getElementById('main');
    window.requestAnimationFrame(() => target?.focus({ preventScroll: true }));
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby="entrance-title"
      aria-describedby="entrance-goals"
      onCancel={(event) => { event.preventDefault(); close('dismiss'); }}
      className="intro-dialog m-0 h-dvh max-h-none w-screen max-w-none overflow-x-hidden overflow-y-auto p-0"
      data-testid="entrance"
    >
      {/* Mounted per showing, so a replay starts the scene from the beginning. */}
      {open ? <EntranceBody exploreRef={exploreRef} onClose={close} /> : null}
    </dialog>
  );
}

function EntranceBody({ exploreRef, onClose }: { exploreRef: RefObject<HTMLButtonElement | null>; onClose: (action: EntranceAction) => void }) {
  const { t, i18n } = useTranslation();
  const language = useAppLanguage();
  const other = language === 'ar' ? 'en' : 'ar';
  const tOther = i18n.getFixedT(other);
  const reduce = useReducedMotion();
  const [stillFrame] = useState<SceneFallback>(() => (reduce ? 'reduced-motion' : lowPowerDevice() ? 'low-power' : 'none'));
  const names = language === 'ar' ? (['ar', 'en'] as const) : (['en', 'ar'] as const);

  return (
    <div className="intro relative flex min-h-dvh flex-col overflow-hidden" data-testid="entrance-body" data-revealed="true"
      data-mode={stillFrame === 'none' ? 'play' : 'static'} data-fallback={stillFrame}>
      <div aria-hidden="true" className="intro-grid" />
      <h2 id="entrance-title" className="sr-only" lang="en" dir="ltr">OSRIP</h2>

      <div className="relative z-10 flex items-center justify-between gap-4 px-5 pt-5 sm:px-[5vw]" dir="ltr">
        <div aria-hidden="true">
          <p className="text-lg font-bold tracking-[0.22em]">OSRIP<span className="intro-gold">.</span></p>
          <p className="intro-muted mt-1 text-[10px] tracking-[0.15em] uppercase">{t('intro.tagline')}</p>
        </div>
        <button type="button" onClick={() => onClose('skip')} data-testid="entrance-skip"
          className="intro-skip min-h-11 rounded-full px-5 py-2 text-sm">
          {t('entrance.skip')}<span lang={other} className="intro-muted"> · {tOther('entrance.skip')}</span>
        </button>
      </div>

      <div className="intro-stage" dir="ltr" data-testid="entrance-stage" role="img"
        aria-label={`${t('intro.portraitMulhim')}. ${t('intro.portraitIlham')}. OSRIP.`}>
        <div className="intro-halo" />
        <div className="intro-floor" />
        <figure className="intro-person intro-person-male" data-testid="entrance-portrait-mulhim">
          <PersonaImage src="/images/intro/mulhim.jpg" alt="" width={PORTRAIT.width} height={PORTRAIT.height} fetchPriority="high" draggable={false} />
        </figure>
        <figure className="intro-person intro-person-female" data-testid="entrance-portrait-ilham">
          <PersonaImage src="/images/intro/ilham.jpg" alt="" width={PORTRAIT.width} height={PORTRAIT.height} fetchPriority="high" draggable={false} />
        </figure>
        <div className="intro-sign" data-testid="entrance-sign">
          <strong data-testid="entrance-sign-text">OSRIP</strong>
          <small>{t('intro.sign')}</small>
        </div>
        <span className="intro-name intro-name-male" aria-hidden="true">المُلْهِم · Al Mulhim</span>
        <span className="intro-name intro-name-female" aria-hidden="true">إلهام · Ilham</span>
      </div>

      <div className="relative z-10 mx-auto mt-4 mb-9 flex w-[min(52rem,92%)] flex-col items-center gap-5 text-center">
        <div className="intro-reveal flex flex-col items-center gap-1" data-testid="entrance-names">
          <p className="intro-gold mb-2 text-xs">{t('intro.eyebrow')}</p>
          {names.map((code) => (
            <p key={code} lang={code} dir={code === 'ar' ? 'rtl' : 'ltr'} data-testid={`entrance-name-${code}`}
              className={code === language ? 'text-xl font-medium sm:text-3xl' : 'intro-muted text-sm sm:text-base'}>
              {NAME[code]}
            </p>
          ))}
        </div>

        <div className="w-full">
          <p className="intro-reveal mb-3 text-sm font-medium">
            {t('intro.connected')}<span lang={other} className="intro-muted"> · {tOther('intro.connected')}</span>
          </p>
          <ul className="grid grid-cols-3 gap-2 sm:gap-3.5" data-testid="entrance-sectors">
            {SECTORS.map((s) => (
              <li key={s.id} className="min-w-0">
                <figure className="intro-sector" data-testid="entrance-sector" data-sector={s.id}>
                  <img src={`/images/intro/${s.id}.jpg`} width={SECTOR.width} height={SECTOR.height} alt={t(s.alt)}
                    decoding="async" draggable={false} />
                  <figcaption>
                    <span className="block text-xs font-medium sm:text-sm">{t(s.label)}</span>
                    <span lang={other} className="intro-muted block text-[10px] sm:text-[11px]">{tOther(s.label)}</span>
                  </figcaption>
                </figure>
              </li>
            ))}
          </ul>
        </div>

        <ul id="entrance-goals" className="intro-reveal grid w-full grid-cols-3 gap-2 sm:gap-3" data-testid="entrance-goals">
          {GOALS.map((goal) => {
            const Icon = goal.icon;
            return (
              <li key={goal.en} className="intro-goal flex flex-col items-center gap-1.5 rounded-[14px] px-1.5 py-3 sm:px-2.5 sm:py-4">
                <Icon aria-hidden="true" className="intro-gold size-5" />
                <span className="text-xs leading-relaxed font-medium sm:text-sm" lang={language} dir={language === 'ar' ? 'rtl' : 'ltr'}>{goal[language]}</span>
                <span className="intro-muted text-[10px] leading-relaxed sm:text-[11px]" lang={other} dir={other === 'ar' ? 'rtl' : 'ltr'}>{goal[other]}</span>
              </li>
            );
          })}
        </ul>

        {/* Available from the first moment: nobody has to wait for the scene. */}
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button ref={exploreRef} type="button" onClick={() => onClose('explore')} data-testid="entrance-explore"
            className="intro-explore inline-flex min-h-11 items-center gap-2 rounded-full px-7 py-3 font-bold">
            {t('entrance.explore')}<span lang={other} className="font-medium"> · {tOther('entrance.explore')}</span>
          </button>
        </div>
        <p className="intro-muted max-w-xl text-[10px] leading-relaxed">
          {t('intro.note')}<br />{t('app.identityNote')}
        </p>
      </div>
    </div>
  );
}
