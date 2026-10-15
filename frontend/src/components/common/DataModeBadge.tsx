import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import type { DataMode } from '@/domain/types';
import { DATA_MODE_KEY } from '@/i18n/keys';

/** Mode label shown on every table, chart and card (booklet 3.4). Text, not colour alone. */
export function DataModeBadge({ mode }: { mode: DataMode }) {
  const { t } = useTranslation();
  return (
    <Badge variant={mode === 'synthetic' ? 'synthetic' : 'verified'} data-testid="data-mode-badge">
      {t(DATA_MODE_KEY[mode])}
    </Badge>
  );
}
