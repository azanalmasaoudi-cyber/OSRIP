import {
  ArrowDownRight, ArrowRight, ArrowUpRight, ClipboardList, DatabaseZap, FileSearch, Gauge, Lightbulb, MapPinned,
  Scale, ShieldAlert, Ship, ThumbsDown, ThumbsUp, TrendingUp,
} from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { adapterKind } from '@/api/config';
import { useDecisionBrief, type BriefFinding, type DecisionBrief as Brief } from '@/api/decision';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import type { SectionCode } from '@/domain/types';
import { formatDateTime, formatDecimal, type AppLanguage } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDataMode } from '@/state/useDataMode';

function Block({ id, title, icon: Icon, children, className, testId }: {
  id: string; title: string; icon: typeof Gauge; children: ReactNode; className?: string; testId: string;
}) {
  return (
    <section aria-labelledby={id} className={cn('glass-card flex min-w-0 flex-col gap-3 rounded-lg border border-border p-4 shadow-card sm:p-5', className)} data-testid={testId}>
      <h3 id={id} className="flex items-center gap-2 text-lg font-semibold">
        <Icon aria-hidden="true" className="size-5 shrink-0 text-primary" />{title}
      </h3>
      {children}
    </section>
  );
}

function Refs({ refs, show }: { refs: readonly string[]; show: boolean }) {
  if (!show || refs.length === 0) return null;
  return <span className="ms-1 text-xs text-muted-foreground" dir="ltr">[{refs.join(', ')}]</span>;
}

