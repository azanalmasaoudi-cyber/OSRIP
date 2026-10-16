import { ArrowUpRight, Columns3, Target } from 'lucide-react';
import { useReducedMotion } from 'motion/react';
import { useEffect, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';

import { PersonaImage } from '@/components/assistant/PersonaImage';
import { usePersona } from '@/components/assistant/persona';
import { EditorialImage } from '@/components/brand/EditorialImage';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * First-visit introduction, after the owner's design (docs/OSRIP_Intro_Single_File.html): the
 * two AI assistants, Al Mulhim and Ilham, arrive from the sides and the OSRIP sign is set down
 * between them; then the platform's name in both languages, its three resources (electricity,
 * water, trade) and its three goals, with Explore and Skip.
 *
 * - Shown once per browser on the home page (remembered locally, nothing sent to the server);
 *   replayable from Settings (Account page) and the footer.
 * - A native modal <dialog>: the page behind keeps loading its data but is inert; focus starts
 *   on Explore and returns to where it was; Escape skips. Explore and Skip work at once.
 * - Reduced motion or a low-power device: the final frame, without movement. A portrait that
 *   cannot load becomes a neutral "AI" badge; everything else works. No sound.
 */

const STORAGE_KEY = 'osrip.entrance';
const SEEN = 'seen-1';

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

export type SceneFallback = 'none' | 'reduced-motion' | 'low-power';

export function entranceSeen(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === SEEN;
  } catch {
    return true; // storage blocked: never trap the visitor behind an overlay that cannot be remembered
  }
}

function markSeen(): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, SEEN);
  } catch {
    // Private mode: the entrance simply shows again next time.
  }
}

/** Data saver, or a device with very few cores or little memory: show the final frame. */
function lowPowerDevice(): boolean {
  const nav = navigator as Navigator & { connection?: { saveData?: boolean }; deviceMemory?: number };
  if (nav.connection?.saveData) return true;
  if (nav.hardwareConcurrency > 0 && nav.hardwareConcurrency <= 2) return true;
  return typeof nav.deviceMemory === 'number' && nav.deviceMemory <= 2;
}

