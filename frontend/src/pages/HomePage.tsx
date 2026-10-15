import { ArrowRight, CircleHelp, Scale, ScanSearch, type LucideIcon } from 'lucide-react';
import type { CSSProperties } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { CrenellationDivider, LatticeBackdrop } from '@/components/brand/BrandMark';
import { EditorialImage } from '@/components/brand/EditorialImage';
import { Photo, PhotoCaption } from '@/components/common/Photo';
import { useSeries } from '@/api/queries';
import { useReferencePack } from '@/api/referencePack';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { buttonVariants } from '@/components/ui/button';
import type { ObservationRecord, SectionCode, Series } from '@/domain/types';
import { REVISION_STATUS_KEY } from '@/i18n/keys';
import { useTilt } from '@/lib/useTilt';
import { formatPeriod } from '@/lib/format';
import { sourceTitle, useProvenance } from '@/lib/provenance';
import { useDataMode } from '@/state/useDataMode';
import { PHOTOS, type PhotoCredit } from '@/content/photos';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const DOES: ReadonlyArray<{
  icon: LucideIcon;
  title: 'pages.home.does.inspectTitle' | 'pages.home.does.compareTitle' | 'pages.home.does.investigateTitle';
  body: 'pages.home.does.inspect' | 'pages.home.does.compare' | 'pages.home.does.investigate';
}> = [
  { icon: ScanSearch, title: 'pages.home.does.inspectTitle', body: 'pages.home.does.inspect' },
  { icon: Scale, title: 'pages.home.does.compareTitle', body: 'pages.home.does.compare' },
  { icon: CircleHelp, title: 'pages.home.does.investigateTitle', body: 'pages.home.does.investigate' },
];

const DOMAINS: ReadonlyArray<{
  path: string;
  title: 'pages.energy.title' | 'pages.food.title' | 'pages.trade.title';
  intro: 'pages.energy.intro' | 'pages.food.intro' | 'pages.trade.intro';
  photo: PhotoCredit;
}> = [
  { path: '/energy', title: 'pages.energy.title', intro: 'pages.energy.intro', photo: PHOTOS.desalination },
  { path: '/food-security', title: 'pages.food.title', intro: 'pages.food.intro', photo: PHOTOS.falaj },
  { path: '/trade', title: 'pages.trade.title', intro: 'pages.trade.intro', photo: PHOTOS.duqm },
];

const PRINCIPLES = [
  'pages.sources.rules.provenance',
  'pages.sources.rules.missing',
  'pages.sources.rules.modes',
  'pages.sources.rules.comparison',
] as const;

const container = 'mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-10';

const depth = (px: number) => ({ '--depth': `${px}px` }) as CSSProperties;

/** One headline per domain; the first indicator with published national data is shown. */
const HEADLINE: ReadonlyArray<{ section: SectionCode; indicators: readonly string[] }> = [
  { section: 'electricity', indicators: ['ELEC_GROSS_GENERATION', 'ELEC_GENERATION'] },
  { section: 'water', indicators: ['WATER_PRODUCTION', 'WATER_CONSUMPTION'] },
  { section: 'food_security', indicators: ['FISH_CAPTURE_LANDINGS', 'FOOD_PRODUCTION'] },
  { section: 'trade', indicators: ['TRADE_MERCH_EXPORTS', 'TRADE_VALUE'] },
];

type SeriesQuery = ReturnType<typeof useSeries>;

/** The most recent national value of the first available indicator, from full years and year-to-date totals. */
function latestOf(queries: readonly SeriesQuery[], indicators: readonly string[]): { series: Series; obs: ObservationRecord } | null {
  const all = queries.flatMap((q) => (q.data?.status === 'ok' ? q.data.series : []));
  for (const code of indicators) {
    const candidates = all.filter(
      (s) => s.indicatorCode === code && (s.area?.code ?? 'OM') === 'OM' && s.partnerCode === null && (s.flow === null || s.flow === 'domestic_export'),
    );
    let best: { series: Series; obs: ObservationRecord } | null = null;
    for (const series of candidates) {
      for (const obs of series.observations) {
        if (obs.value !== null && (!best || obs.periodEnd > best.obs.periodEnd)) best = { series, obs };
      }
    }
    if (best) return best;
  }
  return null;
}

