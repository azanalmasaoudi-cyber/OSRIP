import { Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { CalculationCard } from './CalculationCard';
import { analysisExportUrl, observationsExportUrl, useAnalysis, type SectionFilters } from '@/api/analysis';
import { StatePanel } from '@/components/common/StatePanel';
import { buttonVariants } from '@/components/ui/button';
import type { DataMode, SectionCode } from '@/domain/types';

/** Calculations for one section, driven by the same filters as its tables, charts and exports. */
export function AnalysisPanel({ section, mode, filters, headingLevel = 2 }: {
  section: SectionCode; mode: DataMode; filters: SectionFilters; headingLevel?: 2 | 3;
}) {
  const Heading = `h${headingLevel}` as const;
  const { t } = useTranslation();
  const query = useAnalysis(section, mode, filters);

  let body;
  if (query.isPending) body = <StatePanel kind="loading" skeleton="lines" />;
  else if (query.isError) body = <StatePanel kind="error" detail={query.error.message} onRetry={() => void query.refetch()} />;
  else if (query.data.calculations.length === 0) body = <StatePanel kind="empty"><p className="text-sm text-muted-foreground">{t('analysis.none')}</p></StatePanel>;
  else {
    body = (
      <div className="grid grid-cols-[minmax(0,1fr)] gap-5" data-testid="calculations">
        {query.data.calculations.map((calc) => <CalculationCard key={calc.id} calc={calc} />)}
      </div>
    );
  }

  return (
    <section aria-labelledby={`calc-${section}`} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Heading id={`calc-${section}`} className="text-xl font-semibold">{t('analysis.heading')}</Heading>
          <p className="max-w-3xl text-sm text-muted-foreground">{t('analysis.intro')}</p>
        </div>
        <ExportLinks section={section} mode={mode} filters={filters} only="calculations" />
      </div>
      {body}
    </section>
  );
}

export function ExportLinks({ section, mode, filters, only }: {
  section: SectionCode; mode: DataMode; filters: SectionFilters; only?: 'observations' | 'calculations';
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-2 print:hidden">
      {only !== 'calculations' ? (
      <a href={observationsExportUrl(section, mode, filters)} download className={buttonVariants({ variant: 'outline', size: 'sm' })}
        data-testid="export-observations">
        <Download aria-hidden="true" />
        {t('analysis.exportObservations')}
      </a>
      ) : null}
      {only !== 'observations' ? (
      <a href={analysisExportUrl(section, mode, filters)} download className={buttonVariants({ variant: 'outline', size: 'sm' })}
        data-testid="export-calculations">
        <Download aria-hidden="true" />
        {t('analysis.exportCalculations')}
      </a>
      ) : null}
    </div>
  );
}
