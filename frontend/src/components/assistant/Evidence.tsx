import { BookmarkPlus, ExternalLink, Globe, Search } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import type { AssistantMessage, Evidence } from '@/api/assistant';
import { useSaveResearch } from '@/api/library';
import { DataStatusBadge } from '@/components/common/DataStatusBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatDecimal, formatPeriod, type AppLanguage } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/*
 * A reply's evidence, as shown under it in the assistant panel and on the conversation page:
 * published observations and calculations, web pages with their class and dates, the search
 * log (failures included), Google Search grounded results shown apart, and saving a reply.
 */

export const STATUS_BADGE = {
  answered: null,
  clarification: 'assistant.statusClarification',
  no_evidence: 'assistant.statusNoEvidence',
  unverified: 'assistant.statusUnverified',
  unavailable: 'assistant.statusUnavailable',
  lookup: 'assistant.statusLookup',
  profile: 'assistant.statusProfile',
  cancelled: 'assistant.statusCancelled',
  data_report: 'assistant.statusDataReport',
} as const;

export const EVIDENCE_CLASS_KEY = {
  observed: 'assistant.class.observed',
  calculated: 'assistant.class.calculated',
  forecast: 'assistant.class.forecast',
  hypothetical: 'assistant.class.hypothetical',
  reference: 'assistant.class.reference',
  official: 'assistant.class.official',
  research: 'assistant.class.research',
  secondary: 'assistant.class.secondary',
} as const;

export const SOURCE_CLASS_KEY = {
  official: 'web.sourceClass.official',
  international: 'web.sourceClass.international',
  research: 'web.sourceClass.research',
  secondary: 'web.sourceClass.secondary',
} as const;

export const OPERATOR = { '>': '>', '>=': '≥', '<': '<', '<=': '≤', '~': '≈' } as const;

export function dateLabel(value: string | null | undefined, language: AppLanguage): string | null {
  if (!value) return null;
  const day = value.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? formatPeriod(day, day, language) : null;
}

/** One retrieved web page or search result, with its class, dates and link. */
export function WebEvidenceItem({ item, anchor }: { item: Evidence; anchor: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const publisher = typeof item.publisher === 'string' ? item.publisher : pick(item.publisher, language);
  const official = item.evidence_class === 'official';
  const research = item.evidence_class === 'research';
  const published = dateLabel(item.published, language);
  const retrieved = dateLabel(item.retrieved_at, language);
  // Another AI provider's cited statement about the page, not the page's own text.
  const summary = item.content_kind === 'provider_summary';
  return (
    <li id={anchor} tabIndex={-1} className="scroll-mt-4 rounded-md border border-border bg-background p-2 text-xs focus-visible:outline-2"
      data-testid="web-citation" data-evidence={item.id} data-class={item.source_class ?? ''}>
      <p className="flex flex-wrap items-center gap-1">
        <span className="font-mono">[{item.id}]</span>
        <Badge variant={official ? 'verified' : research ? 'outline' : 'sand'} data-testid="evidence-class">
          {t(official ? 'assistant.class.official' : research ? 'assistant.class.research' : 'assistant.class.secondary')}
        </Badge>
        {item.source_class ? <span className="text-muted-foreground">{t(SOURCE_CLASS_KEY[item.source_class])}</span> : null}
        <DataStatusBadge status={item.data_status} />
        {item.role === 'cross_check' || item.role === 'fallback' ? (
          <Badge variant="outline" data-testid="evidence-route">{t(`web.route.${item.role}`)}</Badge>
        ) : null}
      </p>
      {summary ? (
        <p className="mt-0.5 text-muted-foreground" data-testid="provider-summary">
          {t('web.providerSummary', { model: item.summary_by ?? item.provider ?? '' })}
        </p>
      ) : null}
      {item.url ? (
        <a href={item.url} target="_blank" rel="noreferrer noopener" className="mt-1 inline-flex items-start gap-1 font-medium text-primary underline underline-offset-2">
          <bdi>{(typeof item.title === 'string' ? item.title : pick(item.title, language)) || item.host}</bdi><ExternalLink aria-hidden="true" className="mt-0.5 size-3 shrink-0" />
        </a>
      ) : null}
      <p className="mt-0.5 text-muted-foreground">
        <bdi>{publisher}</bdi>
        {' · '}
        {published
          ? item.published_basis === 'search_engine' ? t('web.publishedBySearchEngine', { date: published }) : t('web.published', { date: published })
          : t('web.notStated')}
        {retrieved ? <> · {t('web.retrieved', { date: retrieved })}</> : null}
      </p>
      {item.freshness === 'stale' ? (
        <p className="mt-0.5"><Badge variant="sand" data-testid="evidence-stale">{t('workflow.stale')}</Badge></p>
      ) : null}
      {item.locator && /^pp?\. /.test(item.locator) ? (
        <p className="mt-0.5 text-muted-foreground" data-testid="evidence-locator">
          {t('workflow.locator', { locator: language === 'ar' ? item.locator.replace(/^pp?\. /, 'ص ') : item.locator })}
        </p>
      ) : null}
      {item.text ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-muted-foreground">
            {item.content_kind === 'pdf_excerpt' ? t('web.pdfExcerpt') : item.content_kind === 'page_excerpt' ? t('web.excerpt')
              : summary ? t('web.summaryText') : t('web.snippet')}
          </summary>
          <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap" dir="auto">{item.text}</p>
        </details>
      ) : null}
    </li>
  );
}

