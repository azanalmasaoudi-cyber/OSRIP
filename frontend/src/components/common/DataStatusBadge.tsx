import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';

// Which kind of figure something is (set by the server on every evidence item and dataset),
// so approved official observations are never confused with web findings, calculations,
// forecasts, scenarios or demonstration data.
const VARIANT = {
  approved_official: 'verified',
  synthetic_demonstration: 'synthetic',
  unreviewed_external: 'sand',
  calculated: 'outline',
  model_forecast: 'outline',
  assumption_scenario: 'sand',
  reference: 'muted',
} as const;
export type DataStatus = keyof typeof VARIANT;

export function DataStatusBadge({ status, showReference = false }: { status: unknown; showReference?: boolean }) {
  const { t } = useTranslation();
  if (typeof status !== 'string' || !(status in VARIANT) || (status === 'reference' && !showReference)) return null;
  const s = status as DataStatus;
  return <Badge variant={VARIANT[s]} data-testid="data-status" data-status={s}>{t(`assistant.dataStatus.${s}`)}</Badge>;
}
