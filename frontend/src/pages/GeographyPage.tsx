import { CheckCircle2, CircleDashed, ExternalLink, MapPin } from 'lucide-react';
import { useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { adapterKind } from '@/api/config';
import {
  useAreaCoverage,
  useAreaObservations,
  useAreaRegistry,
  type AreaCoverage,
  type Coverage,
  type GeoReference,
  type Registry,
  type RegistryArea,
} from '@/api/geography';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { mixedFrequencies, MixedFrequencyNotice, type Frequency } from '@/components/common/MixedFrequency';
import { FilterBar } from '@/components/common/FilterBar';
import { PageHeader } from '@/components/common/PageHeader';
import { StatePanel } from '@/components/common/StatePanel';
import { Basemap } from '@/components/geography/Basemap';
import { GovernorateComparison } from '@/components/geography/GovernorateComparison';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { SelectField } from '@/components/ui/select';
import type { DataMode } from '@/domain/types';
import { FLOW_KEY } from '@/i18n/keys';
import { formatDecimal, formatPeriod, type AppLanguage } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDataMode } from '@/state/useDataMode';
import { useResetFilters, useUrlFilter } from '@/state/useUrlFilter';

const LEVELS = ['all', 'national', 'governorate', 'wilayat'] as const;
const COVERAGE_FILTER = ['all', 'with_data', 'no_data'] as const;
const NONE = 'none';

function areaName(area: { name_en: string; name_ar: string }, language: AppLanguage) {
  return language === 'ar' ? area.name_ar : area.name_en;
}

function otherName(area: { name_en: string; name_ar: string }, language: AppLanguage) {
  return language === 'ar' ? area.name_en : area.name_ar;
}

function NoData() {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1 text-muted-foreground" data-coverage="none">
      <CircleDashed aria-hidden="true" className="size-3.5" />
      <span className="italic">{t('pages.geography.noData')}</span>
    </span>
  );
}

function CoverageCell({ coverage, ready }: { coverage: AreaCoverage | undefined; ready: boolean }) {
  const { t } = useTranslation();
  if (!ready) return <span className="text-muted-foreground">{t('states.loading')}</span>;
  if (!coverage) return <NoData />;
  return (
    <span className="inline-flex items-center gap-1" data-coverage="some">
      <CheckCircle2 aria-hidden="true" className="size-3.5 text-verified-foreground" />
      {t('pages.geography.observationCount', { count: coverage.observations })}
      <span className="text-muted-foreground">· {t('pages.geography.indicatorCount', { count: coverage.indicators.length })}</span>
    </span>
  );
}

function ReferenceLink({ reference }: { reference: GeoReference }) {
  return (
    <a href={reference.url} target="_blank" rel="noreferrer" lang={reference.language} dir="auto"
      className="inline-flex items-center gap-1 text-primary underline underline-offset-2">
      {reference.title}
      <ExternalLink aria-hidden="true" className="size-3 shrink-0" />
    </a>
  );
}

function RegistrySummary({ registry }: { registry: Registry }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const v = registry.verification;
  return (
    <Card className="flex flex-col gap-3 p-5" data-testid="registry-summary">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">{t('pages.geography.registryHeading')}</h2>
        {v?.complete ? <Badge variant="verified"><CheckCircle2 aria-hidden="true" />{t('pages.geography.complete')}</Badge> : null}
      </div>
      <p className="text-sm text-muted-foreground">{t('pages.geography.registryExplain')}</p>
      {v ? (
        <>
          <p className="text-sm" data-testid="registry-counts">
            {t('pages.geography.registryCounts', { governorates: v.found_governorates, wilayats: v.found_wilayats })}
            {' · '}{t('pages.geography.verifiedOn', { date: v.verified_on })}
          </p>
          <p className="text-xs text-muted-foreground">{language === 'ar' ? v.basis_ar : v.basis_en}</p>
        </>
      ) : null}
      <details className="text-sm">
        <summary className="cursor-pointer font-medium">{t('pages.geography.referencesHeading', { count: registry.references.length })}</summary>
        <ul className="mt-2 flex flex-col gap-2">
          {registry.references.map((r) => (
            <li key={r.code} className="rounded-md border border-border p-2 text-xs">
              <ReferenceLink reference={r} />
              <p className="mt-0.5 text-muted-foreground" dir="auto">{r.publisher}</p>
              <p className="text-muted-foreground">
                {r.published_on ? `${t('pages.geography.publishedOn', { date: r.published_on })} · ` : ''}
                {r.page_updated_on ? `${t('pages.geography.pageUpdated', { date: r.page_updated_on })} · ` : ''}
                {t('pages.geography.accessedOn', { date: r.accessed_on })}
              </p>
              <p className="mt-0.5" dir="ltr" lang="en">{r.supports}</p>
            </li>
          ))}
        </ul>
      </details>
      <p className="text-xs text-muted-foreground">{t('pages.geography.codesNote')}</p>
    </Card>
  );
}

