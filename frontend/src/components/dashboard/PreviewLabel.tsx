import { Eye, RefreshCw, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useRecheckBackend } from '@/api/backendStatus';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

/** Marks one card, chart, table or source as preview-only data. Text, not colour alone. */
export function PreviewBadge() {
  const { t } = useTranslation();
  return (
    <Badge variant="synthetic" data-testid="preview-label">
      <Eye aria-hidden="true" />
      {t('dashboard.preview.badge')}
    </Badge>
  );
}

/** Page-level statement that the API is unavailable and what is shown instead. */
export function PreviewNotice() {
  const { t } = useTranslation();
  const recheck = useRecheckBackend();
  return (
    <section role="status" data-testid="preview-notice"
      className="flex flex-col gap-3 rounded-lg border border-synthetic-border bg-synthetic p-4 text-synthetic-foreground sm:flex-row sm:items-center sm:p-5">
      <TriangleAlert aria-hidden="true" className="size-5 shrink-0" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <h2 className="font-semibold">{t('dashboard.preview.title')}</h2>
        <p className="text-sm leading-relaxed">{t('dashboard.preview.body')}</p>
      </div>
      <Button type="button" variant="outline" size="sm" onClick={recheck} className="shrink-0 self-start sm:self-center">
        <RefreshCw aria-hidden="true" />
        {t('dashboard.preview.retry')}
      </Button>
    </section>
  );
}