function Empty({ children }: { children: string }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

function ShareBar({ label, value, share, language }: { label: string; value: string; share: string | null; language: AppLanguage }) {
  const pct = share === null ? null : Math.max(0, Math.min(100, Number(share)));
  return (
    <li className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="min-w-0 truncate">{label}</span>
        <span className="shrink-0 tabular-nums">
          {formatDecimal(value, language)}{pct === null ? null : <span className="text-muted-foreground"> · {formatDecimal(String(pct), language, 1)}%</span>}
        </span>
      </div>
      {pct === null ? null : (
        <div className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
          <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
        </div>
      )}
    </li>
  );
}

function Findings({ items, show, language, empty, testId }: {
  items: readonly BriefFinding[]; show: boolean; language: AppLanguage; empty: string; testId: string;
}) {
  const { t } = useTranslation();
  if (items.length === 0) return <Empty>{empty}</Empty>;
  return (
    <ul className="flex flex-col gap-2" data-testid={testId}>
      {items.map((f) => (
        <li key={f.id} className="text-sm" data-kind={f.kind}>
          <p>{f.text[language]}<Refs refs={f.refs} show={show} /></p>
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer">{t('decision.rule')}</summary>
            <p className="mt-1">{f.rule[language]}</p>
          </details>
        </li>
      ))}
    </ul>
  );
}

/** The decision brief of the axis: findings built by the server from published data and stated
 * rules (no AI, no estimates). Source references stay out of the findings unless asked for; the
 * sources and their verification records are in the collapsed panel at the end. */
export function DecisionBrief({ section }: { section: SectionCode }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const query = useDecisionBrief(section, mode);
  const [showRefs, setShowRefs] = useState(false);
  const uid = useId();
  if (adapterKind !== 'http') return null;

  const heading = (
    <div className="flex flex-col gap-1">
      <h2 id={`${uid}-h`} className="text-2xl font-semibold">{t('decision.title')}</h2>
      <p className="max-w-3xl text-base text-muted-foreground">{t('decision.intro')}</p>
    </div>
  );
  if (query.isPending) return <section aria-labelledby={`${uid}-h`} className="flex flex-col gap-4">{heading}<StatePanel kind="loading" skeleton="lines" /></section>;
  if (query.isError) {
    return (
      <section aria-labelledby={`${uid}-h`} className="flex flex-col gap-4">
        {heading}<StatePanel kind="error" detail={query.error.message} onRetry={() => void query.refetch()} />
      </section>
    );
  }
  const b: Brief = query.data;
  // Isolated (U+2066 … U+2069) so a minus sign stays in front of the number in Arabic text.
  const n = (value: string, places = 1) => `⁦${formatDecimal(value, language, places) ?? '—'}⁩`;
  const movers = new Set(b.movers);
  const id = (part: string) => `${uid}-${part}`;

  return (
    <section id="decision-brief" tabIndex={-1} aria-labelledby={`${uid}-h`} className="flex scroll-mt-24 flex-col gap-4 outline-none" data-testid="decision-brief" data-section={section}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        {heading}
        <label className="flex min-h-10 items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-primary" checked={showRefs} onChange={(e) => setShowRefs(e.target.checked)} data-testid="decision-show-refs" />
          {t('decision.showRefs')}
        </label>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Block id={id('perf')} title={t('decision.performance')} icon={Gauge} className="xl:col-span-2" testId="decision-performance">
          {b.performance.length === 0 ? <Empty>{t('decision.noPerformance')}</Empty> : (
            <div className="relative overflow-x-auto">
              <table className="w-full min-w-[36rem] text-sm">
                <thead><tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pe-2 text-start font-medium">{t('decision.indicator')}</th>
                  <th scope="col" className="px-2 py-2 text-start font-medium">{t('decision.periods')}</th>
                  <th scope="col" className="px-2 py-2 text-end font-medium">{t('decision.latest')}</th>
                  <th scope="col" className="py-2 ps-2 text-end font-medium">{t('decision.change')}</th>
                </tr></thead>
                <tbody>{b.performance.map((p) => {
                  const Arrow = p.direction === 'up' ? ArrowUpRight : p.direction === 'down' ? ArrowDownRight : ArrowRight;
                  return (
                    <tr key={p.id} className="border-b border-border last:border-0 align-top" data-indicator={p.indicator.code}>
                      <th scope="row" className="py-2 pe-2 text-start font-medium">
                        {p.indicator.name[language]}
                        {movers.has(p.id) ? <Badge variant="sand" className="ms-2 align-middle">{t('decision.mover')}</Badge> : null}
                        <Refs refs={p.refs} show={showRefs} />
                      </th>
                      <td className="px-2 py-2 text-muted-foreground">{p.previous.period[language]} → {p.current.period[language]}</td>
                      <td className="px-2 py-2 text-end tabular-nums">{n(p.current.value)} <span className="text-xs text-muted-foreground">{p.unit[language]}</span></td>
                      <td className="py-2 ps-2 text-end tabular-nums">
                        <span className="inline-flex items-center gap-1" dir="ltr">
                          <Arrow aria-hidden="true" className="size-4" />{n(p.change_pct)}%
                        </span>
                      </td>
                    </tr>
                  );
                })}</tbody>
              </table>
            </div>
          )}
        </Block>

        <Block id={id('factors')} title={t('decision.factors')} icon={TrendingUp} testId="decision-factors">
          {b.composition.length === 0 ? <Empty>{t('decision.noComposition')}</Empty> : b.composition.map((c) => (
            <div key={c.parent.code} className="flex flex-col gap-2">
              <p className="text-sm font-medium">{t('decision.compositionOf', { name: c.parent.name[language], period: c.period[language] })}<Refs refs={c.refs} show={showRefs} /></p>
              <ul className="flex flex-col gap-2">
                {c.parts.map((part) => <ShareBar key={part.indicator.code} label={part.indicator.name[language]} value={part.value} share={part.share_pct} language={language} />)}
              </ul>
            </div>
          ))}
          <p className="text-xs text-muted-foreground">{t('decision.factorsNote')}</p>
        </Block>

        <Block id={id('balance')} title={t('decision.balance')} icon={Scale} testId="decision-balance">
          {!b.balance.assessable ? <Empty>{t('decision.notAssessable')}</Empty> : (
            <div className="grid gap-3 sm:grid-cols-2">
              {(['surplus', 'shortage'] as const).map((side) => (
                <div key={side} className="flex flex-col gap-2">
                  <p className="text-sm font-semibold">{t(`decision.${side}`)}</p>
                  {b.balance[side].length === 0 ? <Empty>{t('decision.none')}</Empty> : (
                    <ul className="flex flex-col gap-1.5 text-sm" data-testid={`decision-${side}`}>
                      {b.balance[side].map((item) => (
                        <li key={`${item.indicator.code}-${item.period.en}`}>
                          {item.indicator.name[language]}: <span className="tabular-nums">{n(item.value)}</span> {item.unit[language]} ({item.period[language]})
                          <Refs refs={item.refs} show={showRefs} />
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </Block>

        <Block id={id('strengths')} title={t('decision.strengths')} icon={ThumbsUp} testId="decision-strengths">
          <Findings items={b.strengths} show={showRefs} language={language} empty={t('decision.noStrengths')} testId="decision-strength-list" />
        </Block>
        <Block id={id('weaknesses')} title={t('decision.weaknesses')} icon={ThumbsDown} testId="decision-weaknesses">
          <Findings items={b.weaknesses} show={showRefs} language={language} empty={t('decision.noWeaknesses')} testId="decision-weakness-list" />
        </Block>

        {b.trade.length > 0 ? (
          <Block id={id('trade')} title={t('decision.trade')} icon={Ship} className="xl:col-span-2" testId="decision-trade">
            <ul className="flex flex-col gap-1.5 text-sm">
              {b.trade.map((x) => (
                <li key={`${x.kind}-${x.exports?.code ?? 'all'}`}>
                  {x.kind === 'balance'
                    ? t('decision.tradeBalance', { value: n(x.value ?? '0', 0), unit: x.unit[language], period: x.period[language] })
                    : t('decision.tradeGroup', { exports: x.exports?.name[language] ?? '', imports: x.imports?.name[language] ?? '', value: n(x.net ?? '0', 0), unit: x.unit[language], period: x.period[language] })}
                  <Refs refs={x.refs} show={showRefs} />
                </li>
              ))}
            </ul>
          </Block>
        ) : null}

        <Block id={id('regional')} title={t('decision.regional')} icon={MapPinned} testId="decision-regional">
          {b.regional.length === 0 ? <Empty>{t('decision.noRegional')}</Empty> : b.regional.map((r) => (
            <div key={r.indicator.code} className="flex flex-col gap-2">
              <p className="text-sm font-medium">{r.indicator.name[language]} · {r.period[language]} <span className="text-xs text-muted-foreground">({r.unit[language]})</span></p>
              <ul className="flex flex-col gap-2">
                {r.areas.map((a) => <ShareBar key={a.area.code} label={a.area.name[language]} value={a.value} share={a.share_pct} language={language} />)}
              </ul>
            </div>
          ))}
          <p className="text-xs text-muted-foreground">
            {section === 'trade' ? t('decision.nationalOnly') : t('decision.coverage', { count: b.coverage.governorates.length, of: b.coverage.of })}
          </p>
          <Link to="/geography" className="w-fit text-sm font-medium text-primary underline-offset-4 hover:underline">{t('decision.openMap')}</Link>
        </Block>

        <Block id={id('risks')} title={t('decision.risks')} icon={ShieldAlert} testId="decision-risks">
          <Findings items={b.risks} show={showRefs} language={language} empty={t('decision.noRisks')} testId="decision-risk-list" />
        </Block>

        <Block id={id('scenarios')} title={t('decision.scenarios')} icon={ClipboardList} testId="decision-scenarios">
          {b.scenarios.length === 0 ? <Empty>{t('decision.noScenarios')}</Empty> : (
            <>
              <p className="text-sm text-muted-foreground">{t('decision.scenariosIntro', { count: b.scenarios.length })}</p>
              <ul className="flex flex-col gap-1 text-sm">
                {b.scenarios.slice(0, 6).map((s) => (
                  <li key={s.series_id}>{s.indicator.name[language]} · {s.area[language]}: <span className="tabular-nums">{n(s.base.value)}</span> {s.unit[language]} ({s.base.period[language]})</li>
                ))}
              </ul>
            </>
          )}
          <Link to="/forecasts" className="w-fit text-sm font-medium text-primary underline-offset-4 hover:underline">{t('decision.compareScenarios')}</Link>
        </Block>

        <Block id={id('gaps')} title={t('decision.gaps')} icon={DatabaseZap} testId="decision-gaps">
          {b.gaps.length === 0 ? <Empty>{t('decision.noGaps')}</Empty> : (
            <ul className="flex flex-col gap-1.5 text-sm">
              {b.gaps.map((g) => (
                <li key={`${g.kind}-${g.indicator?.code ?? ''}`} data-kind={g.kind}>
                  {g.kind === 'regional'
                    ? t('decision.gap.regional', { count: g.covered ?? 0, of: g.of ?? 0 })
                    : t(`decision.gap.${g.kind}`, { name: g.indicator?.name[language] ?? '', date: g.latest ?? '' })}
                </li>
              ))}
            </ul>
          )}
        </Block>

        <Block id={id('recs')} title={t('decision.recommendations')} icon={Lightbulb} className="xl:col-span-2" testId="decision-recommendations">
          {b.recommendations.length === 0 ? <Empty>{t('decision.noRecommendations')}</Empty> : (
            <ol className="flex list-decimal flex-col gap-1.5 ps-5 text-sm">
              {b.recommendations.map((r, i) => <li key={`${r.kind}-${i}`} data-kind={r.kind}>{r.text[language]}</li>)}
            </ol>
          )}
          <p className="text-xs text-muted-foreground">{t('decision.recommendationsNote')}</p>
        </Block>
      </div>

      <details className="glass-card group rounded-lg border border-border p-4 shadow-card" data-testid="decision-provenance">
        <summary className="flex cursor-pointer items-center gap-2 text-base font-semibold">
          <FileSearch aria-hidden="true" className="size-5 text-primary" />
          {t('decision.provenance', { count: b.provenance.length })}
        </summary>
        <p className="mt-3 text-sm text-muted-foreground">
          {t('decision.provenanceIntro', { date: formatDateTime(b.generated_at, language), version: b.version })}
        </p>
        {b.provenance.length === 0 ? null : (
          <div className="relative mt-3 overflow-x-auto">
            <table className="w-full min-w-[48rem] text-xs">
              <thead><tr className="border-b border-border-strong/40 text-muted-foreground">
                <th scope="col" className="py-2 pe-2 text-start font-medium">{t('decision.ref')}</th>
                <th scope="col" className="px-2 py-2 text-start font-medium">{t('decision.indicator')}</th>
                <th scope="col" className="px-2 py-2 text-start font-medium">{t('decision.period')}</th>
                <th scope="col" className="px-2 py-2 text-end font-medium">{t('decision.value')}</th>
                <th scope="col" className="px-2 py-2 text-start font-medium">{t('decision.source')}</th>
                <th scope="col" className="py-2 ps-2 text-start font-medium">{t('decision.verification')}</th>
              </tr></thead>
              <tbody>{b.provenance.map((e) => (
                <tr key={e.ref} className="border-b border-border last:border-0 align-top">
                  <td className="py-2 pe-2 font-mono" dir="ltr">{e.ref}</td>
                  <td className="px-2 py-2">{e.indicator_name[language]} <span className="text-muted-foreground" dir="ltr">({e.area})</span></td>
                  <td className="px-2 py-2 whitespace-nowrap" dir="ltr">{e.period_start} – {e.period_end}</td>
                  <td className="px-2 py-2 text-end tabular-nums">{e.value === null ? '—' : n(e.value, 3)} {e.unit?.[language]}</td>
                  <td className="px-2 py-2">
                    {e.source_url ? <a href={e.source_url} target="_blank" rel="noreferrer" className="text-primary underline-offset-4 hover:underline" dir="ltr">{e.source_title}</a> : <span dir="ltr">{e.source_title}</span>}
                    {e.source_locator ? <span className="text-muted-foreground" dir="ltr"> · {e.source_locator}</span> : null}
                  </td>
                  <td className="py-2 ps-2 text-muted-foreground" dir="ltr">
                    {[e.dataset_version, e.record_ref, e.quality_status, e.revision_status, e.published_at ? formatDateTime(e.published_at, language) : null].filter(Boolean).join(' · ')}
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </details>
    </section>
  );
}
