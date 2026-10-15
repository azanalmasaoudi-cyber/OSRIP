import { motion } from 'motion/react';
import { useTranslation } from 'react-i18next';

import type { Dataset } from '@/api/studyEvents';
import { DataStatusBadge } from '@/components/common/DataStatusBadge';
import { StudyBarChart, StudyHeatmap, StudyLineChart } from '@/components/studies/StudyCharts';
import { StudyTable, useLabels } from '@/components/studies/StudyView';
import { Badge } from '@/components/ui/badge';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/**
 * One validated dataset: its charts and its table are drawn from exactly the same rows, so
 * they can never disagree. ``highlight`` holds the row ids a spoken sentence is about (an
 * empty set with ``whole`` marks the whole table). ``state`` says whether the result is still
 * provisional (study in progress), final (the answer rests on it) or was not used.
 */
export type DatasetState = 'provisional' | 'final' | 'unused' | 'stopped' | 'reference';

export function DatasetView({ dataset, state, highlight, whole = false, headingLevel = 3 }: {
  dataset: Dataset;
  state: DatasetState;
  highlight?: ReadonlySet<string>;
  whole?: boolean;
  headingLevel?: 3 | 4;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const labels = useLabels(language);
  const H = headingLevel === 3 ? 'h3' : 'h4';
  const rows = dataset.table.rows;
  const rowIds = dataset.rows_meta.map((m) => m.row_id);
  const indexes = new Set(rowIds.flatMap((id, i) => (highlight?.has(id) ? [i] : [])));
  const columns = dataset.table.columns.filter((c) => !c.key.endsWith('_ar'));
  const title = dataset.title[language];
  const lit = whole || indexes.size > 0;

  return (
    <motion.section
      layout="position"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      aria-label={title}
      data-testid="dataset"
      data-dataset={dataset.dataset_id}
      data-state={state}
      data-highlighted={lit ? 'true' : undefined}
      className={cn(
        'flex flex-col gap-3 rounded-lg border bg-card p-4 transition-shadow motion-reduce:transition-none',
        state === 'provisional' || state === 'stopped' ? 'border-dashed border-sand' : 'border-border',
        lit && 'shadow-[0_0_0_3px_var(--copper)]',
      )}
    >
      <header className="flex flex-col gap-1">
        <p className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="font-mono text-muted-foreground" dir="ltr">{dataset.dataset_id}</span>
          <DataStatusBadge status={dataset.data_status} />
          <Badge variant={state === 'final' ? 'verified' : state === 'reference' ? 'outline' : 'sand'} data-testid="dataset-state">
            {t(`workspace.dataset.${state}`)}
          </Badge>
          <span className="text-muted-foreground">{t(`workspace.origin.${dataset.origin}`)}</span>
        </p>
        <H className="font-semibold">{title}</H>
        {dataset.subtitle ? <p className="text-sm text-muted-foreground">{dataset.subtitle[language]}</p> : null}
        {state === 'provisional' ? <p className="text-xs text-sand-foreground" role="note">{t('workspace.dataset.provisionalNote')}</p> : null}
      </header>
      {dataset.charts.map((chart, i) => (
        <div key={i} className="rounded-md border border-border/70 p-3" data-testid="dataset-chart" data-chart={chart.type}>
          {chart.type === 'line' ? <StudyLineChart chart={chart} rows={rows} labelFor={labels.text} highlight={indexes} />
            : chart.type === 'bar' ? <StudyBarChart chart={chart} rows={rows} labelFor={labels.text} highlight={indexes} />
              : <StudyHeatmap chart={chart} rows={rows} labelFor={labels.text} />}
          <p className="mt-2 text-xs text-muted-foreground">{t('workspace.dataset.sameRows')}</p>
        </div>
      ))}
      <StudyTable columns={columns} rows={rows} language={language} rowIds={rowIds} highlighted={highlight} caption={title}
        filterAlways={rows.length > 3} />
      {dataset.study ? (
        <details className="text-sm" data-testid="dataset-study">
          <summary className="cursor-pointer font-medium">{t('workspace.dataset.studyNotes')}</summary>
          <div className="mt-2 flex flex-col gap-2 text-muted-foreground">
            {dataset.study.findings.length ? (
              <ul className="list-disc ps-5">{dataset.study.findings.map((f, i) => <li key={i}>{f[language]}</li>)}</ul>
            ) : null}
            <p><span className="font-medium text-foreground">{t('studies.method')}:</span> {dataset.study.method[language]}</p>
            {dataset.study.assumptions.length ? (
              <p><span className="font-medium text-foreground">{t('studies.assumptions')}:</span> {dataset.study.assumptions.map((a) => a[language]).join(' ')}</p>
            ) : null}
            {dataset.study.limitations.length ? (
              <p><span className="font-medium text-foreground">{t('studies.limitations')}:</span> {dataset.study.limitations.map((a) => a[language]).join(' ')}</p>
            ) : null}
          </div>
        </details>
      ) : null}
    </motion.section>
  );
}
