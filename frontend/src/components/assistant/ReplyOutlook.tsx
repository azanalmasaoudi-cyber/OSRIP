import { Telescope } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { StructuredReply } from '@/api/assistant';
import { OutlookList } from '@/components/sector/SectorOutlook';

/** The official outlook items an answer used, each labelled with its evidence class (forecast,
 * target, plan, option): kept apart from the answer's observed figures. */
export function ReplyOutlook({ outlook }: { outlook: NonNullable<StructuredReply['outlook']> }) {
  const { t } = useTranslation();
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-dashed border-border-strong/60 bg-card p-4" data-testid="reply-outlook"
      aria-label={t('outlook.heading')}>
      <p className="flex items-center gap-2 text-sm font-semibold"><Telescope aria-hidden="true" className="size-4 text-primary" />{t('outlook.heading')}</p>
      <p className="text-xs text-muted-foreground">{t('outlook.lead')}</p>
      <OutlookList items={outlook.items} />
    </section>
  );
}
