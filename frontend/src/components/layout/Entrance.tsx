import { Compass, Lightbulb, ScanSearch } from 'lucide-react';
import { motion, useReducedMotion } from 'motion/react';
import { lazy, Suspense, useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { LatticeBackdrop } from '@/components/brand/BrandMark';
import { useAppLanguage } from '@/lib/useAppLanguage';
import type { SceneFallback } from './EntranceScene';

/**
 * First-visit entrance: a short illustrated scene (EntranceScene: an Omani man carries the
 * OSRIP sign in, sets it down in the centre and steps aside), then the platform's name in
 * English and Arabic and its three goals, with Explore and Skip.
 *
 * - Shown once per browser (remembered locally, nothing sent to the server); replayable from
 *   Settings (Account page) and the footer.
 * - A native modal <dialog>: the page behind keeps loading its data but is inert; focus starts
 *   on Explore and returns to where it was; Escape skips. Explore and Skip work at once.
 * - The scene loads on demand. Reduced motion or a low-power device: its final frame, without
 *   movement. If it cannot load, a plain sign stands in and everything else works. No sound.
 */

const STORAGE_KEY = 'osrip.entrance';
const SEEN = 'seen-1';
const SLOW_LOAD_MS = 1200; // reveal the text anyway if the scene is this slow to arrive

const EntranceScene = lazy(() => import('./EntranceScene'));

// The approved names and goals, always shown in both languages.
const NAME = { en: 'Oman Smart Resource Intelligence Platform', ar: 'منصة عُمان الذكية لمعلومات الموارد' };
const GOALS = [
  { icon: Compass, en: 'Understand Oman’s resources', ar: 'فهم موارد عُمان' },
  { icon: ScanSearch, en: 'Analyse reliable data', ar: 'تحليل البيانات الموثوقة' },
  { icon: Lightbulb, en: 'Support informed decisions', ar: 'دعم القرارات المبنية على البيانات' },
] as const;

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

/** Data saver, or a device with very few cores or little memory: show the scene's final frame. */
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
      exploreRef.current?.focus();
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
      className="on-nav m-0 h-dvh max-h-none w-screen max-w-none overflow-x-hidden overflow-y-auto bg-nav p-0 text-nav-foreground backdrop:bg-nav"
      data-testid="entrance"
    >
      {/* Mounted per showing, so a replay starts the scene from the beginning. */}
      {open ? <EntranceBody exploreRef={exploreRef} onClose={close} /> : null}
    </dialog>
  );
}

