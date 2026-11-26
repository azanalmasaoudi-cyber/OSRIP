import { useEffect } from 'react';
import { useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useAvailability, VIEWS } from '@/api/series';
import type { Sector } from '@/components/brand/SectorIllustration';
import { SectorArtwork } from '@/components/brand/SectorArtwork';
import { AnnualIndicators } from '@/components/sector/AnnualIndicators';
import { CommodityRegistry } from '@/components/common/CommodityRegistry';
import { SectorGuide } from '@/components/sector/SectorGuide';
import { SectorIndicators } from '@/components/sector/SectorIndicators';
import { SectorNav } from '@/components/sector/SectorNav';
import { resolve, sortIndicators, SectorWorkflow } from '@/components/sector/SectorWorkflow';
import { Tabs, tabPanelProps } from '@/components/workspace/Tabs';
import type { SectionCode } from '@/domain/types';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { useSectorSelection, type SectorSelection } from '@/state/sectorSelections';
import { useDataMode } from '@/state/useDataMode';
import { useUpdateSearch } from '@/state/useUpdateSearch';
import { useUrlFilter } from '@/state/useUrlFilter';

const TABS = ['data', 'analysis', 'charts'] as const;
type Tab = (typeof TABS)[number];

/**
 * One sector page: the sector's name and artwork (whole, at the top, on every screen width;
 * below the text on phones) with the four sectors as tabs, then three views of the same sector,
 * sharing one selection (indicator, area and period view, kept per sector):
 *
 * - Data and indicators: every published indicator with its latest value and sources.
 * - Analysis (the default): the guided analysis (components/sector/SectorGuide), one step at a
 *   time: selection, results, analysis, objectives, recommendations.
 * - Tables and charts: the period-first workflow (components/sector/SectorWorkflow). Results
 *   appear only after "Show results"; a chart only after "Show chart".
 *
 * This replaces the separate Analysis Workspace: one component for all four sectors.
 */
function SectorPage({ section, page, image, registry = false }: {
  section: SectionCode;
  page: 'electricity' | 'water' | 'food' | 'trade';
  image: Sector;
  registry?: boolean;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const title = t(`pages.${page}.title`);
  useDocumentTitle(title);
  const [tab, setTab] = useUrlFilter<Tab>('tab', TABS, 'analysis');
  const availability = useAvailability(section, mode);
  const { setDraft } = useSectorSelection(section, mode);
  const indicators = availability.data ? sortIndicators(section, availability.data.indicators, language) : [];
  const choose = (next: Partial<SectorSelection>) => {
    const resolved = resolve(next, indicators);
    if (resolved) setDraft(resolved.selection);
  };

  // A link to a selection (an old /workspace link): its indicator, area and view become this
  // sector's selection once its availability is known; then the parameters leave the address.
  const [params] = useSearchParams();
  const update = useUpdateSearch();
  const linked = params.get('indicator');
  useEffect(() => {
    if (!linked || !availability.data) return;
    const view = VIEWS.find((v) => v === params.get('view'));
    const resolved = resolve({ indicator: linked, area: params.get('area') ?? undefined, view }, sortIndicators(section, availability.data.indicators, language));
    if (resolved) setDraft(resolved.selection);
    update((p) => { p.delete('indicator'); p.delete('area'); p.delete('view'); }, { replace: true });
  }, [linked, availability.data, params, section, language, setDraft, update]);

  const tabs = TABS.map((id) => ({ id, label: t(`sector.tabs.${id}`) }));
  return (
    <div className="flex flex-col gap-6 lg:gap-8" data-testid="sector-page" data-sector={page}>
      <header className="overflow-hidden rounded-xl border border-border bg-card shadow-card">
        <div className="grid items-center md:grid-cols-[minmax(0,1fr)_minmax(0,0.95fr)]">
          <div className="gold-rule flex flex-col justify-center gap-2 p-5 sm:p-6 lg:p-8">
            <p className="text-sm font-semibold text-primary ltr:tracking-wider ltr:uppercase">{t('sectorFlow.eyebrow')}</p>
            <h1 className="text-2xl leading-tight font-semibold sm:text-3xl 3xl:text-4xl">{title}</h1>
            <p className="max-w-2xl text-base text-muted-foreground">{t(`pages.${page}.lead`)}</p>
          </div>
          <div className="px-3 pb-3 md:py-3 md:ps-0">
            <SectorArtwork sector={image} eager sizes="(min-width: 768px) 46vw, 100vw" className="overflow-hidden rounded-xl shadow-card" />
          </div>
        </div>
        <SectorNav />
      </header>

      <Tabs tabs={tabs} value={tab} onChange={setTab} idBase="sector" label={t('sector.tabs.label', { sector: title })} className="w-full sm:w-fit" />

      {tab === 'data' ? (
        <div {...tabPanelProps('sector', 'data', true)} className="flex flex-col gap-6 outline-none">
          {section === 'electricity' || section === 'water' ? <AnnualIndicators section={section} /> : null}
          <SectorIndicators section={section}
            onAnalyse={(code, kind) => { choose({ indicator: code, view: VIEWS.find((v) => v === kind) }); setTab('analysis'); }}>
            {registry ? (
              <details className="rounded-lg border border-border bg-card p-4 shadow-card" data-testid="commodity-registry-details">
                <summary className="cursor-pointer text-base font-semibold">{t('pages.food.commoditiesHeading')}</summary>
                <div className="mt-3"><CommodityRegistry /></div>
              </details>
            ) : null}
          </SectorIndicators>
        </div>
      ) : null}
      {tab === 'analysis' ? (
        <div {...tabPanelProps('sector', 'analysis', true)} className="outline-none">
          <SectorGuide section={section} title={title} />
        </div>
      ) : null}
      {tab === 'charts' ? (
        <div {...tabPanelProps('sector', 'charts', true)} className="outline-none">
          <SectorWorkflow section={section} title={title} />
        </div>
      ) : null}
    </div>
  );
}

export function ElectricityPage() {
  return <SectorPage section="electricity" page="electricity" image="electricity" />;
}

export function WaterPage() {
  return <SectorPage section="water" page="water" image="water" />;
}

export function FoodSecurityPage() {
  return <SectorPage section="food_security" page="food" image="food" registry />;
}

export function TradePage() {
  return <SectorPage section="trade" page="trade" image="trade" registry />;
}
