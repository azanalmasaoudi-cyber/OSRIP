import { BarChart3, Sparkles, Table2 } from 'lucide-react';
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';

import { adapterKind } from '@/api/config';
import { useAvailability, VIEWS } from '@/api/series';
import { StatePanel } from '@/components/common/StatePanel';
import { AreaComparison } from '@/components/sector/AreaComparison';
import { AskMulhim } from '@/components/sector/AskMulhim';
import { DecisionBrief } from '@/components/sector/DecisionBrief';
import { resolve, sortIndicators, type Resolved } from '@/components/sector/SectorWorkflow';
import { Button } from '@/components/ui/button';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import { RecentStudies } from '@/components/workspace/DashboardPanels';
import { SelectionStudy } from '@/components/workspace/SelectionStudy';
import type { SectionCode } from '@/domain/types';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useSectorSelection, type SectorSelection } from '@/state/sectorSelections';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * The sector's Analysis (what the Analysis Workspace offered, now for this sector only): the
 * current selection (indicator, area and period view, shared with Tables and charts and kept
 * per sector) and, for it, the server's validated findings and rule-based recommendations, the
 * governorates compared where that is valid, Al Mulhim for a study, a forecast or a scenario,
 * and the axis's decision brief. Every figure comes from published observations; nothing here
 * is written by AI.
 */
export function SectorAnalysis({ section, onOpenCharts }: { section: SectionCode; onOpenCharts: () => void }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const availability = useAvailability(section, mode);
  const { state, setDraft } = useSectorSelection(section, mode);
  const navigate = useNavigate();
  const to = usePreservedSearch();

  if (adapterKind !== 'http') {
    return <StatePanel kind="not_implemented"><p className="text-base text-muted-foreground">{t('sectorFlow.requiresApi')}</p></StatePanel>;
  }
  if (availability.isPending) return <StatePanel kind="loading" skeleton="cards" />;
  if (availability.isError) {
    return (
      <StatePanel kind="error" error={availability.error} onRetry={() => void availability.refetch()}>
        <p className="text-base">{t('sectorFlow.availabilityFailed')}</p>
      </StatePanel>
    );
  }
  const indicators = sortIndicators(section, availability.data.indicators, language);
  // The selection being made (shared with Tables and charts), or the sector's headline indicator.
  const resolved: Resolved | null = resolve(state.draft ?? state.applied, indicators);
  if (!resolved) {
    return (
      <div className="flex flex-col gap-6">
        <StatePanel kind={mode === 'verified_source' ? 'no_verified_data' : 'empty'}>
          <p className="text-base text-muted-foreground" data-testid="sector-no-data">{t('sectorFlow.noData')}</p>
        </StatePanel>
        <DecisionBrief section={section} />
      </div>
    );
  }
  const { selection, indicator, entry, areas, available } = resolved;
  const change = (next: Partial<SectorSelection>) => {
    const r = resolve({ ...selection, ...next }, indicators);
    if (r) setDraft(r.selection);
  };
  const indicatorName = indicator.name[language];
  const areaName = entry.area.name[language];

  return (
    <div className="flex flex-col gap-6" data-testid="sector-analysis" data-indicator={selection.indicator} data-area={selection.area}
      data-view={selection.view}>
      {/* What is analysed: chosen here or in Tables and charts (one selection per sector). */}
      <section aria-labelledby={`${section}-analysis-h`} className="flex flex-col gap-4 rounded-lg border border-border border-s-4 border-s-primary bg-card p-4 shadow-card sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-muted-foreground">{t('sector.analysis.current')}</p>
            <h2 id={`${section}-analysis-h`} className="text-xl font-semibold" data-testid="sector-analysis-title">{indicatorName}</h2>
            <p className="text-sm text-muted-foreground" data-testid="sector-analysis-definition">{indicator.definition[language]}</p>
          </div>
          <Button variant="outline" size="sm" onClick={onOpenCharts} data-testid="sector-open-charts">
            <Table2 aria-hidden="true" />{t('sector.analysis.openCharts')}
          </Button>
        </div>
        {/* The period views (with their "not published" notes) take a row of their own: squeezed
            into a third column beside the sidebar they ran past the page edge at 1024 px. */}
        <div className="grid gap-3 sm:grid-cols-2">
          <SelectField label={t('sectorFlow.indicator')} value={selection.indicator}
            onValueChange={(v) => change({ indicator: v, breakdown: '', view: undefined })}
            options={indicators.map((i) => ({ value: i.code, label: i.name[language] }))} data-testid="analysis-indicator" />
          {areas.length > 1 ? (
            <SelectField label={t('sectorFlow.area')} value={selection.area} onValueChange={(v) => change({ area: v, breakdown: '', view: undefined })}
              options={areas.map((a) => ({ value: a.code, label: a.name[language] }))} data-testid="analysis-area" />
          ) : (
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">{t('sectorFlow.area')}</span>
              <p className="text-base" data-testid="analysis-area-fixed">{areaName}</p>
            </div>
          )}
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <span className="text-sm font-medium" aria-hidden="true">{t('sectorFlow.frequency')}</span>
            <Segmented label={t('sectorFlow.frequency')} value={selection.view} testId="analysis-frequency" className="w-full"
              onChange={(v) => { const view = VIEWS.find((x) => x === v); if (view) change({ view }); }}
              options={VIEWS.map((v) => ({ value: v, label: t(`series.views.${v}`), note: available.includes(v) ? undefined : t('series.viewUnavailable') }))} />
          </div>
        </div>
      </section>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)]">
        <section aria-labelledby={`${section}-findings-h`} className="flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-card p-4 shadow-card sm:p-5"
          data-testid="sector-findings">
          <h2 id={`${section}-findings-h`} className="flex items-center gap-2 text-base font-semibold">
            <Sparkles aria-hidden="true" className="size-4 text-primary" />{t('sector.analysis.findings')}
          </h2>
          <p className="text-sm text-muted-foreground">{t('sector.analysis.findingsNote')}</p>
          <SelectionStudy indicator={selection.indicator} area={selection.area} periodKind={selection.view} mode={mode} section={section} />
        </section>
        <div className="flex min-w-0 flex-col gap-6">
          <AskMulhim indicator={indicatorName} area={areaName} />
          <AreaComparison indicator={selection.indicator} frequency={selection.view} />
          {/* This session's studies open under their reply on the Al Mulhim page. */}
          <RecentStudies onOpen={(id) => void navigate(to(`/assistant?${new URLSearchParams({ study: id }).toString()}`))} />
        </div>
      </div>

      <DecisionBrief section={section} />
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <BarChart3 aria-hidden="true" className="size-4" />{t('sector.analysis.chartsNote')}
      </p>
    </div>
  );
}