function EntranceBody({ exploreRef, onClose }: { exploreRef: RefObject<HTMLButtonElement | null>; onClose: (explore: boolean) => void }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const other = language === 'ar' ? 'en' : 'ar';
  const reduce = useReducedMotion();
  const [stillFrame] = useState<SceneFallback>(() => (reduce ? 'reduced-motion' : lowPowerDevice() ? 'low-power' : 'none'));
  const [revealedAtStart] = useState(stillFrame !== 'none');
  const [revealed, setRevealed] = useState(revealedAtStart);
  const reveal = useCallback(() => setRevealed(true), []);

  const step = (i: number) => (revealedAtStart
    ? { initial: false as const }
    : {
        initial: { opacity: 0, y: 10 },
        animate: revealed ? { opacity: 1, y: 0 } : undefined,
        transition: { duration: 0.42, delay: i * 0.12, ease: [0.2, 0, 0, 1] as const },
      });

  const names = language === 'ar' ? (['ar', 'en'] as const) : (['en', 'ar'] as const);

  return (
    <div className="relative flex min-h-dvh flex-col items-center justify-center px-4 py-6 text-center sm:px-6 sm:py-8">
      <LatticeBackdrop className="bg-nav-foreground/[0.07]" />
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-copper via-nav-ring to-copper" />
      <div className="relative flex w-full max-w-5xl flex-col items-center gap-5 sm:gap-6" data-revealed={revealed ? 'true' : 'false'}
        data-testid="entrance-body">
        <h2 id="entrance-title" className="sr-only" lang="en" dir="ltr">OSRIP</h2>

        <div className="relative aspect-[29/21] max-h-[42dvh] w-full sm:aspect-[16/7]" data-testid="entrance-stage">
          <ErrorBoundary fallback={() => <SceneUnavailable onShown={reveal} />}>
            <Suspense fallback={<SceneLoading onSlow={reveal} />}>
              <EntranceScene mode={revealed || stillFrame !== 'none' ? 'static' : 'play'} fallback={stillFrame}
                mirror={language === 'ar'} onReveal={reveal} />
            </Suspense>
          </ErrorBoundary>
        </div>

        <motion.div {...step(0)} className="flex flex-col items-center gap-1" data-testid="entrance-names">
          {names.map((code) => (
            <p key={code} lang={code} dir={code === 'ar' ? 'rtl' : 'ltr'} data-testid={`entrance-name-${code}`}
              className={code === language ? 'text-lg font-semibold sm:text-2xl' : 'text-base text-nav-foreground/90 sm:text-lg'}>
              {NAME[code]}
            </p>
          ))}
        </motion.div>

        <ul id="entrance-goals" className="grid w-full max-w-3xl gap-2 sm:grid-cols-3 sm:gap-3" data-testid="entrance-goals">
          {GOALS.map((goal, i) => {
            const Icon = goal.icon;
            return (
              <motion.li key={goal.en} {...step(i + 1)}
                className="flex items-center gap-3 rounded-lg border border-nav-foreground/15 bg-nav-active/60 px-4 py-2.5 text-start sm:flex-col sm:gap-1.5 sm:py-4 sm:text-center">
                <Icon aria-hidden="true" className="size-5 shrink-0 text-nav-accent sm:size-6" />
                <span className="flex flex-col">
                  <span className="font-medium" lang={language} dir={language === 'ar' ? 'rtl' : 'ltr'}>{goal[language]}</span>
                  <span className="text-sm text-nav-muted" lang={other} dir={other === 'ar' ? 'rtl' : 'ltr'}>{goal[other]}</span>
                </span>
              </motion.li>
            );
          })}
        </ul>

        {/* Available from the first moment: nobody has to wait for the scene. */}
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button ref={exploreRef} type="button" onClick={() => onClose(true)} data-testid="entrance-explore"
            className="inline-flex min-h-11 items-center gap-2 rounded-md bg-nav-foreground px-6 py-2 font-semibold text-nav hover:bg-nav-foreground/90">
            {t('entrance.explore')}
          </button>
          <button type="button" onClick={() => onClose(false)} data-testid="entrance-skip"
            className="inline-flex min-h-11 items-center rounded-md border border-nav-foreground/40 px-5 py-2 font-medium hover:bg-nav-active">
            {t('entrance.skip')}
          </button>
        </div>
        <p className="max-w-xl text-xs leading-relaxed text-nav-muted">{t('app.identityNote')}</p>
      </div>
    </div>
  );
}

/** While the scene's code loads: the same space, empty; after a moment the text appears anyway. */
function SceneLoading({ onSlow }: { onSlow: () => void }) {
  useEffect(() => {
    const id = window.setTimeout(onSlow, SLOW_LOAD_MS);
    return () => window.clearTimeout(id);
  }, [onSlow]);
  return <div className="absolute inset-0" data-testid="entrance-scene-loading" />;
}

/** The scene could not load (offline, blocked): a plain sign in its place. */
function SceneUnavailable({ onShown }: { onShown: () => void }) {
  useEffect(() => { onShown(); }, [onShown]);
  return (
    <div className="absolute inset-0 flex items-end justify-center pb-[6%]" data-testid="entrance-scene-fallback">
      <div className="rounded-md border-[6px] border-[#8e5c34] bg-[#fbf7ee] px-8 py-3 shadow-raised sm:px-12 sm:py-5">
        <span className="text-4xl font-semibold tracking-[0.12em] text-[#0c3326] sm:text-6xl" lang="en" dir="ltr">OSRIP</span>
      </div>
    </div>
  );
}
