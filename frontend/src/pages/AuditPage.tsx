import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { hasPermission, useMe } from '@/api/auth';
import { apiJson } from '@/api/client';
import { adapterKind } from '@/api/config';
import { PageHeader } from '@/components/common/PageHeader';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { DataTable, type Column } from '@/components/ui/data-table';
import { SelectField } from '@/components/ui/select';
import { formatDateTime } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

const eventSchema = z.object({
  id: z.number(),
  occurred_at: z.string(),
  actor: z.string().nullable(),
  action: z.string(),
  entity_type: z.string().nullable(),
  entity_id: z.string().nullable(),
  outcome: z.string().nullable(),
  metadata: z.unknown(),
});
type AuditEvent = z.infer<typeof eventSchema>;

/** The latest 500 audit events (the server's limit), for people who may read the audit log. */
export function AuditPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const me = useMe();
  const allowed = hasPermission(me.data, 'audit.read');
  const events = useQuery({
    queryKey: ['admin', 'audit-events'],
    queryFn: () => apiJson('/admin/audit-events?limit=500', z.array(eventSchema)),
    enabled: adapterKind === 'http' && allowed,
  });
  const [area, setArea] = useState('');

  if (adapterKind !== 'http') return <StatePanel kind="not_implemented" />;
  const rows = (events.data ?? []).filter((e) => !area || e.action.startsWith(`${area}.`));
  const areas = [...new Set((events.data ?? []).map((e) => e.action.split('.')[0] ?? ''))].filter(Boolean).sort();
  const columns: Column<AuditEvent>[] = [
    { key: 'at', header: t('audit.when'), cell: (e) => <span className="whitespace-nowrap">{formatDateTime(e.occurred_at, language)}</span>, sortValue: (e) => e.occurred_at, csv: (e) => e.occurred_at },
    { key: 'actor', header: t('audit.actor'), cell: (e) => e.actor ?? '—', sortValue: (e) => e.actor },
    { key: 'action', header: t('audit.action'), cell: (e) => <span className="font-mono text-xs" dir="ltr">{e.action}</span>, sortValue: (e) => e.action },
    { key: 'entity', header: t('audit.entity'), cell: (e) => <span className="text-xs" dir="ltr">{[e.entity_type, e.entity_id].filter(Boolean).join(' · ') || '—'}</span>, sortValue: (e) => e.entity_type, csv: (e) => [e.entity_type, e.entity_id].filter(Boolean).join(' ') },
    {
      key: 'outcome', header: t('audit.outcome'), sortValue: (e) => e.outcome,
      cell: (e) => <Badge variant={e.outcome === 'success' ? 'verified' : e.outcome ? 'accent' : 'muted'}>{e.outcome ?? '—'}</Badge>,
    },
  ];
  return (
    <>
      <PageHeader title={t('audit.title')} intro={t('audit.intro')} />
      {!allowed ? <StatePanel kind="restricted" /> : events.isPending ? <StatePanel kind="loading" skeleton="lines" /> : events.isError ? (
        <StatePanel kind="error" detail={events.error.message} onRetry={() => void events.refetch()} />
      ) : (
        <DataTable rows={rows} columns={columns} rowKey={(e) => String(e.id)} caption={t('audit.caption')} pageSize={25}
          search={(e) => [e.actor, e.action, e.entity_type, e.entity_id, e.outcome].filter(Boolean).join(' ')}
          empty={t('audit.empty')} exportName="osrip-audit-log" testId="audit-table" initialSort={{ key: 'at', direction: 'desc' }}
          toolbar={(
            <SelectField className="w-full sm:w-56" label={t('audit.area')} value={area} onValueChange={setArea} data-testid="audit-area"
              options={[{ value: '', label: t('filters.all') }, ...areas.map((a) => ({ value: a, label: a }))]} />
          )} />
      )}
    </>
  );
}
