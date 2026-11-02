import { Gauge, RefreshCw, Wallet } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import type { Monitoring, UsageRow } from '@/api/monitoring';
import { Segmented } from '@/components/ui/segmented';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { formatDateTime, formatDecimal } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

const TH = 'px-2 py-2 font-medium';

function SectionTitle({ id, icon: Icon, children }: { id: string; icon: typeof Gauge; children: string }) {
  return (
    <h2 id={id} className="flex items-center gap-2 text-lg font-semibold">
      <Icon aria-hidden="true" className="size-5 text-primary" />{children}
    </h2>
  );
}

/** Calls, failures, tokens and estimated cost per provider, from the server's own call log. */
export function UsagePanel({ usage }: { usage: Monitoring['usage'] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [range, setRange] = useState<'day' | 'month'>('day');
  const rows: UsageRow[] = usage.windows[range];
  const n = (value: number) => formatDecimal(String(value), language, 0) ?? '—';
  return (
    <section aria-labelledby="usage" className="flex flex-col gap-3" data-testid="health-usage">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionTitle id="usage" icon={Wallet}>{t('health.usage.title')}</SectionTitle>
        <Segmented label={t('health.usage.range')} value={range} onChange={setRange} testId="usage-range" className="w-56 shrink-0" options={[
          { value: 'day', label: t('health.usage.day') },
          { value: 'month', label: t('health.usage.month') },
        ]} />
      </div>
      <p className="text-sm text-muted-foreground">{t('health.usage.note')}</p>
      {rows.length === 0 ? <p className="text-sm text-muted-foreground">{t('health.usage.none')}</p> : (
        <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full min-w-[40rem] text-sm" data-testid="usage-table">
            <thead><tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
              <th scope="col" className={`${TH} px-3 text-start`}>{t('health.usage.provider')}</th>
              <th scope="col" className={`${TH} text-end`}>{t('health.usage.calls')}</th>
              <th scope="col" className={`${TH} text-end`}>{t('health.usage.failures')}</th>
              <th scope="col" className={`${TH} text-end`}>{t('health.usage.refused')}</th>
              <th scope="col" className={`${TH} text-end`}>{t('health.usage.tokens')}</th>
              <th scope="col" className={`${TH} text-end`}>{t('health.usage.average')}</th>
              <th scope="col" className={`${TH} px-3 text-end`}>{t('health.usage.cost')}</th>
            </tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.provider} className="border-b border-border last:border-0" data-provider={r.provider}>
                <th scope="row" className="px-3 py-2 text-start font-medium" dir="ltr">{r.provider}</th>
                <td className="px-2 py-2 text-end tabular-nums">{n(r.calls)}</td>
                <td className="px-2 py-2 text-end tabular-nums">{n(r.failures)}</td>
                <td className="px-2 py-2 text-end tabular-nums">{n(r.refused)}</td>
                <td className="px-2 py-2 text-end tabular-nums" dir="ltr">{n(r.input_tokens)} / {n(r.output_tokens)}</td>
                <td className="px-2 py-2 text-end tabular-nums">{r.average_ms === null ? '—' : t('health.ms', { value: n(r.average_ms) })}</td>
                <td className="px-3 py-2 text-end tabular-nums">
                  {r.estimated_cost_usd === null ? <span className="text-muted-foreground">{t('health.usage.notPriced')}</span>
                    : <span dir="ltr">US$ {formatDecimal(String(r.estimated_cost_usd), language, 4)}</span>}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** Official-statistics feeds: schedule, last check and releases waiting for an administrator. */
export function SyncPanel({ feeds }: { feeds: Monitoring['sync'] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const when = (value: string | null) => (value ? formatDateTime(value, language) : '—');
  return (
    <section aria-labelledby="sync" className="flex flex-col gap-3" data-testid="health-sync">
      <SectionTitle id="sync" icon={RefreshCw}>{t('health.sync.title')}</SectionTitle>
      <p className="text-sm text-muted-foreground">{t('health.sync.note')}</p>
      {feeds.length === 0 ? <p className="text-sm text-muted-foreground">{t('health.sync.none')}</p> : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {feeds.map((f) => (
            <li key={f.code}>
              <Card className="flex flex-col gap-2 p-4 text-sm" data-testid="sync-feed" data-code={f.code}>
                <p className="font-semibold">{language === 'ar' ? f.title.ar : f.title.en}</p>
                <div className="flex flex-wrap gap-1.5">
                  <Badge variant={f.enabled ? 'verified' : 'muted'}>{f.enabled ? t('health.sync.on') : t('health.sync.off')}</Badge>
                  <Badge variant="outline">{f.auto_publish ? t('health.sync.autoPublish') : t('health.sync.approval')}</Badge>
                  {f.consecutive_failures > 0 ? <Badge variant="accent">{t('health.sync.failures', { count: f.consecutive_failures })}</Badge> : null}
                  {f.awaiting_approval > 0 ? <Badge variant="pending">{t('health.sync.awaiting', { count: f.awaiting_approval })}</Badge> : null}
                </div>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                  <dt className="text-muted-foreground">{t('health.sync.lastSuccess')}</dt><dd>{when(f.last_success_at)}</dd>
                  <dt className="text-muted-foreground">{t('health.sync.lastChecked')}</dt>
                  <dd>{when(f.last_checked_at)}{f.last_status ? <span className="text-muted-foreground" dir="ltr"> · {f.last_status}</span> : null}</dd>
                  <dt className="text-muted-foreground">{t('health.sync.nextCheck')}</dt><dd>{f.enabled ? when(f.next_check_at) : '—'}</dd>
                </dl>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <Link to="/data-management" className="w-fit text-sm font-medium text-primary underline-offset-4 hover:underline">{t('health.sync.manage')}</Link>
    </section>
  );
}

/** Response times of this server process (route patterns only), since it started. */
export function PerformancePanel({ perf }: { perf: Monitoring['performance'] }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const ms = (value: number | null) => (value === null ? '—' : t('health.ms', { value: formatDecimal(String(value), language, 0) ?? '—' }));
  const tiles = [
    { key: 'p50', label: t('health.perf.p50'), value: ms(perf.p50_ms) },
    { key: 'p95', label: t('health.perf.p95'), value: ms(perf.p95_ms) },
    { key: 'max', label: t('health.perf.max'), value: ms(perf.max_ms) },
    { key: 'errors', label: t('health.perf.serverErrors'), value: formatDecimal(String(perf.server_errors), language, 0) ?? '0' },
  ];
  return (
    <section aria-labelledby="performance" className="flex flex-col gap-3" data-testid="health-performance">
      <SectionTitle id="performance" icon={Gauge}>{t('health.perf.title')}</SectionTitle>
      <p className="text-sm text-muted-foreground">
        {t('health.perf.note', { requests: perf.requests, window: perf.window, hours: Math.floor(perf.uptime_seconds / 3600) })}
      </p>
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {tiles.map((tile) => (
          <li key={tile.key}>
            <Card className="flex flex-col gap-1 p-4" data-testid={`perf-${tile.key}`}>
              <span className="text-xs text-muted-foreground">{tile.label}</span>
              <span className="text-xl font-semibold tabular-nums">{tile.value}</span>
            </Card>
          </li>
        ))}
      </ul>
      {perf.slowest.length > 0 ? (
        <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full min-w-[32rem] text-sm" data-testid="slowest-routes">
            <caption className="px-3 pt-2 text-start text-xs text-muted-foreground">{t('health.perf.slowest')}</caption>
            <thead><tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
              <th scope="col" className={`${TH} px-3 text-start`}>{t('health.perf.route')}</th>
              <th scope="col" className={`${TH} text-end`}>{t('health.perf.requests')}</th>
              <th scope="col" className={`${TH} px-3 text-end`}>{t('health.perf.p95')}</th>
            </tr></thead>
            <tbody>{perf.slowest.map((r) => (
              <tr key={r.route} className="border-b border-border last:border-0">
                <th scope="row" className="px-3 py-2 text-start font-mono text-xs font-normal" dir="ltr">{r.route}</th>
                <td className="px-2 py-2 text-end tabular-nums">{r.requests}</td>
                <td className="px-3 py-2 text-end tabular-nums">{ms(r.p95_ms)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
