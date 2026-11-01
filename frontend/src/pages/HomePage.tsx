import { ArrowRight, Bot, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useSeries } from '@/api/queries';
import { useReferencePack } from '@/api/referencePack';
import type { Sector } from '@/components/brand/SectorIllustration';
import { SectorImage } from '@/components/brand/SectorImage';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { PhotoCaption } from '@/components/common/Photo';
import { buttonVariants } from '@/components/ui/button';
import { PHOTOS } from '@/content/photos';
import { HEADLINE, latestOf, type SeriesQuery } from '@/domain/headline';
import type { SectionCode } from '@/domain/types';
import { REVISION_STATUS_KEY } from '@/i18n/keys';
import { formatPeriod } from '@/lib/format';
import { sourceTitle, useProvenance } from '@/lib/provenance';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { cn } from '@/lib/utils';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const SECTORS: readonly { section: SectionCode; image: Sector; path: string; title: 'pages.electricity.title' | 'pages.water.title' | 'pages.food.title' | 'pages.trade.title' }[] = [
  { section: 'electricity', image: 'electricity', path: '/energy/electricity', title: 'pages.electricity.title' },
  { section: 'water', image: 'water', path: '/energy/water', title: 'pages.water.title' },
  { section: 'food_security', image: 'food', path: '/food-security', title: 'pages.food.title' },
  { section: 'trade', image: 'trade', path: '/trade', title: 'pages.trade.title' },
];

const PRINCIPLES = [
  'pages.sources.rules.provenance',
  'pages.sources.rules.missing',
  'pages.sources.rules.modes',
  'pages.sources.rules.comparison',
] as const;

