import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ChartType, DatasetView } from '@/api/datasets';
import {
  StudyBarChart,
  StudyColumnChart,
  StudyHeatmap,
  StudyLineChart,
  StudyPieChart,
  StudyScatterChart,
} from '@/components/studies/StudyCharts';
import { Segmented } from '@/components/ui/segmented';
import { useAppLanguage } from '@/lib/useAppLanguage';

const TYPE_KEY = {
  line: 'datasets.chartType.line',
  bar: 'datasets.chartType.bar',
  pie: 'datasets.chartType.pie',
  scatter: 'datasets.chartType.scatter',
  heatmap: 'datasets.chartType.heatmap',
} as const satisfies Record<ChartType, string>;

/**
 * One chart chosen by the server for a table it computed, with the other chart types that
 * remain valid for the same table (for example bars for a time series, or a pie for shares of
 * a total) as a switch. The table below the chart holds the same values for every reader.
 */
export function ViewChart({ view }: { view: DatasetView }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [type, setType] = useState<ChartType>(view.chart.type);
  const chart = { ...view.chart, type };
  const rows = view.table.rows;
  const labelFor = (row: Record<string, string | null>, key: string) => row[key] ?? '';
  const xColumn = view.table.columns.find((c) => c.key === chart.x);
  const byPeriod = xColumn?.kind === 'period';

  let figure;
  if (type === 'line') figure = <StudyLineChart chart={chart} rows={rows} labelFor={labelFor} />;
  else if (type === 'pie') figure = <StudyPieChart chart={chart} rows={rows} labelFor={labelFor} />;
  else if (type === 'scatter') figure = <StudyScatterChart chart={chart} rows={rows} xLabel={xColumn?.label[language] ?? ''} />;
  else if (type === 'heatmap') figure = <StudyHeatmap chart={chart} rows={rows} labelFor={labelFor} />;
  else if (byPeriod || chart.series.length > 1) figure = <StudyColumnChart chart={chart} rows={rows} labelFor={labelFor} />;
  else figure = <StudyBarChart chart={chart} rows={rows} labelFor={labelFor} />;

  return (
    <div className="flex flex-col gap-3" data-testid={`dataset-view-${view.id}`} data-chart-type={type}>
      {view.alternatives.length > 1 ? (
        <Segmented label={t('datasets.chartTypeLabel')} value={type} className="w-fit"
          options={view.alternatives.map((a) => ({ value: a, label: t(TYPE_KEY[a]) }))}
          onChange={setType} testId={`chart-type-${view.id}`} />
      ) : null}
      {figure}
      {view.note ? <p className="text-xs text-muted-foreground">{view.note[language]}</p> : null}
      <details className="text-sm">
        <summary className="cursor-pointer text-xs font-medium text-primary">{t('datasets.showChartTable')}</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-max text-sm">
            <caption className="sr-only">{view.title[language]}</caption>
            <thead>
              <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                {view.table.columns.map((c) => (
                  <th key={c.key} scope="col" className={c.kind === 'number' ? 'px-2 py-1 text-end font-medium' : 'px-2 py-1 text-start font-medium'}>
                    {c.label[language]}{c.unit ? ` (${language === 'ar' ? c.unit.label_ar : c.unit.label_en})` : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-border/60">
                  {view.table.columns.map((c) => (
                    <td key={c.key} className={c.kind === 'number' ? 'px-2 py-1 text-end tabular-nums' : 'px-2 py-1'} dir={c.kind === 'number' ? 'ltr' : 'auto'}>
                      {r[c.key] ?? <span className="text-muted-foreground">{t('datasets.table.missing')}</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
