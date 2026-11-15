import { useTranslation } from 'react-i18next';

import { problemOf } from '@/api/problems';

/**
 * In place of a figure that is not shown: why. A failed request names its reason in a few words
 * (server not connected, database unavailable, ...); with no failure, the figure simply has not
 * been published. Never a zero or an estimate.
 */
export function NoFigure({ error }: { error?: unknown }) {
  const { t } = useTranslation();
  if (error) {
    const { kind } = problemOf(error);
    return <span className="text-destructive" data-state="error" data-problem={kind}>{t(`problems.${kind}.short`)}</span>;
  }
  return <span data-state="data-unavailable">{t('states.noPublishedValue')}</span>;
}