export function Entrance({ open, onClose }: { open: boolean; onClose: (explore: boolean) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const exploreRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      returnTo.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
      dialog.scrollTop = 0;
      // Focus without scrolling, so a phone starts at the top of the scene.
      exploreRef.current?.focus({ preventScroll: true });
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const close = (explore: boolean) => {
    markSeen();
    onClose(explore);
    // Back to where the visitor was, as the browser would for a dialog; on a first visit (focus
    // was nowhere in particular) to the page's main content.
    const previous = returnTo.current;
    const target = previous && previous !== document.body && document.contains(previous) ? previous : document.getElementById('main');
    window.requestAnimationFrame(() => target?.focus({ preventScroll: true }));
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby="entrance-title"
      aria-describedby="entrance-goals"
      onCancel={(event) => { event.preventDefault(); close(false); }}
      className="on-nav m-0 h-dvh max-h-none w-screen max-w-none overflow-x-hidden overflow-y-auto bg-[#062426] p-0 text-[#f7eedb] backdrop:bg-[#062426]"
      data-testid="entrance"
    >
      {/* Mounted per showing, so a replay starts the scene from the beginning. */}
      {open ? <EntranceBody exploreRef={exploreRef} onClose={close} /> : null}
    </dialog>
  );
}

function EntranceBody({ exploreRef, onClose }: { exploreRef: RefObject<HTMLButtonElement | null>; onClose: (explore: boolean) => void }) {
  const { t, i18n } = useTranslation();
  const language = useAppLanguage();
  const other = language === 'ar' ? 'en' : 'ar';
  const tOther = i18n.getFixedT(other);
  const reduce = useReducedMotion();
  const [stillFrame] = useState<SceneFallback>(() => (reduce ? 'reduced-motion' : lowPowerDevice() ? 'low-power' : 'none'));
  const { personas } = usePersona();
  const mulhim = personas.find((p) => p.code === 'mulhim');
  const ilham = personas.find((p) => p.code === 'ilham');
  const names = language === 'ar' ? (['ar', 'en'] as const) : (['en', 'ar'] as const);

  return (
    <div className="intro relative flex min-h-dvh flex-col overflow-hidden" data-testid="entrance-body" data-revealed="true"
      data-mode={stillFrame === 'none' ? 'play' : 'static'} data-fallback={stillFrame}>
      <div aria-hidden="true" className="intro-grid" />
      <h2 id="entrance-title" className="sr-only" lang="en" dir="ltr">OSRIP</h2>

      <div className="relative z-10 flex items-center justify-between gap-4 px-5 pt-5 sm:px-[5vw]" dir="ltr">
        <div aria-hidden="true">
          <p className="text-lg font-bold tracking-[0.22em]">OSRIP<span className="text-[var(--intro-gold)]">.</span></p>
          <p className="mt-1 text-[10px] tracking-[0.15em] text-[var(--intro-muted)] uppercase">{t('intro.tagline')}</p>
        </div>
        <button type="button" onClick={() => onClose(false)} data-testid="entrance-skip"
          className="min-h-11 rounded-full border border-[rgb(170_198_185/0.3)] px-5 py-2 text-sm hover:bg-white/5">
          {t('entrance.skip')}<span lang={other} className="text-[var(--intro-muted)]"> · {tOther('entrance.skip')}</span>
        </button>
      </div>

      <div className="intro-stage" dir="ltr" data-testid="entrance-stage" role="img"
        aria-label={`${t('intro.portraitMulhim')}. ${t('intro.portraitIlham')}. OSRIP.`}>
        <div className="intro-halo" />
        <div className="intro-floor" />
        <figure className="intro-person intro-person-male" data-testid="entrance-portrait-mulhim">
          <PersonaImage src={mulhim?.avatar.figure ?? mulhim?.avatar.portrait} alt="" width={600} height={800} fetchPriority="high" draggable={false} />
        </figure>
        <figure className="intro-person intro-person-female" data-testid="entrance-portrait-ilham">
          <PersonaImage src={ilham?.avatar.figure ?? ilham?.avatar.portrait} alt="" width={600} height={800} fetchPriority="high" draggable={false} />
        </figure>
        <div className="intro-sign" data-testid="entrance-sign">
          <strong data-testid="entrance-sign-text">OSRIP</strong>
          <small>{t('intro.sign')}</small>
        </div>
        <span className="intro-name intro-name-male" aria-hidden="true">{mulhim ? `${mulhim.name.ar} · ${mulhim.name.en}` : null}</span>
        <span className="intro-name intro-name-female" aria-hidden="true">{ilham ? `${ilham.name.ar} · ${ilham.name.en}` : null}</span>
      </div>

      <div className="relative z-10 mx-auto mt-4 mb-9 flex w-[min(52rem,92%)] flex-col items-center gap-5 text-center">
        <div className="intro-reveal flex flex-col items-center gap-1" data-testid="entrance-names">
          <p className="mb-2 text-xs text-[var(--intro-gold)]">{t('intro.eyebrow')}</p>
          {names.map((code) => (
            <p key={code} lang={code} dir={code === 'ar' ? 'rtl' : 'ltr'} data-testid={`entrance-name-${code}`}
              className={code === language ? 'text-xl font-medium sm:text-3xl' : 'text-sm text-[var(--intro-muted)] sm:text-base'}>
              {NAME[code]}
            </p>
          ))}
        </div>

        <div className="w-full">
          <p className="intro-reveal mb-3 text-sm font-medium">
            {t('intro.connected')}<span lang={other} className="text-[var(--intro-muted)]"> · {tOther('intro.connected')}</span>
          </p>
          <ul className="grid grid-cols-3 gap-2 sm:gap-3.5" data-testid="entrance-sectors">
            {SECTORS.map((s) => (
              <li key={s.id} className="min-w-0">
                <figure className="intro-sector" data-testid="entrance-sector" data-sector={s.id}>
                  <EditorialImage id={s.id} alt={t(s.alt)} sizes="(min-width: 640px) 16rem, 30vw" eager />
                  <figcaption>
                    <span className="block text-xs font-medium sm:text-sm">{t(s.label)}</span>
                    <span lang={other} className="block text-[10px] text-[var(--intro-muted)] sm:text-[11px]">{tOther(s.label)}</span>
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
              <li key={goal.en} className="flex flex-col items-center gap-1.5 rounded-[14px] border border-[rgb(176_212_197/0.12)] bg-[rgb(196_220_195/0.03)] px-1.5 py-3 sm:px-2.5 sm:py-4">
                <Icon aria-hidden="true" className="size-5 text-[var(--intro-gold)]" />
                <span className="text-xs leading-relaxed font-medium sm:text-sm" lang={language} dir={language === 'ar' ? 'rtl' : 'ltr'}>{goal[language]}</span>
                <span className="text-[10px] leading-relaxed text-[var(--intro-muted)] sm:text-[11px]" lang={other} dir={other === 'ar' ? 'rtl' : 'ltr'}>{goal[other]}</span>
              </li>
            );
          })}
        </ul>

        {/* Available from the first moment: nobody has to wait for the scene. */}
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button ref={exploreRef} type="button" onClick={() => onClose(true)} data-testid="entrance-explore"
            className="inline-flex min-h-11 items-center gap-2 rounded-full bg-[var(--intro-cream)] px-7 py-3 font-bold text-[var(--intro-ink)] shadow-lg hover:bg-[#ffe2a8]">
            {t('entrance.explore')}<span lang={other} className="font-medium"> · {tOther('entrance.explore')}</span>
          </button>
        </div>
        <p className="max-w-xl text-[10px] leading-relaxed text-[var(--intro-muted)]">
          {t('intro.note')}<br />{t('app.identityNote')}
        </p>
      </div>
    </div>
  );
}