const SEARCH_PROVIDERS = ['brave', 'openai', 'gemini', 'fake-search', 'fake-openai', 'fake-gemini'] as const;

/** The search route's name for people ("Brave Search", "OpenAI web search", ...). */
function useRouteName() {
  const { t } = useTranslation();
  return (provider: string | null | undefined) => (provider && (SEARCH_PROVIDERS as readonly string[]).includes(provider)
    ? t(`web.provider.${provider as 'brave'}`) : provider ?? '');
}

/** What happened to each web search, including failures (never hidden), by which route. */
export function SearchLog({ items }: { items: Evidence[] }) {
  const { t } = useTranslation();
  const routeName = useRouteName();
  if (!items.length) return null;
  return (
    <ul className="flex flex-col gap-1 text-xs" data-testid="search-log">
      {items.map((s) => {
        const status = typeof s.status === 'string' ? s.status : '';
        const failed = status !== 'ok' && status !== 'no_results';
        const shownApart = s.display_only === true && status === 'ok';
        const text = shownApart ? t('web.shownApart', { query: s.query ?? '' })
          : status === 'ok' ? t('web.searched', { query: s.query ?? '', count: s.result_count ?? 0 })
            : status === 'no_results' ? t('web.noResults', { query: s.query ?? '' })
              : status === 'not_configured' ? t('web.notConfigured')
                : status === 'rate_limited' ? t('web.rateLimited')
                  : t('web.failed', { error: s.error ?? status });
        return (
          <li key={s.id} className={failed ? 'flex items-start gap-1 text-destructive' : 'flex items-start gap-1 text-muted-foreground'}
            data-status={status} data-provider={s.provider ?? ''} data-role={typeof s.role === 'string' ? s.role : 'primary'}
            role={failed ? 'status' : undefined}>
            <Search aria-hidden="true" className="mt-0.5 size-3 shrink-0" />
            <span dir="auto">
              {text}
              {s.provider ? <> · {t('web.via', { route: routeName(s.provider) })}</> : null}
              {s.role === 'fallback' || s.role === 'cross_check' ? <> · {t(`web.route.${s.role}`)}</> : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Google Search grounded results (Grounding with Google Search, via Gemini), shown exactly as
 * returned, with their sources and Google's Search Suggestions, and apart from the answer: the
 * answer never uses them (Gemini API terms), and they are not reviewed OSRIP data.
 * The suggestions are Google's own HTML, rendered in a sandboxed frame that cannot run
 * scripts or reach this page; its links open in a new tab.
 */
export function GroundedContext({ entries }: { entries: NonNullable<AssistantMessage['structured']['grounded_context']> }) {
  const { t } = useTranslation();
  return (
    <section className="flex flex-col gap-2 rounded-md border border-sand/50 bg-sand-subtle/30 p-2 text-xs" data-testid="grounded-context"
      aria-label={t('web.grounded.title')}>
      <p className="flex flex-wrap items-center gap-1 font-semibold">
        <Globe aria-hidden="true" className="size-3.5" />{t('web.grounded.title')}
        <DataStatusBadge status="unreviewed_external" />
      </p>
      <p className="text-muted-foreground">{t('web.grounded.note')}</p>
      {entries.map((g, i) => (
        <div key={i} className="flex flex-col gap-1.5 rounded border border-border bg-background p-2" data-testid="grounded-entry">
          <p className="text-muted-foreground">
            {g.attribution ?? t('web.grounded.attribution')}{g.model ? <> · <span dir="ltr">{g.model}</span></> : null}
          </p>
          <p className="whitespace-pre-wrap" dir="auto" data-testid="grounded-text">{g.text}</p>
          {g.citations.length ? (
            <ol className="flex flex-col gap-0.5" data-testid="grounded-citations">
              {g.citations.map((c, j) => (
                <li key={`${c.url}-${j}`} className="flex flex-wrap items-center gap-1">
                  <span className="font-mono">[{j + 1}]</span>
                  <a href={c.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-primary underline underline-offset-2">
                    <bdi>{c.title || c.url}</bdi><ExternalLink aria-hidden="true" className="size-3 shrink-0" />
                  </a>
                  {c.source_class && c.source_class in SOURCE_CLASS_KEY
                    ? <span className="text-muted-foreground">{t(SOURCE_CLASS_KEY[c.source_class as keyof typeof SOURCE_CLASS_KEY])}</span> : null}
                </li>
              ))}
            </ol>
          ) : null}
          {g.search_suggestions.map((html, j) => (
            <iframe key={j} title={t('web.grounded.suggestions')} data-testid="grounded-suggestions"
              sandbox="allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer"
              srcDoc={`<!doctype html><meta charset="utf-8"><base target="_blank">${html}`}
              className="h-16 w-full rounded border-0 bg-transparent" />
          ))}
        </div>
      ))}
    </section>
  );
}

export function pick(text: { en: string; ar: string } | undefined, language: AppLanguage): string {
  return text ? (language === 'ar' ? text.ar : text.en) : '';
}

export function EvidenceItem({ item, anchor }: { item: Evidence; anchor: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const cls = typeof item.evidence_class === 'string' && item.evidence_class in EVIDENCE_CLASS_KEY
    ? (item.evidence_class as keyof typeof EVIDENCE_CLASS_KEY)
    : null;
  if (item.kind === 'note') {
    // A documented conflict, revision or limitation from the curated reference pack.
    const title = typeof item.title === 'string' ? item.title : pick(item.title, language);
    return (
      <li id={anchor} tabIndex={-1} className="scroll-mt-4 rounded-md border border-border bg-background p-2 text-xs focus-visible:outline-2"
        data-testid="citation" data-evidence={item.id} data-class="note">
        <p className="flex flex-wrap items-center gap-1">
          <span className="font-mono">[{item.id}]</span><Badge variant="muted">{t('assistant.note')}</Badge>
          <span className="font-medium" dir="auto">{title}</span>
        </p>
        <p className="mt-0.5 whitespace-pre-wrap" dir="auto">{language === 'ar' && item.text_ar ? item.text_ar : item.text}</p>
      </li>
    );
  }
  if (item.kind !== 'observation') {
    return (
      <li id={anchor} tabIndex={-1} className="scroll-mt-4 text-xs focus-visible:outline-2">
        <span className="font-mono">[{item.id}]</span> <DataStatusBadge status={item.data_status} /> {pick(item.name, language)} — {pick(item.definition, language)}
      </li>
    );
  }
  const operator = typeof item.value_operator === 'string' && item.value_operator in OPERATOR
    ? OPERATOR[item.value_operator as keyof typeof OPERATOR]
    : null;
  const source = item.source;
  return (
    <li id={anchor} tabIndex={-1} className="scroll-mt-4 rounded-md border border-border bg-background p-2 text-xs focus-visible:outline-2"
      data-testid="citation" data-evidence={item.id} data-class={cls ?? ''}>
      <p className="flex flex-wrap items-center gap-1">
        <span className="font-mono">[{item.id}]</span>
        {cls ? <Badge variant={cls === 'observed' ? 'verified' : 'sand'} data-testid="evidence-class">{t(EVIDENCE_CLASS_KEY[cls])}</Badge> : null}
        <DataStatusBadge status={item.data_status} />
        <span className="font-medium">{pick(item.indicator_name, language)}</span> · {pick(item.area_name, language)} ·{' '}
        {item.period_start && item.period_end ? formatPeriod(item.period_start, item.period_end, language) : null}
        {item.period_kind === 'year_to_date' ? <Badge variant="sand">{t('frequency.year_to_date')}</Badge>
          : item.period_complete === false ? <Badge variant="sand">{t('table.incompletePeriod')}</Badge> : null}
      </p>
      <p className="mt-0.5">
        <span className="tabular-nums" dir="ltr">
          {item.value == null ? t('states.dataUnavailable') : `${operator ? `${operator} ` : ''}${formatDecimal(item.value, language, 4) ?? ''}`}
        </span>{' '}
        {pick(item.unit_label, language) || item.unit}
        {typeof item.revision_status === 'string' ? <> · {t(`revisionStatus.${item.revision_status as 'reported'}`)}</> : null}
        {item.data_mode === 'synthetic' && !item.data_status ? <> · <Badge variant="synthetic">{t('dataMode.synthetic')}</Badge></> : null}
      </p>
      {source ? (
        <p className="mt-0.5 text-muted-foreground">
          {source.url ? (
            <a href={source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary underline underline-offset-2">
              <bdi>{source.title}</bdi><ExternalLink aria-hidden="true" className="size-3" />
            </a>
          ) : <bdi>{source.title}</bdi>}
          {source.publisher ? ` · ${source.publisher}` : ''}
          {typeof item.record_ref === 'string' ? <> · <span dir="ltr" className="font-mono">{item.record_ref}{source.locator ? `, ${source.locator}` : ''}</span></> : null}
          {' · '}{t('analysis.version')} <span dir="ltr">{item.dataset_version}</span>
        </p>
      ) : null}
    </li>
  );
}

/** Saves one reply (with its evidence and validated parts) to the reader's research library. */
export function SaveResearchButton({ messageId }: { messageId: number }) {
  const { t } = useTranslation();
  const save = useSaveResearch();
  const to = usePreservedSearch();
  if (save.isSuccess) {
    const target = to('/library');
    return (
      <p className="text-xs" role="status" data-testid="research-saved">
        {t('assistant.saved')} ·{' '}
        <Link to={{ pathname: target.pathname, search: `${target.search ? `${target.search}&` : '?'}tab=saved` }}
          className="text-primary underline underline-offset-2">{t('assistant.openLibrary')}</Link>
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <Button variant="outline" size="sm" className="w-fit" disabled={save.isPending} data-testid="save-research"
        onClick={() => save.mutate({ message_id: messageId })}>
        <BookmarkPlus aria-hidden="true" />{t('assistant.save')}
      </Button>
      {save.error ? <p className="text-xs text-destructive" role="alert">{t('assistant.saveFailed', { message: save.error.message })}</p> : null}
    </div>
  );
}

export const SAVEABLE = new Set(['answered', 'no_evidence', 'clarification', 'lookup']);
