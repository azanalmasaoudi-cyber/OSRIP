import { useTranslation } from 'react-i18next';

import { useAssistantStatus } from '@/api/assistant';
import { Badge } from '@/components/ui/badge';

/** The answer service in a few words: working, failing (data-based reports meanwhile),
 * set up but untested, or not set up (record lookup). */
export function ServiceChip() {
  const { t } = useTranslation();
  const status = useAssistantStatus();
  if (!status.data) return null;
  const state = !status.data.configured ? 'not_configured' : (status.data.health?.state ?? 'untested');
  const variant = state === 'ok' ? 'verified' : state === 'failing' || state === 'not_configured' ? 'sand' : 'muted';
  return (
    <Badge variant={variant} data-testid="assistant-service" data-state={state}
      title={state === 'failing' && status.data.health?.category ? t(`assistant.health.category.${status.data.health.category}`, { defaultValue: '' }) : undefined}>
      {t(`assistant.health.${state}`)}
    </Badge>
  );
}
