import { FlaskConical, Trash2 } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useMe } from '@/api/auth';
import { ApiRequestError } from '@/api/client';
import { adapterKind } from '@/api/config';
import { useAreaCoverage, useAreaRegistry } from '@/api/geography';
import { useCommodities } from '@/api/queries';
import { STUDY_KINDS, useDeleteStudy, useMyStudies, useRunStudy, useStudy, type StudyKind } from '@/api/studies';
import { PageHeader } from '@/components/common/PageHeader';
import { StatePanel } from '@/components/common/StatePanel';
import { CreateStudy, JobView, MyJobs } from '@/components/studies/ResearchJobs';
import { StudyView } from '@/components/studies/StudyView';
import { Button } from '@/components/ui/button';
import { SelectField } from '@/components/ui/select';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * Studies: pick one of the allowlisted analyses, fill its typed parameters and let the
 * server run it from published observations. The result opens at its own address
 * (/studies/:id) so it can be reopened, exported and reproduced.
 */

type IndicatorOption = { code: string; name_en: string; name_ar: string; frequency: string; first_period: string; last_period: string };

const NEEDS_AREA: readonly StudyKind[] = ['trend', 'growth', 'seasonal_profile', 'scenario', 'forecast_eligibility', 'programme_assessment'];
const NEEDS_COMMODITY: readonly StudyKind[] = ['import_dependence', 'partner_concentration'];
const PERIOD_KINDS = ['annual', 'year_to_date', 'quarterly', 'monthly'] as const;

function NumberField({ label, value, onChange, step = '1', testId }: {
  label: string; value: string; onChange: (v: string) => void; step?: string; testId?: string;
}) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium text-muted-foreground">{label}</label>
      <input id={id} type="number" inputMode="decimal" step={step} value={value} onChange={(e) => onChange(e.target.value)} dir="ltr"
        className="h-10 w-full rounded-md border border-border-strong bg-card px-3 text-sm" data-testid={testId} />
    </div>
  );
}

function years(first?: string, last?: string): string[] {
  if (!first || !last) return [];
  const out: string[] = [];
  for (let y = Number(last.slice(0, 4)); y >= Number(first.slice(0, 4)); y--) out.push(String(y));
  return out;
}

