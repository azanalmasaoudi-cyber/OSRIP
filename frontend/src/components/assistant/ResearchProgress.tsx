import { useTranslation } from 'react-i18next';

import { PROGRESS_STAGES, type StructuredReply } from '@/api/assistant';

type Stage = (typeof PROGRESS_STAGES)[number];
const isStage = (s: string): s is Stage => (PROGRESS_STAGES as readonly string[]).includes(s);
const ANSWER_PROVIDERS = { anthropic: 1, openai: 1, gemini: 1, fake: 1 } as const;
const SEARCH_ROUTES = ['brave', 'openai', 'gemini', 'fake-search', 'fake-openai', 'fake-gemini'] as const;

/** "How this answer was prepared": counts the server took from what was actually done. */
export function MethodSummary({ method }: { method: NonNullable<StructuredReply['method']> }) {
  const { t, i18n } = useTranslation();
  const steps = method.steps.filter(isStage).filter((s) => s !== 'done' && s !== 'cancelled');
  const languages = method.search_languages
    .map((l) => (l === 'ar' ? t('workflow.method.languageAr') : l === 'en' ? t('workflow.method.languageEn') : l))
    .join(i18n.language === 'ar' ? '، ' : ', ');
  const separator = i18n.language === 'ar' ? '، ' : ', ';
  const lines: string[] = [];
  // Which provider answered (one per question), and why a fallback did if it did.
  if (method.answer_provider) {
    const provider = method.answer_provider in ANSWER_PROVIDERS
      ? t(`workflow.method.provider.${method.answer_provider as keyof typeof ANSWER_PROVIDERS}`) : method.answer_provider;
    lines.push(method.answer_model
      ? t('workflow.method.answeredByModel', { provider, model: method.answer_model })
      : t('workflow.method.answeredBy', { provider }));
  }
  if (method.answer_fallback) {
    const name = (p: string | null) => (p && p in ANSWER_PROVIDERS ? t(`workflow.method.provider.${p as keyof typeof ANSWER_PROVIDERS}`) : p ?? '—');
    lines.push(t('workflow.method.fallback', {
      to: name(method.answer_fallback.to), from: name(method.answer_fallback.from), reason: method.answer_fallback.reason,
    }));
  }
  if (method.route?.numerical && !method.route.web_first) lines.push(t('workflow.method.routeNumerical'));
  else if (method.route?.web_first && method.route.recent) lines.push(t('workflow.method.routeRecent'));
  const routes = method.search_routes ?? [];
  if (routes.length) {
    const unique = [...new Map(routes.map((r) => [`${r.provider}:${r.role}`, r])).values()];
    lines.push(t('workflow.method.searchRoutes', {
      routes: unique.map((r) => {
        const label = (SEARCH_ROUTES as readonly string[]).includes(r.provider) ? t(`web.provider.${r.provider as 'brave'}`) : r.provider;
        return r.role === 'primary' ? label : `${label} (${t(`web.route.${r.role === 'fallback' ? 'fallback' : 'cross_check'}`)})`;
      }).join(separator),
    }));
  }
  if (routes.some((r) => r.role === 'cross_check')) lines.push(t('workflow.method.crossCheck'));
  if (method.provider_summaries) lines.push(t('workflow.method.providerSummaries', { count: method.provider_summaries }));
  if (method.grounded_results) lines.push(t('workflow.method.grounded', { count: method.grounded_results }));
  if (steps.length) lines.push(t('workflow.method.steps', { steps: steps.map((s) => t(`workflow.stage.${s}`)).join(' → ') }));
  if (method.published_records) lines.push(t('workflow.method.records', { count: method.published_records }));
  if (method.calculations) lines.push(t('workflow.method.calculations', { count: method.calculations }));
  if (method.studies) lines.push(t('workflow.method.studies', { count: method.studies }));
  lines.push(method.searches ? t('workflow.method.searches', { count: method.searches, languages }) : t('workflow.method.noSearch'));
  if (method.failed_searches) lines.push(t('workflow.method.failedSearches', { count: method.failed_searches }));
  if (method.web_results) lines.push(t('workflow.method.results', { count: method.web_results }));
  if (method.pages_read) lines.push(t('workflow.method.pages', { count: method.pages_read }));
  if (method.stale_sources) lines.push(t('workflow.method.stale', { count: method.stale_sources }));
  if (method.undated_sources) lines.push(t('workflow.method.undated', { count: method.undated_sources }));
  return (
    <details className="rounded-md border border-border p-2 text-xs" data-testid="reply-method">
      <summary className="cursor-pointer font-semibold">{t('workflow.method.heading')}</summary>
      <ul className="mt-1.5 list-disc ps-4 text-muted-foreground">
        {lines.map((line) => <li key={line}>{line}</li>)}
      </ul>
    </details>
  );
}