/**
 * Latest published value of each headline indicator in the current data mode, or
 * "Data unavailable". Each card names its own period: domains are published on
 * different schedules, so the cards do not share one "latest month".
 */
function LatestFigures() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const provenance = useProvenance();
  const queries = {
    electricity: [useSeries('electricity', mode, 'annual'), useSeries('electricity', mode, 'year_to_date')],
    water: [useSeries('water', mode, 'annual'), useSeries('water', mode, 'year_to_date')],
    food_security: [useSeries('food_security', mode, 'annual'), useSeries('food_security', mode, 'year_to_date')],
    trade: [useSeries('trade', mode, 'annual'), useSeries('trade', mode, 'year_to_date')],
  } satisfies Record<SectionCode, SeriesQuery[]>;
  return (
    <section aria-labelledby="latest-heading" className="flex flex-col gap-2" data-testid="latest-figures">
      <h2 id="latest-heading" className="flex flex-wrap items-center gap-2 text-sm font-semibold">
        {t('pages.home.latestHeading')} <DataModeBadge mode={mode} />
      </h2>
      <ul className="grid gap-3 sm:grid-cols-2">
        {HEADLINE.map(({ section, indicators }) => {
          const qs = queries[section];
          const found = latestOf(qs, indicators);
          const shown = found ? provenance.value(found.obs, language, 1) : null;
          const ytd = found && found.series.frequency === 'year_to_date';
          return (
            <li key={section} className="surface-card p-4" data-testid="latest-card" data-section={section}
              data-indicator={found?.series.indicatorCode ?? indicators[0]}>
              <p className="text-xs text-muted-foreground">{found ? found.series.name[language] : t(`pages.home.headline.${section}`)}</p>
              {qs.some((q) => q.isPending) ? <p className="mt-1 text-sm text-muted-foreground">{t('states.loading')}</p> : found && shown ? (
                <>
                  <p className="mt-1 text-2xl font-semibold tabular-nums" dir="ltr">{shown.text}</p>
                  <p className="text-xs text-muted-foreground">
                    {found.series.unit.label[language]} · {formatPeriod(found.obs.periodStart, found.obs.periodEnd, language)}
                    {ytd ? ` · ${t('frequency.year_to_date')}` : found.obs.periodComplete ? '' : ` · ${t('table.incompletePeriod')}`}
                    {found.obs.revisionStatus ? ` · ${t(REVISION_STATUS_KEY[found.obs.revisionStatus])}` : ''}
                  </p>
                  <p className="mt-1 truncate text-xs text-muted-foreground" title={found.series.source.title}>
                    <bdi>{sourceTitle(found.series)}</bdi>
                  </p>
                </>
              ) : (
                <p className="mt-1 text-sm font-medium text-muted-foreground" data-state="data-unavailable">{t('states.dataUnavailable')}</p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** The prototype's status: names the loaded reference pack and its cutoff, or says nothing verified is published. */
function StatusText() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const pack = useReferencePack();
  const loaded = pack.data?.pack && pack.data.pack.published_records > 0 ? pack.data.pack : null;
  if (!loaded) return <p className="text-muted-foreground">{t('pages.home.status')}</p>;
  return (
    <p className="text-muted-foreground" data-testid="pack-status">
      {t('pages.home.statusPack', {
        count: loaded.published_records,
        cutoff: formatPeriod(loaded.research_cutoff, loaded.research_cutoff, language),
      })}
    </p>
  );
}

export function HomePage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const heroTilt = useTilt(6);
  const cardTilt = useTilt(3);
  useDocumentTitle(t('app.shortName'));

  return (
    <div data-testid="home-page">
      {/* Hero: sand and white, deep green accents, the portrait illustration in an arch. */}
      <section aria-labelledby="home-title" className="relative isolate overflow-hidden bg-sand-subtle/60">
        <LatticeBackdrop className="bg-sand/20" />
        <div className={cn(container, 'relative grid items-center gap-10 py-12 md:py-16 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]')}>
          <div className="flex flex-col gap-6">
            <p className="w-fit rounded-sm border border-primary/40 bg-card px-2.5 py-1 text-xs font-semibold text-primary ltr:tracking-wide ltr:uppercase">
              {t('pages.home.eyebrow')}
            </p>
            <h1 id="home-title" className="max-w-2xl text-4xl leading-tight font-semibold text-foreground sm:text-5xl">
              {t('pages.home.title')}
            </h1>
            <p className="max-w-xl text-base text-muted-foreground sm:text-lg">{t('pages.home.intro')}</p>
            <div className="flex flex-wrap gap-3">
              <Link to={to('/overview')} className={buttonVariants({ size: 'lg' })}>
                {t('pages.home.ctaOverview')}
                <ArrowRight aria-hidden="true" className="rtl:-scale-x-100" />
              </Link>
              <Link to={to('/sources')} className={buttonVariants({ size: 'lg', variant: 'outline' })}>
                {t('pages.home.ctaMethod')}
              </Link>
            </div>
            <LatestFigures />
          </div>
          <figure className="mx-auto w-full max-w-sm" data-testid="home-portrait">
            {/* Dimensional hero: three layers at different depths, moved a few degrees by the
                pointer. Flat (2D) on touch screens and with reduced motion. */}
            <div className="scene relative" data-testid="hero-scene" {...heroTilt}>
              <div aria-hidden="true" className="depth absolute -inset-3 rounded-[2.5rem] bg-gradient-to-b from-copper-subtle to-transparent" style={depth(-40)} />
              <div className="depth relative mx-auto w-4/5 overflow-hidden rounded-t-[10rem] rounded-b-2xl shadow-[var(--shadow-raised)]" style={depth(0)}>
                <EditorialImage id="omani-professional" alt={t('pages.home.portraitAlt')} sizes="(min-width: 1024px) 18rem, 70vw" eager />
              </div>
              <div aria-hidden="true" className="depth absolute -start-6 bottom-16 hidden w-28 lg:w-32 rotate-[-4deg] rounded-xl bg-card p-1.5 shadow-[var(--shadow-raised)] sm:block" style={depth(60)}>
                <img src="/images/illustrations/sector-water.svg" width={320} height={240} alt="" className="h-auto w-full rounded-lg" loading="lazy" decoding="async" />
              </div>
              <div aria-hidden="true" className="depth absolute end-0 top-6 hidden w-24 lg:w-28 rotate-[5deg] rounded-xl bg-card p-1.5 shadow-[var(--shadow-raised)] sm:block" style={depth(90)}>
                <img src="/images/illustrations/sector-electricity.svg" width={320} height={240} alt="" className="h-auto w-full rounded-lg" loading="lazy" decoding="async" />
              </div>
            </div>
            <figcaption className="mt-2 text-center text-xs text-muted-foreground" data-testid="portrait-label">
              {t('pages.home.portraitLabel')}
            </figcaption>
          </figure>
        </div>
      </section>
      <div className="relative">
        <img src={PHOTOS.misfat.src} width={PHOTOS.misfat.width} height={PHOTOS.misfat.height}
          alt={PHOTOS.misfat.alt[language]} loading="lazy" className="h-40 w-full object-cover sm:h-56" />
        <PhotoCaption standalone photo={PHOTOS.misfat}
          className="absolute end-0 bottom-0 max-w-full rounded-ss-md bg-black/65 px-3 py-1.5 text-white [&_a]:text-white" />
      </div>      <CrenellationDivider className="bg-sand/60" />

      {/* Purpose */}
      <section aria-labelledby="does-heading" className={cn(container, 'py-16')}>
        <h2 id="does-heading" className="mb-8 text-2xl font-semibold sm:text-3xl">
          {t('pages.home.doesHeading')}
        </h2>
        <ul className="grid gap-5 md:grid-cols-3">
          {DOES.map(({ icon: Icon, title, body }) => (
            <li key={title} className="tilt surface-card p-6" {...cardTilt}>
              <span className="mb-4 flex size-11 items-center justify-center rounded-full bg-sand-subtle text-sand-foreground">
                <Icon aria-hidden="true" className="size-5" />
              </span>
              <h3 className="mb-2 font-semibold">{t(title)}</h3>
              <p className="text-sm text-muted-foreground">{t(body)}</p>
            </li>
          ))}
        </ul>
        <div className="surface-card mt-6 border-s-4 border-s-copper p-6">
          <h3 className="mb-1 font-semibold text-accent">{t('pages.home.doesNotHeading')}</h3>
          <p className="max-w-3xl text-sm text-muted-foreground">{t('pages.home.doesNot')}</p>
        </div>
      </section>

      {/* Domains */}
      <section aria-labelledby="domains-heading" className="border-y border-border bg-card/60 py-16">
        <div className={container}>
          <h2 id="domains-heading" className="mb-2 text-2xl font-semibold sm:text-3xl">
            {t('pages.home.domainsHeading')}
          </h2>
          <p className="mb-8 max-w-2xl text-muted-foreground">{t('pages.home.domainsIntro')}</p>
          <ul className="grid gap-6 md:grid-cols-3">
            {DOMAINS.map((domain) => (
              <li key={domain.path} className="tilt surface-card flex flex-col overflow-hidden" {...cardTilt}>
                <Photo photo={domain.photo} className="[&_figcaption]:px-5" imgClassName="aspect-[16/10]" />
                <div className="flex flex-1 flex-col gap-2 p-5 pt-4">
                  <h3 className="text-lg font-semibold">{t(domain.title)}</h3>
                  <p className="text-sm text-muted-foreground">{t(domain.intro)}</p>
                  <Link
                    to={to(domain.path)}
                    className="mt-auto inline-flex w-fit items-center gap-1.5 pt-3 text-sm font-medium text-primary underline-offset-4 hover:underline"
                  >
                    {t('pages.home.explore', { domain: t(domain.title) })}
                    <ArrowRight aria-hidden="true" className="size-4 rtl:-scale-x-100" />
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Principles */}
      <section aria-labelledby="principles-heading" className="on-nav relative overflow-hidden bg-nav text-nav-foreground">
        <LatticeBackdrop className="bg-nav-foreground/[0.07]" />
        <div className={cn(container, 'relative grid items-center gap-10 py-16 lg:grid-cols-2')}>
          <div>
            <h2 id="principles-heading" className="mb-6 text-2xl font-semibold sm:text-3xl">
              {t('pages.home.principlesHeading')}
            </h2>
            <ol className="flex flex-col gap-4">
              {PRINCIPLES.map((key, i) => (
                <li key={key} className="flex gap-4">
                  <span
                    aria-hidden="true"
                    className="flex size-8 shrink-0 items-center justify-center rounded-full border border-nav-ring/60 text-sm font-semibold text-nav-ring"
                  >
                    {i + 1}
                  </span>
                  <p className="pt-1">{t(key)}</p>
                </li>
              ))}
            </ol>
          </div>
          <Photo
            photo={PHOTOS.bahla}
            className="overflow-hidden rounded-lg [&_figcaption]:text-nav-muted [&_figcaption_a]:text-nav-foreground"
            imgClassName="rounded-lg"
          />
        </div>
      </section>

      {/* Status */}
      <section aria-labelledby="status-heading" className={cn(container, 'py-16')}>
        <div className="grid overflow-hidden rounded-lg border border-border bg-card shadow-card md:grid-cols-5">
          <Photo photo={PHOTOS.wahiba} className="md:col-span-2 [&_figcaption]:px-5 [&_figcaption]:pb-3" imgClassName="aspect-[16/9] md:aspect-auto md:h-72" />
          <div className="flex flex-col justify-center gap-4 p-6 sm:p-8 md:col-span-3">
            <h2 id="status-heading" className="text-2xl font-semibold">
              {t('pages.home.statusHeading')}
            </h2>
            <StatusText />
            <div className="flex flex-wrap gap-3">
              <Link to={to('/overview')} className={buttonVariants()}>
                {t('pages.home.ctaOverview')}
                <ArrowRight aria-hidden="true" className="rtl:-scale-x-100" />
              </Link>
              <Link to={{ ...to('/sources'), hash: '#image-credits' }} className={buttonVariants({ variant: 'outline' })}>
                {t('pages.home.creditsLink')}
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