function StudyForm() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const navigate = useNavigate();
  const to = usePreservedSearch();
  const registry = useAreaRegistry();
  const coverage = useAreaCoverage(mode);
  const commodities = useCommodities(mode);
  const run = useRunStudy();
  const objectiveId = useId();

  const [kind, setKind] = useState<StudyKind>('trend');
  const [area, setArea] = useState('OM');
  const [indicator, setIndicator] = useState('');
  const [periodKind, setPeriodKind] = useState<string>('annual');
  const [commodity, setCommodity] = useState('');
  const [year, setYear] = useState('');
  const [fromYear, setFromYear] = useState('');
  const [toYear, setToYear] = useState('');
  const [growth, setGrowth] = useState('3');
  const [oneOff, setOneOff] = useState('0');
  const [horizon, setHorizon] = useState('5');
  const [objective, setObjective] = useState('');
  const [baselineYear, setBaselineYear] = useState('');
  const [targetValue, setTargetValue] = useState('');
  const [targetYear, setTargetYear] = useState(String(new Date().getUTCFullYear() + 5));

  const areaName = useMemo(() => new Map((registry.data?.areas ?? []).map((a) => [a.code, language === 'ar' ? a.name_ar : a.name_en])), [registry.data, language]);
  const levels = useMemo(() => new Map((registry.data?.areas ?? []).map((a) => [a.code, a.level])), [registry.data]);
  const covered = useMemo(() => coverage.data?.areas ?? {}, [coverage.data]);
  const areaCodes = Object.keys(covered).sort((a, b) => (a === 'OM' ? -1 : b === 'OM' ? 1 : (areaName.get(a) ?? a).localeCompare(areaName.get(b) ?? b, language)));

  const indicatorRows: IndicatorOption[] = useMemo(() => {
    if (kind === 'compare_regions') {
      return Object.entries(covered).filter(([code]) => levels.get(code) === 'governorate').flatMap(([, c]) => c.indicators);
    }
    if (kind === 'data_quality') return Object.values(covered).flatMap((c) => c.indicators);
    return covered[area]?.indicators ?? [];
  }, [kind, covered, area, levels]);
  const indicatorOptions = [...new Map(indicatorRows.map((i) => [i.code, i])).values()].sort((a, b) => a.code.localeCompare(b.code));
  const chosen = indicatorOptions.find((i) => i.code === indicator) ?? indicatorOptions[0];
  const chosenCode = chosen?.code ?? '';
  const frequencies = indicatorRows.filter((i) => i.code === chosenCode).map((i) => i.frequency)
    .filter((f): f is (typeof PERIOD_KINDS)[number] => (PERIOD_KINDS as readonly string[]).includes(f));
  const annual = indicatorRows.find((i) => i.code === chosenCode && i.frequency === 'annual');
  const annualYears = years(annual?.first_period, annual?.last_period);
  const effectivePeriodKind = frequencies.includes(periodKind as (typeof PERIOD_KINDS)[number]) ? periodKind : (frequencies[0] ?? 'annual');

  // Year choices stay inside the chosen series' published range.
  const inRange = (value: string, fallback: string | undefined) => (annualYears.includes(value) ? value : (fallback ?? ''));
  const first = inRange(fromYear, annualYears.at(-1));
  const last = inRange(toYear, annualYears[0]);
  const baseline = inRange(baselineYear, annualYears.at(-1));

  const params = (): Record<string, unknown> => {
    switch (kind) {
      case 'trend': return { indicator: chosenCode, area, period_kind: effectivePeriodKind };
      case 'growth': return { indicator: chosenCode, area, from_year: Number(first), to_year: Number(last) };
      case 'compare_regions': return { indicator: chosenCode, period_kind: effectivePeriodKind };
      case 'seasonal_profile': return { indicator: chosenCode, area };
      case 'import_dependence':
      case 'partner_concentration': return { commodity, ...(year ? { year: Number(year) } : {}) };
      case 'data_quality': return { indicator: chosenCode };
      case 'scenario': return { indicator: chosenCode, area, growth_pct: growth, years: Number(horizon), one_off_pct: oneOff };
      case 'forecast_eligibility': return { indicator: chosenCode, area };
      case 'programme_assessment': return {
        indicator: chosenCode, area, objective, baseline_year: Number(baseline), target_value: targetValue, target_year: Number(targetYear),
      };
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run.mutate({ kind, data_mode: mode, params: params() }, {
      onSuccess: (stored) => void navigate(to(`/studies/${stored.id}`)),
    });
  };

  const commodityOptions = (commodities.data ?? []).map((c) => ({ value: c.code, label: `${c.name[language]} (${c.code})` }));
  const missingCommodity = NEEDS_COMMODITY.includes(kind) && !commodity;
  const missingIndicator = !NEEDS_COMMODITY.includes(kind) && !chosenCode;
  const missingObjective = kind === 'programme_assessment' && (objective.trim().length < 3 || !targetValue);

  return (
    <form onSubmit={submit} className="surface-card flex flex-col gap-4 p-4 sm:p-5" data-testid="study-form" aria-labelledby="study-form-heading">
      <h2 id="study-form-heading" className="text-lg font-semibold">{t('studies.formHeading')}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <SelectField label={t('studies.kind')} value={kind} onValueChange={(v) => setKind(v as StudyKind)} data-testid="study-kind"
          options={STUDY_KINDS.map((k) => ({ value: k, label: t(`studies.kinds.${k}`) }))} />
        {NEEDS_AREA.includes(kind) ? (
          <SelectField label={t('studies.area')} value={area} onValueChange={setArea} data-testid="study-area"
            options={(areaCodes.length ? areaCodes : ['OM']).map((c) => ({ value: c, label: areaName.get(c) ?? c }))} />
        ) : null}
        {NEEDS_COMMODITY.includes(kind) ? (
          <>
            <SelectField label={t('studies.commodity')} value={commodity} onValueChange={setCommodity} data-testid="study-commodity"
              options={[{ value: '', label: '—' }, ...commodityOptions]} />
            <NumberField label={`${t('studies.year')} (${t('studies.yearLatest')})`} value={year} onChange={setYear} testId="study-year" />
          </>
        ) : (
          <SelectField label={t('studies.indicator')} value={chosenCode} onValueChange={setIndicator} data-testid="study-indicator" disabled={!indicatorOptions.length}
            options={indicatorOptions.length ? indicatorOptions.map((i) => ({ value: i.code, label: language === 'ar' ? i.name_ar : i.name_en })) : [{ value: '', label: t('studies.noIndicators') }]} />
        )}
        {(kind === 'trend' || kind === 'compare_regions') && frequencies.length > 1 ? (
          <SelectField label={t('studies.periodKind')} value={effectivePeriodKind} onValueChange={setPeriodKind}
            options={frequencies.map((f) => ({ value: f, label: t(`studies.code.${f}`) }))} />
        ) : null}
        {kind === 'growth' ? (
          <>
            <SelectField label={t('studies.fromYear')} value={first} onValueChange={setFromYear} options={annualYears.map((y) => ({ value: y, label: y }))} data-testid="study-from" />
            <SelectField label={t('studies.toYear')} value={last} onValueChange={setToYear} options={annualYears.map((y) => ({ value: y, label: y }))} data-testid="study-to" />
          </>
        ) : null}
        {kind === 'scenario' ? (
          <>
            <NumberField label={t('studies.growthPct')} value={growth} onChange={setGrowth} step="0.1" testId="study-growth" />
            <NumberField label={t('studies.oneOffPct')} value={oneOff} onChange={setOneOff} step="0.1" />
            <NumberField label={t('studies.years')} value={horizon} onChange={setHorizon} />
          </>
        ) : null}
        {kind === 'programme_assessment' ? (
          <>
            <div className="flex min-w-0 flex-col gap-1.5 sm:col-span-2 lg:col-span-3">
              <label htmlFor={objectiveId} className="text-xs font-medium text-muted-foreground">{t('studies.objective')}</label>
              <input id={objectiveId} value={objective} onChange={(e) => setObjective(e.target.value)} maxLength={300} dir="auto"
                className="h-10 w-full rounded-md border border-border-strong bg-card px-3 text-sm" data-testid="study-objective" />
            </div>
            <SelectField label={t('studies.baselineYear')} value={baseline} onValueChange={setBaselineYear} options={annualYears.map((y) => ({ value: y, label: y }))} />
            <NumberField label={t('studies.targetValue')} value={targetValue} onChange={setTargetValue} step="any" testId="study-target" />
            <NumberField label={t('studies.targetYear')} value={targetYear} onChange={setTargetYear} />
          </>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={run.isPending || missingCommodity || missingIndicator || missingObjective} data-testid="study-run">
          <FlaskConical aria-hidden="true" className="size-4" />{run.isPending ? t('studies.running') : t('studies.run')}
        </Button>
        {run.isError ? <p className="text-sm text-destructive" role="alert">{t('studies.failed', { message: run.error.message })}</p> : null}
      </div>
    </form>
  );
}

function MyStudies() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const me = useMe();
  const signedIn = Boolean(me.data?.authenticated);
  const mine = useMyStudies(signedIn);
  const remove = useDeleteStudy();
  const to = usePreservedSearch();
  const navigate = useNavigate();
  const { studyId } = useParams();
  return (
    <section aria-labelledby="my-studies" className="surface-card flex flex-col gap-3 p-4 sm:p-5" data-testid="my-studies">
      <h2 id="my-studies" className="text-lg font-semibold">{t('studies.mine')}</h2>
      {!signedIn ? <p className="text-sm text-muted-foreground">{t('studies.signInForList')}</p>
        : mine.isPending ? <StatePanel kind="loading" skeleton="lines" />
          : !mine.data?.length ? <p className="text-sm text-muted-foreground">{t('studies.mineEmpty')}</p>
            : (
              <ul className="flex flex-col divide-y divide-border">
                {mine.data.map((s) => (
                  <li key={s.id} className="flex items-center gap-2 py-2 text-sm">
                    <Link to={to(`/studies/${s.id}`)} className="min-w-0 flex-1 truncate text-primary underline underline-offset-2">{s.title[language]}</Link>
                    <span className="hidden text-xs text-muted-foreground sm:inline">{t(`studies.kinds.${s.kind}`)}</span>
                    <Button type="button" variant="ghost" size="sm" aria-label={`${t('studies.delete')}: ${s.title[language]}`}
                      onClick={() => remove.mutate(s.id, { onSuccess: () => { if (studyId === s.id) void navigate(to('/studies')); } })}>
                      <Trash2 aria-hidden="true" className="size-4" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
    </section>
  );
}

function OpenStudy({ id }: { id: string }) {
  const { t } = useTranslation();
  const study = useStudy(id);
  const ref = useRef<HTMLDivElement>(null);
  // Move focus to the new result so keyboard and screen-reader users land on it.
  useEffect(() => { if (study.data) ref.current?.focus(); }, [study.data?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (study.isPending) return <StatePanel kind="loading" skeleton="cards" />;
  if (study.isError) {
    const gone = study.error instanceof ApiRequestError && study.error.status === 404;
    return <StatePanel kind="error" detail={gone ? t('studies.notFound') : study.error.message} />;
  }
  return (
    <div ref={ref} tabIndex={-1} className="surface-card p-4 outline-none sm:p-5">
      <StudyView stored={study.data} />
    </div>
  );
}

export function StudiesPage() {
  const { t } = useTranslation();
  const { studyId } = useParams();
  const [params] = useSearchParams();
  const jobId = params.get('job');
  if (adapterKind !== 'http') {
    return (
      <>
        <PageHeader title={t('studies.title')} intro={t('studies.intro')} />
        <StatePanel kind="not_implemented"><p className="text-sm text-muted-foreground">{t('studies.requiresApi')}</p></StatePanel>
      </>
    );
  }
  return (
    <>
      <PageHeader title={t('studies.title')} intro={t('studies.intro')} />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex min-w-0 flex-col gap-6">
          <CreateStudy />
          {jobId ? <JobView id={jobId} /> : null}
          <StudyForm />
          {studyId ? <OpenStudy id={studyId} /> : null}
        </div>
        <div className="flex flex-col gap-6">
          <MyJobs activeId={jobId} />
          <MyStudies />
        </div>
      </div>
    </>
  );
}
