import { FileText } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { DataModeBadge } from './DataModeBadge';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import type { Series } from '@/domain/types';
import { FREQUENCY_KEY, VALUE_TYPE_KEY } from '@/i18n/keys';
import { useAppLanguage } from '@/lib/useAppLanguage';

/** Button + dialog with the full provenance of one series. */
export function SourceDetailsButton({ series }: { series: Series }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [open, setOpen] = useState(false);
  const notRecorded = <span className="text-muted-foreground">{t('table.notRecorded')}</span>;

  const rows: Array<[string, ReactNode]> = [
    [t('table.definition'), series.definition[language]],
    [t('table.unit'), series.unit.label[language]],
    [t('table.valueType'), t(VALUE_TYPE_KEY[series.valueType])],
    [t('table.dataMode'), <DataModeBadge key="mode" mode={series.dataMode} />],
    [t('table.source'), series.source.title],
    [t('table.publisher'), series.source.publisher ?? t('table.noPublisher')],
    [t('table.version'), <span key="v" dir="ltr">{series.source.versionLabel}</span>],
    [t('table.accessDate'), series.source.accessDate ?? notRecorded],
    [
      t('table.link'),
      series.source.url ? (
        <a key="url" href={series.source.url} className="break-all text-primary underline" dir="ltr" rel="noreferrer" target="_blank">
          {series.source.url}
        </a>
      ) : (
        notRecorded
      ),
    ],
  ];
  if (series.source.sourceCode) {
    rows.push([t('provenance.sourceCode'), <span key="sc" dir="ltr">{series.source.sourceCode}</span>]);
  }
  if (series.source.sourceRole) rows.push([t('provenance.sourceRole'), series.source.sourceRole.replaceAll('_', ' ')]);
  if (series.frequency) rows.push([t('table.frequency'), t(FREQUENCY_KEY[series.frequency])]);
  if (series.area?.level === 'reporting_group') rows.push([t('provenance.reportingGroup'), t('provenance.reportingGroupNote')]);
  if (series.source.referencePeriod) rows.push([t('table.referencePeriod'), series.source.referencePeriod]);
  if (series.source.geographicCoverage) rows.push([t('table.coverage'), series.source.geographicCoverage]);
  if (series.source.reuseConditions) rows.push([t('table.reuseConditions'), series.source.reuseConditions]);
  if (series.source.publishedAt) {
    rows.push([t('table.publishedAt'), <span key="p" dir="ltr">{series.source.publishedAt.slice(0, 10)}</span>]);
  }
  if (series.note) rows.push([t('table.note'), series.note[language]]);

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} data-testid="source-details-button">
        <FileText aria-hidden="true" />
        {t('table.showSource')}
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} title={series.name[language]} description={t('table.showSource')}>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-[minmax(8rem,auto)_1fr]" data-testid="source-details">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="font-medium text-muted-foreground">{label}</dt>
              <dd className="mb-2 sm:mb-0">{value}</dd>
            </div>
          ))}
        </dl>
      </Dialog>
    </>
  );
}