const container = 'mx-auto w-full max-w-[var(--content-max)] px-4 sm:px-6 lg:px-10';

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
    <section aria-labelledby="latest-heading" className="flex flex-col gap-3" data-testid="latest-figures">
      <h2 id="latest-heading" className="gold-rule flex flex-wrap items-center gap-2 text-xl font-semibold sm:text-2xl">
        {t('pages.home.latestHeading')} <DataModeBadge mode={mode} />
      </h2>
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {HEADLINE.map(({ section, indicators }) => {
          const qs = queries[section];
          const found = latestOf(qs, indicators);
          const shown = found ? provenance.value(found.obs, language, 1) : null;
          const ytd = found && found.series.frequency === 'year_to_date';
          return (
            <li key={section} className="surface-card flex flex-col gap-1 p-5" data-testid="latest-card" data-section={section}
              data-indicator={found?.series.indicatorCode ?? indicators[0]}>
              <p className="text-sm text-muted-foreground">{found ? found.series.name[language] : t(`pages.home.headline.${section}`)}</p>
              {qs.some((q) => q.isPending) ? <p className="text-base text-muted-foreground">{t('states.loading')}</p> : found && shown ? (
                <>
                  <p className="text-3xl font-semibold tabular-nums" dir="ltr">{shown.text}</p>
                  <p className="text-sm text-muted-foreground">
                    {found.series.unit.label[language]} · {formatPeriod(found.obs.periodStart, found.obs.periodEnd, language)}
                    {ytd ? ` · ${t('frequency.year_to_date')}` : found.obs.periodComplete ? '' : ` · ${t('table.incompletePeriod')}`}
                    {found.obs.revisionStatus ? ` · ${t(REVISION_STATUS_KEY[found.obs.revisionStatus])}` : ''}
                  </p>
                  <p className="truncate text-sm text-muted-foreground" title={found.series.source.title}>
                    <bdi>{sourceTitle(found.series)}</bdi>
                  </p>
                </>
              ) : (
                <p className="text-base font-medium text-muted-foreground" data-state="data-unavailable">{t('states.dataUnavailable')}</p>
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
  if (!loaded) return <p className="text-base text-nav-muted">{t('pages.home.status')}</p>;
  return (
    <p className="text-base text-nav-muted" data-testid="pack-status">
      {t('pages.home.statusPack', {
        count: loaded.published_records,
        cutoff: formatPeriod(loaded.research_cutoff, loaded.research_cutoff, language),
      })}
    </p>
  );
}

/**
 * The landing page: a credited photograph of a real Omani place with the platform's name and two
 * actions, the latest published figures (labelled with the data mode), the four sectors and the
 * data rules. No pointer effects, parallax or decorative animation.
 */
export function HomePage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  useDocumentTitle(t('app.shortName'));
  const hero = PHOTOS.misfat;

  return (
    <div data-testid="home-page">
      {/* Hero: the photograph with a navy veil on the text side, so the text keeps its contrast. */}
      <section aria-labelledby="home-title" className="on-nav relative isolate overflow-hidden bg-nav text-nav-foreground">
        <img src={hero.src} width={hero.width} height={hero.height} alt={hero.alt[language]} sizes="100vw" decoding="async"
          className="absolute inset-0 -z-10 size-full object-cover object-[50%_70%]" data-testid="home-hero-image" />
        <div aria-hidden="true" className="absolute inset-0 -z-10 bg-gradient-to-r from-nav via-nav/75 to-nav/5 rtl:bg-gradient-to-l" />
        <div className={cn(container, 'flex min-h-[26rem] flex-col justify-center gap-6 py-14 sm:min-h-[30rem] lg:py-20 3xl:min-h-[36rem]')}>
          <p className="w-fit rounded-md border border-nav-ring/60 px-2.5 py-1 text-sm font-semibold text-nav-ring ltr:tracking-wide ltr:uppercase">
            {t('pages.home.eyebrow')}
          </p>
          <h1 id="home-title" className="max-w-3xl text-4xl leading-tight font-semibold sm:text-5xl 3xl:text-6xl">
            {t('pages.home.title')}
          </h1>
          <p className="max-w-2xl text-base text-nav-muted sm:text-lg">{t('pages.home.intro')}</p>
          <div className="flex flex-wrap gap-3">
            <Link to={to('/overview')} className={buttonVariants({ size: 'lg' })}>
              {t('pages.home.ctaOverview')}
              <ArrowRight aria-hidden="true" className="rtl:-scale-x-100" />
            </Link>
            <Link to={to('/assistant')} className={cn(buttonVariants({ size: 'lg', variant: 'outline' }), 'border-nav-foreground/40 bg-transparent text-nav-foreground hover:bg-nav-active')}>
              <Bot aria-hidden="true" />{t('pages.home.ctaAssistant')}
            </Link>
          </div>
        </div>
        <PhotoCaption standalone photo={hero}
          className="absolute end-0 bottom-0 max-w-full rounded-ss-md bg-black/65 px-3 py-1.5 text-xs text-white [&_a]:text-white" />
      </section>

      <div className={cn(container, 'flex flex-col gap-12 py-12 lg:gap-16 lg:py-16')}>
        <LatestFigures />

        {/* The four sectors */}
        <section aria-labelledby="domains-heading" className="flex flex-col gap-4">
          <h2 id="domains-heading" className="gold-rule text-xl font-semibold sm:text-2xl">{t('overviewIntro.sectorsHeading')}</h2>
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {SECTORS.map((s) => (
              <li key={s.section} className="surface-card card-link flex flex-col overflow-hidden" data-testid="home-sector" data-section={s.section}>
                <SectorImage sector={s.image} />
                <div className="flex flex-1 flex-col gap-2 p-5">
                  <h3 className="text-lg font-semibold">{t(s.title)}</h3>
                  <Link to={to(s.path)}
                    className="mt-auto inline-flex w-fit items-center gap-1.5 pt-2 text-base font-medium text-primary underline-offset-4 hover:underline">
                    {t('pages.home.explore', { domain: t(s.title) })}
                    <ArrowRight aria-hidden="true" className="size-4 rtl:-scale-x-100" />
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {/* The data rules and where the prototype stands */}
      <section aria-labelledby="principles-heading" className="on-nav bg-nav text-nav-foreground">
        <div className={cn(container, 'grid gap-10 py-14 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)] lg:py-16')}>
          <div>
            <h2 id="principles-heading" className="mb-6 flex items-center gap-2 text-xl font-semibold sm:text-2xl">
              <ShieldCheck aria-hidden="true" className="size-6 text-nav-ring" />{t('pages.home.principlesHeading')}
            </h2>
            <ol className="grid gap-4 sm:grid-cols-2">
              {PRINCIPLES.map((key, i) => (
                <li key={key} className="flex gap-3">
                  <span aria-hidden="true"
                    className="flex size-7 shrink-0 items-center justify-center rounded-full border border-nav-ring/60 text-xs font-semibold text-nav-ring">
                    {i + 1}
                  </span>
                  <p className="text-base">{t(key)}</p>
                </li>
              ))}
            </ol>
          </div>
          <div className="flex flex-col justify-center gap-4 rounded-xl border border-nav-foreground/15 bg-nav-active/60 p-6">
            <h2 className="text-lg font-semibold">{t('pages.home.statusHeading')}</h2>
            <StatusText />
            <div className="flex flex-wrap gap-2">
              <Link to={to('/sources')} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'border-nav-foreground/40 bg-transparent text-nav-foreground hover:bg-nav-active')}>
                {t('pages.home.ctaMethod')}
              </Link>
              <Link to={{ ...to('/sources'), hash: '#image-credits' }} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'border-nav-foreground/40 bg-transparent text-nav-foreground hover:bg-nav-active')}>
                {t('pages.home.creditsLink')}
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