function CoverageSummary({ coverage, total, mode }: { coverage: Coverage | undefined; total: number; mode: DataMode }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const covered = coverage ? Object.keys(coverage.areas).length : null;
  return (
    <Card className="flex flex-col gap-3 p-5" data-testid="coverage-summary">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">{t('pages.geography.statisticalHeading')}</h2>
        <DataModeBadge mode={mode} />
      </div>
      <p className="text-sm text-muted-foreground">{t('pages.geography.statisticalExplain')}</p>
      {covered === null ? null : (
        <p className="text-sm" data-testid="coverage-counts">
          {t('pages.geography.coverageCounts', { covered, total })}
        </p>
      )}
      {coverage ? <p className="text-xs text-muted-foreground">{language === 'ar' ? coverage.note_ar : coverage.note_en}</p> : null}
    </Card>
  );
}

function AreaObservations({ mode, area }: { mode: DataMode; area: RegistryArea }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [frequency, setFrequency] = useState<Frequency | undefined>(undefined);
  const query = useAreaObservations(mode, area.code, frequency);
  if (query.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  const mixed = query.isError ? mixedFrequencies(query.error) : null;
  if (mixed) return <MixedFrequencyNotice frequencies={mixed} onChoose={setFrequency} />;
  if (query.isError) return <StatePanel kind="error" detail={query.error.message} onRetry={() => void query.refetch()} />;
  if (query.data.series.length === 0) {
    return (
      <div role="status" className="rounded-md border border-dashed border-border-strong/50 p-4 text-sm" data-testid="area-no-data">
        <p className="font-semibold"><NoData /></p>
        <p className="mt-1 text-muted-foreground">{t('pages.geography.noDataExplain', { area: areaName(area, language) })}</p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4" data-testid="area-observations">
      {query.data.series.map((s) => {
        const caption = [
          language === 'ar' ? s.indicator.name_ar : s.indicator.name_en,
          language === 'ar' ? s.unit.label_ar : s.unit.label_en,
          t(`frequency.${s.frequency as 'annual'}`),
          s.commodity?.code, s.partner?.code,
          s.flow && s.flow in FLOW_KEY ? t(FLOW_KEY[s.flow as keyof typeof FLOW_KEY]) : s.flow,
        ].filter(Boolean).join(' · ');
        return (
          <div key={`${s.dataset_version.id}-${s.indicator.code}-${s.commodity?.code}-${s.partner?.code}-${s.flow}`} className="relative overflow-x-auto">
            <table className="w-full min-w-[20rem] text-sm">
              <caption className="mb-1 text-start text-xs font-semibold">
                {caption}
                <span className="block font-normal text-muted-foreground">
                  {s.source.dataset_title} · {t('analysis.version')} <span dir="ltr">{s.dataset_version.label}</span>
                </span>
              </caption>
              <thead>
                <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                  <th scope="col" className="py-1 text-start font-medium">{t('table.period')}</th>
                  <th scope="col" className="py-1 text-end font-medium">{t('table.value')}</th>
                </tr>
              </thead>
              <tbody>
                {s.observations.map((o) => (
                  <tr key={o.period_start} className="border-b border-border last:border-0">
                    <td className="py-1">{formatPeriod(o.period_start, o.period_end, language)}</td>
                    <td className="py-1 text-end tabular-nums" dir="ltr">
                      {o.value === null ? <span className="italic text-muted-foreground">{t('states.missingValue')}</span> : formatDecimal(o.value, language, 4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}

function SelectedArea({ area, parent, registry, mode, onClear }: {
  area: RegistryArea; parent: RegistryArea | undefined; registry: Registry; mode: DataMode; onClear: () => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const refs = new Map(registry.references.map((r) => [r.code, r]));
  const note = language === 'ar' ? area.note_ar : area.note_en;
  return (
    <Card className="flex flex-col gap-4 p-5" data-testid="selected-area" data-area={area.code}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <MapPin aria-hidden="true" className="size-4 text-accent" />{areaName(area, language)}
          </h3>
          <p className="text-sm text-muted-foreground">{otherName(area, language)}</p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClear}>{t('pages.geography.clearSelection')}</Button>
      </div>
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
        <dt className="text-muted-foreground">{t('pages.geography.code')}</dt>
        <dd className="font-mono text-xs" dir="ltr">
          {area.code} <span className="font-sans text-muted-foreground">({t(`pages.geography.authority.${area.code_authority}`)})</span>
        </dd>
        <dt className="text-muted-foreground">{t('pages.geography.level')}</dt>
        <dd>{t(`pages.geography.levels.${area.level}`)}</dd>
        {parent ? (
          <>
            <dt className="text-muted-foreground">{t('pages.geography.parent')}</dt>
            <dd>{areaName(parent, language)}</dd>
          </>
        ) : null}
        {area.verified_on ? (
          <>
            <dt className="text-muted-foreground">{t('pages.geography.verified')}</dt>
            <dd dir="ltr" className="text-start">{area.verified_on}</dd>
          </>
        ) : null}
        {area.references.length > 0 ? (
          <>
            <dt className="text-muted-foreground">{t('pages.geography.sources')}</dt>
            <dd>
              <ul className="flex flex-col gap-1">
                {area.references.map((r) => {
                  const ref = refs.get(r.code);
                  return (
                    <li key={r.code} className="text-xs">
                      {ref ? <ReferenceLink reference={ref} /> : r.code}
                      <span className="text-muted-foreground"> — {r.supports.map((s) => t(`pages.geography.supports.${s as 'existence'}`)).join(language === 'ar' ? '، ' : ', ')}</span>
                    </li>
                  );
                })}
              </ul>
            </dd>
          </>
        ) : null}
      </dl>
      {note ? <p className="rounded-md bg-sand-subtle p-3 text-xs text-sand-foreground">{note}</p> : null}
      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <h4 className="text-sm font-semibold">{t('pages.geography.areaObservations')}</h4>
        <p className="text-xs text-muted-foreground">{t('pages.geography.noAllocation')}</p>
        <AreaObservations mode={mode} area={area} />
      </div>
    </Card>
  );
}

function AreaTable({ areas, byCode, coverage, selected, onSelect }: {
  areas: RegistryArea[]; byCode: Map<string, RegistryArea>; coverage: Coverage | undefined;
  selected: string; onSelect: (code: string) => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const captionId = useId();
  return (
    <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
      <table className="w-full min-w-[40rem] text-sm" aria-describedby={captionId} data-testid="area-table">
        <caption id={captionId} className="px-4 pt-3 text-start text-xs text-muted-foreground">
          {t('pages.geography.tableCaption', { count: areas.length })}
        </caption>
        <thead>
          <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
            <th scope="col" className="px-4 py-2 text-start font-medium">{t('pages.geography.name')}</th>
            <th scope="col" className="px-2 py-2 text-start font-medium">{t('pages.geography.code')}</th>
            <th scope="col" className="px-2 py-2 text-start font-medium">{t('pages.geography.level')}</th>
            <th scope="col" className="px-2 py-2 text-start font-medium">{t('pages.geography.parent')}</th>
            <th scope="col" className="px-2 py-2 text-start font-medium">{t('pages.geography.statisticalColumn')}</th>
            <th scope="col" className="px-4 py-2 text-end font-medium"><span className="sr-only">{t('pages.geography.select')}</span></th>
          </tr>
        </thead>
        <tbody>
          {areas.map((a) => {
            const parent = a.parent_code ? byCode.get(a.parent_code) : undefined;
            const isSelected = a.code === selected;
            return (
              <tr key={a.code} data-code={a.code} aria-current={isSelected ? 'true' : undefined}
                className={isSelected ? 'bg-sand-subtle/70' : 'border-b border-border last:border-0'}>
                <th scope="row" className="px-4 py-2 text-start font-medium">
                  {areaName(a, language)}
                  <span className="block text-xs font-normal text-muted-foreground">{otherName(a, language)}</span>
                </th>
                <td className="px-2 py-2 font-mono text-xs" dir="ltr">{a.code}</td>
                <td className="px-2 py-2">{t(`pages.geography.levels.${a.level}`)}</td>
                <td className="px-2 py-2">{parent ? areaName(parent, language) : '—'}</td>
                <td className="px-2 py-2"><CoverageCell coverage={coverage?.areas[a.code]} ready={coverage !== undefined} /></td>
                <td className="px-4 py-2 text-end">
                  <Button variant={isSelected ? 'default' : 'outline'} size="sm" aria-pressed={isSelected}
                    onClick={() => onSelect(a.code)}>
                    {isSelected ? t('pages.geography.selected') : t('pages.geography.select')}
                    <span className="sr-only"> {areaName(a, language)}</span>
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function GeographyPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const registry = useAreaRegistry();
  const coverage = useAreaCoverage(mode);
  const detailRef = useRef<HTMLDivElement>(null);
  const [search, setSearch] = useState('');
  const searchId = useId();

  const areas = registry.data?.areas ?? [];
  const byCode = new Map(areas.map((a) => [a.code, a]));
  const governorates = areas.filter((a) => a.level === 'governorate');

  const [level, setLevel] = useUrlFilter('level', LEVELS, 'all');
  const [gov, setGov] = useUrlFilter('governorate', ['all', ...governorates.map((g) => g.code)], 'all');
  const [cov, setCov] = useUrlFilter('coverage', COVERAGE_FILTER, 'all');
  const [selected, setSelected] = useUrlFilter('area', [NONE, ...areas.map((a) => a.code)], NONE);
  const { reset, active, count } = useResetFilters(['level', 'governorate', 'coverage']);

  if (adapterKind !== 'http') {
    return (
      <>
        <PageHeader title={t('pages.geography.title')} intro={t('pages.geography.intro')} />
        <StatePanel kind="not_implemented"><p className="text-sm text-muted-foreground">{t('pages.geography.requiresApi')}</p></StatePanel>
      </>
    );
  }

  const needle = search.trim().toLowerCase();
  const visible = areas.filter((a) => {
    if (level !== 'all' && a.level !== level) return false;
    if (gov !== 'all' && a.code !== gov && a.parent_code !== gov) return false;
    // Until coverage has loaded it is unknown, so the coverage filter does not apply yet.
    if (coverage.data) {
      const has = Boolean(coverage.data.areas[a.code]);
      if (cov === 'with_data' && !has) return false;
      if (cov === 'no_data' && has) return false;
    }
    if (needle && ![a.name_en, a.name_ar, a.code].some((s) => s.toLowerCase().includes(needle))) return false;
    return true;
  });
  const selectedArea = selected === NONE ? undefined : byCode.get(selected);
  // Indicators that at least one governorate publishes on its own (from coverage).
  const governorateIndicators = [...new Map(
    governorates.flatMap((g) => coverage.data?.areas[g.code]?.indicators ?? []).map((i) => [i.code, i]),
  ).values()].sort((a, b) => a.code.localeCompare(b.code));

  const select = (code: string) => {
    setSelected(code);
    // Move focus to the details so keyboard and screen-reader users land on the result.
    window.requestAnimationFrame(() => detailRef.current?.focus());
  };

  return (
    <>
      <PageHeader title={t('pages.geography.title')} intro={t('pages.geography.intro')} />
      {registry.isPending ? <StatePanel kind="loading" skeleton="cards" /> : null}
      {registry.isError ? <StatePanel kind="error" detail={registry.error.message} onRetry={() => void registry.refetch()} /> : null}
      {registry.data ? (
        <div className="flex flex-col gap-8">
          <div className="grid gap-4 lg:grid-cols-2">
            <RegistrySummary registry={registry.data} />
            <CoverageSummary coverage={coverage.data} total={areas.length} mode={mode} />
          </div>
          {coverage.isError ? <StatePanel kind="error" detail={coverage.error.message} onRetry={() => void coverage.refetch()} /> : null}

          <section aria-labelledby="map-heading" className="flex flex-col gap-3">
            <h2 id="map-heading" className="text-xl font-semibold">{t('pages.geography.mapHeading')}</h2>
            <Basemap label={t('pages.geography.mapLabel')} />
            <ul className="flex max-w-4xl list-disc flex-col gap-1 ps-5 text-xs text-muted-foreground" data-testid="map-notes">
              <li>{language === 'ar' ? registry.data.geometry.ar : registry.data.geometry.en}</li>
              <li>{t('pages.geography.mapBoundariesNote')}</li>
              <li>{t('pages.geography.mapTableNote')}</li>
              <li>{t('pages.geography.noDirections')}</li>
            </ul>
          </section>

          <section aria-labelledby="compare-heading" className="flex flex-col gap-3">
            <h2 id="compare-heading" className="text-xl font-semibold">{t('compare.title')}</h2>
            <GovernorateComparison mode={mode} indicators={governorateIndicators} />
          </section>

          <section aria-labelledby="areas-heading" className="flex flex-col gap-4">
            <h2 id="areas-heading" className="text-xl font-semibold">{t('pages.geography.areasHeading')}</h2>
            <FilterBar onReset={reset} canReset={active} activeCount={count}>
              <SelectField label={t('pages.geography.level')} value={level} onValueChange={(v) => setLevel(v as (typeof LEVELS)[number])}
                options={LEVELS.map((l) => ({ value: l, label: l === 'all' ? t('filters.all') : t(`pages.geography.levels.${l}`) }))}
                data-testid="filter-level" />
              <SelectField label={t('pages.geography.governorate')} value={gov} onValueChange={setGov}
                options={[{ value: 'all', label: t('filters.all') }, ...governorates.map((g) => ({ value: g.code, label: areaName(g, language) }))]}
                data-testid="filter-governorate" />
              <SelectField label={t('pages.geography.statisticalColumn')} value={cov} onValueChange={(v) => setCov(v as (typeof COVERAGE_FILTER)[number])}
                options={COVERAGE_FILTER.map((c) => ({ value: c, label: t(`pages.geography.coverageFilter.${c}`) }))}
                data-testid="filter-coverage" />
              <div className="flex min-w-0 flex-col gap-1.5">
                <label htmlFor={searchId} className="text-xs font-medium text-muted-foreground">{t('pages.geography.search')}</label>
                <input id={searchId} type="search" value={search} onChange={(e) => setSearch(e.target.value)}
                  className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm" data-testid="area-search" />
              </div>
            </FilterBar>

            <div ref={detailRef} tabIndex={-1} className="outline-none" aria-live="polite">
              {selectedArea ? (
                <SelectedArea area={selectedArea} parent={selectedArea.parent_code ? byCode.get(selectedArea.parent_code) : undefined}
                  registry={registry.data} mode={mode} onClear={() => setSelected(NONE)} />
              ) : (
                <p className="text-sm text-muted-foreground">{t('pages.geography.selectHint')}</p>
              )}
            </div>

            {visible.length === 0 ? (
              <StatePanel kind="empty" onReset={() => { reset(); setSearch(''); }} />
            ) : (
              <AreaTable areas={visible} byCode={byCode} coverage={coverage.data} selected={selected} onSelect={select} />
            )}
          </section>
        </div>
      ) : null}
    </>
  );
}
