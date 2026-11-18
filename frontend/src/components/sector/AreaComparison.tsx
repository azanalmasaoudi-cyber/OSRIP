import { MapPinned } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { adapterKind } from '@/api/config';
import { useAreaComparison } from '@/api/library';
import { StatePanel } from '@/components/common/StatePanel';
import { DashboardCard } from '@/components/workspace/DashboardPanels';
import { comparisonDataset } from '@/components/workspace/datasets';
import { DatasetView } from '@/components/workspace/DatasetView';
import { useDataMode } from '@/state/useDataMode';

/** Governorates side by side for one indicator, only where the coverage supports a valid
 * comparison (otherwise it says why). Drawn as a table, with a chart on request. */
export function AreaComparison({ indicator, frequency }: { indicator: string | null; frequency: string }) {
  const { t } = useTranslation();
  const [mode] = useDataMode();
  const comparison = useAreaComparison(mode, indicator, null, null, frequency);
  const dataset = comparisonDataset(comparison.data, mode);
  return (
    <DashboardCard title={t('workspace.comparison.heading')} labelledBy="sector-area-comparison" testId="workspace-geography"
      icon={<MapPinned aria-hidden="true" className="size-4 text-primary" />}>
      <p className="text-xs font-medium">{t('workspace.geography.heading')}</p>
      {adapterKind !== 'http' ? <StatePanel kind="not_implemented" />
        : !indicator ? null
          : comparison.isPending ? <StatePanel kind="loading" skeleton="lines" />
            : comparison.isError ? <StatePanel kind="error" error={comparison.error} onRetry={() => void comparison.refetch()} />
              : dataset ? (
                <>
                  <p className="text-xs text-muted-foreground">{t('workspace.geography.note')}</p>
                  <DatasetView dataset={dataset} state="reference" chartsOnRequest />
                </>
              ) : (
                <div role="status" data-testid="workspace-geography-none" className="rounded-md border border-dashed border-border-strong/40 p-3 text-xs">
                  <p className="font-medium">{t('workspace.geography.noneTitle')}</p>
                  <p className="text-muted-foreground">
                    {comparison.data?.status === 'not_comparable' ? t('workspace.geography.notComparable') : t('workspace.geography.none')}
                  </p>
                  <p className="mt-2 text-muted-foreground">{t('workspace.geography.noBoundaries')}</p>
                </div>
              )}
    </DashboardCard>
  );
}
