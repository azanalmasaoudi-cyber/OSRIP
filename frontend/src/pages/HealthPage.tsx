import { Activity, CheckCircle2, CircleDashed, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { hasPermission, useMe } from '@/api/auth';
import { adapterKind } from '@/api/config';
import { useMonitoring } from '@/api/monitoring';
import { PageHeader } from '@/components/common/PageHeader';
import { ProviderReadiness } from '@/components/common/ProviderReadiness';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';

const NAMES = ['email', 'assistant', 'google', 'microsoft', 'official_statistics'] as const;

/** Service health and recent errors (administrators with audit access). */
export function HealthPage() {
  const { t } = useTranslation();
  const me = useMe();
  const allowed = hasPermission(me.data, 'audit.read');
  const data = useMonitoring(allowed);

  if (adapterKind !== 'http') return <StatePanel kind="not_implemented" />;
  return (
    <>
      <PageHeader title={t('health.title')} intro={t('health.intro')} />
      {!allowed ? <StatePanel kind="restricted" /> : data.isPending ? <StatePanel kind="loading" skeleton="lines" /> : data.isError ? (
        <StatePanel kind="error" detail={data.error.message} onRetry={() => void data.refetch()} />
      ) : (
        <div className="flex flex-col gap-6" data-testid="health-page">
          <Card className="flex flex-wrap items-center gap-3 p-4">
            <Activity aria-hidden="true" className="size-5 text-primary" />
            <span className="font-semibold">{data.data.ready ? t('health.ready') : t('health.notReady')}</span>
            <span className="text-sm text-muted-foreground" dir="ltr">
              {t('health.release')} {data.data.release} · {t('health.migration')} {data.data.checks.migration ?? '—'}
            </span>
          </Card>
          <section aria-labelledby="integrations" className="flex flex-col gap-3">
            <h2 id="integrations" className="text-lg font-semibold">{t('health.integrations')}</h2>
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {NAMES.map((name) => {
                const i = data.data.integrations[name];
                if (!i) return null;
                const icon = i.status === 'ok' || i.status === 'file_import' ? <CheckCircle2 aria-hidden="true" className="size-4 text-verified-foreground" />
                  : i.status === 'degraded' ? <TriangleAlert aria-hidden="true" className="size-4 text-destructive" />
                    : <CircleDashed aria-hidden="true" className="size-4 text-muted-foreground" />;
                return (
                  <li key={name}>
                    <Card className="flex flex-col gap-1 p-4 text-sm" data-testid="integration" data-name={name} data-status={i.status}>
                      <p className="flex items-center gap-1.5 font-semibold">{icon}{t(`health.name.${name}`)}</p>
                      <Badge variant={i.status === 'degraded' ? 'accent' : 'muted'} className="w-fit">{t(`health.status.${i.status as 'ok'}`)}</Badge>
                      {i.last_failure_code ? <p className="text-xs text-muted-foreground" dir="ltr">{i.last_failure_code} · {i.failures_since_start}</p> : null}
                      {i.mode ? <p className="text-xs text-muted-foreground">{t('health.mode')}: {i.mode}</p> : null}
                    </Card>
                  </li>
                );
              })}
            </ul>
          </section>
          <ProviderReadiness enabled={allowed} canTest={hasPermission(me.data, 'user.manage')} />
          <section aria-labelledby="errors" className="flex flex-col gap-3">
            <h2 id="errors" className="text-lg font-semibold">{t('health.errors')}</h2>
            {data.data.errors.length === 0 ? <p className="text-sm text-muted-foreground">{t('health.noErrors')}</p> : (
              <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
                <table className="w-full min-w-[40rem] text-sm" data-testid="error-table">
                  <thead><tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                    <th scope="col" className="px-3 py-2 text-start font-medium">{t('health.lastSeen')}</th>
                    <th scope="col" className="px-2 py-2 text-start font-medium">{t('health.source')}</th>
                    <th scope="col" className="px-2 py-2 text-start font-medium">{t('health.error')}</th>
                    <th scope="col" className="px-2 py-2 text-end font-medium">{t('health.count')}</th>
                  </tr></thead>
                  <tbody>{data.data.errors.map((e) => (
                    <tr key={e.fingerprint} className="border-b border-border last:border-0 align-top">
                      <td className="px-3 py-2 text-xs" dir="ltr">{e.last_seen.slice(0, 19).replace('T', ' ')}</td>
                      <td className="px-2 py-2 text-xs">{e.source}</td>
                      <td className="px-2 py-2"><span className="font-mono text-xs" dir="ltr">{e.kind}</span><p className="text-xs text-muted-foreground" dir="ltr">{e.message} · {e.location}</p></td>
                      <td className="px-2 py-2 text-end tabular-nums">{e.count}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}
