import { CheckCircle2, CircleDashed, ExternalLink, FlaskConical, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useProviderReadiness, useTestProvider, type ProviderState } from '@/api/monitoring';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { useAppLanguage } from '@/lib/useAppLanguage';

const ICON = {
  tested: <CheckCircle2 aria-hidden="true" className="size-4 text-verified-foreground" />,
  configured: <CircleDashed aria-hidden="true" className="size-4 text-primary" />,
  failed: <TriangleAlert aria-hidden="true" className="size-4 text-destructive" />,
  unavailable: <CircleDashed aria-hidden="true" className="size-4 text-muted-foreground" />,
} as const;

const TEST_STATUS = { ok: true, not_configured: true, unsupported: true } as const;

/**
 * AI and search providers for administrators: configured, tested, unavailable or failed, the
 * role each plays (answering / search, primary / fallback), the configured model, today's calls
 * and limits, and a Test button that makes one small live call. Names of missing settings only;
 * secret values never reach the browser.
 */
export function ProviderReadiness({ enabled, canTest }: { enabled: boolean; canTest: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const data = useProviderReadiness(enabled);
  const test = useTestProvider();
  if (!data.data) return null;
  const r = data.data;
  return (
    <section aria-labelledby="providers" className="flex flex-col gap-3" data-testid="provider-readiness">
      <h2 id="providers" className="text-lg font-semibold">{t('providers.title')}</h2>
      <p className="max-w-3xl text-sm text-muted-foreground">{language === 'ar' ? r.policy.ar : r.policy.en}</p>
      <p className="text-xs text-muted-foreground" dir="ltr" data-testid="provider-routing">
        {t('providers.answering')}: {r.routing.answer.primary ?? '—'}{r.routing.answer.fallback ? ` → ${r.routing.answer.fallback}` : ''}
        {' · '}{t('providers.search')}: {r.routing.search.primary ?? '—'}{r.routing.search.fallback ? ` → ${r.routing.search.fallback}` : ''}
      </p>
      <ul className="grid gap-3 md:grid-cols-2">
        {r.providers.map((p) => <ProviderCard key={p.provider} p={p} testing={test.isPending && test.variables?.provider === p.provider}
          onTest={canTest ? (capability) => test.mutate({ provider: p.provider, capability }) : null} />)}
      </ul>
      {test.isError ? <p role="alert" className="text-sm text-destructive" data-testid="provider-test-result">{test.error.message}</p> : null}
      {test.data ? (
        <p role="status" className="text-sm" data-testid="provider-test-result" data-status={test.data.status}>
          {t('providers.testResult', {
            provider: r.providers.find((p) => p.provider === test.data.provider)?.label ?? test.data.provider,
            capability: t(`providers.capability.${test.data.capability as 'answer'}`),
            status: test.data.status in TEST_STATUS ? t(`providers.testStatus.${test.data.status as keyof typeof TEST_STATUS}`)
              : t('providers.testFailed', { code: test.data.status }),
          })}
        </p>
      ) : null}
      <p className="text-xs text-muted-foreground">{t('providers.note')}</p>
    </section>
  );
}

function ProviderCard({ p, onTest, testing }: { p: ProviderState; onTest: ((capability: string) => void) | null; testing: boolean }) {
  const { t } = useTranslation();
  const last = [p.last_test, p.last_call].filter((x): x is NonNullable<typeof x> => Boolean(x))
    .sort((a, b) => b.at.localeCompare(a.at))[0];
  return (
    <li>
      <Card className="flex h-full flex-col gap-2 p-4 text-sm" data-testid="provider" data-name={p.provider} data-status={p.status}>
        <p className="flex items-center gap-1.5 font-semibold">{ICON[p.status]}{p.label}</p>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant={p.status === 'failed' ? 'accent' : p.status === 'tested' ? 'verified' : 'muted'}>{t(`providers.status.${p.status}`)}</Badge>
          {p.roles.map((role) => <Badge key={role} variant="outline">{t(`providers.role.${role as 'answer_primary'}`)}</Badge>)}
          {p.billing ? (
            <Badge variant={p.billing === 'free_tier_available' ? 'verified' : 'sand'} data-testid="provider-billing" data-billing={p.billing}>
              {t(`providers.billing.${p.billing}`)}
            </Badge>
          ) : null}
        </div>
        {p.billing === 'usage_billed' && p.roles.includes('answer_fallback') ? (
          <p className="text-xs text-sand-foreground" role="note" data-testid="provider-billed-fallback">{t('providers.billedFallback')}</p>
        ) : null}
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          {Object.entries(p.capabilities).map(([cap, c]) => (
            <div key={cap} className="contents">
              <dt className="text-muted-foreground">{t(`providers.capability.${cap as 'answer'}`)}</dt>
              <dd dir="ltr">
                {c.model ?? (c.missing.length ? '—' : t('providers.noModelNeeded'))}
                {c.missing.length ? <span className="block text-destructive" data-testid="provider-missing">{t('providers.missing')}: {c.missing.join(', ')}</span> : null}
              </dd>
            </div>
          ))}
          <dt className="text-muted-foreground">{t('providers.today')}</dt>
          <dd>{t('providers.calls', { calls: p.today.calls, errors: p.today.errors, limit: p.limits.daily_calls })}
            {p.today.estimated_cost_usd != null ? ` · ≈ ${p.today.estimated_cost_usd.toFixed(4)} USD` : ` · ${t('providers.noPrices')}`}</dd>
          {last ? (
            <>
              <dt className="text-muted-foreground">{t('providers.last')}</dt>
              <dd dir="ltr">{last.status} · {last.capability} · {last.at.slice(0, 19).replace('T', ' ')}</dd>
            </>
          ) : null}
        </dl>
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
          {onTest && Object.entries(p.capabilities).filter(([, c]) => c.missing.length === 0).map(([cap]) => (
            <Button key={cap} size="sm" variant="outline" disabled={testing} onClick={() => onTest(cap)} data-testid={`provider-test-${cap}`}>
              <FlaskConical aria-hidden="true" />{t('providers.test', { capability: t(`providers.capability.${cap as 'answer'}`) })}
            </Button>
          ))}
          <a href={p.docs} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-xs text-primary underline underline-offset-2">
            {t('providers.docs')}<ExternalLink aria-hidden="true" className="size-3" />
          </a>
        </div>
      </Card>
    </li>
  );
}
