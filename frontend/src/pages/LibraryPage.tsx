import { Bell, BookOpen, Download, ExternalLink, Eye, FileText, Trash2 } from 'lucide-react';
import { useId, useRef, useState, type KeyboardEvent } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useMe } from '@/api/auth';
import {
  downloadBrief,
  SOURCE_FILTERS,
  useAddRule,
  useAlerts,
  useDeleteRule,
  useDeleteSaved,
  useMarkAlertsRead,
  useSavedResearch,
  useSourceLibrary,
  useUnwatch,
  useUpdateRule,
  useUpdateSaved,
  useWatchlist,
  type AlertRule,
  type LibrarySource,
  type SavedResearch,
  type SourceFilter,
  type WatchItem,
} from '@/api/library';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { PageHeader } from '@/components/common/PageHeader';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SelectField } from '@/components/ui/select';
import { formatDecimal, formatPeriod, type AppLanguage } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const TABS = ['sources', 'saved', 'watch'] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL = { sources: 'library.tabSources', saved: 'library.tabSaved', watch: 'library.tabWatch' } as const;
const TAB_ICON = { sources: BookOpen, saved: FileText, watch: Bell } as const;

function day(value: string | null | undefined, language: AppLanguage): string {
  if (!value) return '';
  const d = value.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(d) ? formatPeriod(d, d, language) : value;
}

function SignInNeeded() {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  return (
    <div className="rounded-lg border border-dashed border-border-strong/60 p-4 text-sm" role="status" data-testid="library-sign-in">
      <p>{t('library.signInNeeded')}</p>
      <Link to={to('/sign-in')} className="mt-2 inline-block rounded-md bg-primary px-3 py-2 font-medium text-primary-foreground">{t('auth.signIn')}</Link>
    </div>
  );
}

// ------------------------------------------------------------------ source library

function SourceRow({ source }: { source: LibrarySource }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const cls = source.source_class as 'official' | 'international' | 'research' | 'secondary' | 'crosscheck';
  const known = ['official', 'international', 'research', 'secondary', 'crosscheck'].includes(cls);
  return (
    <li className="rounded-md border border-border bg-card p-3 text-sm" data-testid="library-source" data-kind={source.kind} data-class={source.source_class}>
      <p className="flex flex-wrap items-center gap-1.5 text-xs">
        <Badge variant={source.kind === 'web_found' ? 'sand' : 'verified'}>{t(`library.kind.${source.kind}`)}</Badge>
        {known ? <Badge variant="outline">{t(`library.cls.${cls}`)}</Badge> : null}
        {source.code ? <span className="font-mono text-muted-foreground" dir="ltr">{source.code}</span> : null}
      </p>
      <p className="mt-1 font-medium" dir="auto">
        {source.url ? (
          <a href={source.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-start gap-1 text-primary underline underline-offset-2">
            <bdi>{source.title}</bdi><ExternalLink aria-hidden="true" className="mt-1 size-3 shrink-0" />
          </a>
        ) : <bdi>{source.title}</bdi>}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        {source.publisher ? <bdi>{source.publisher}</bdi> : null}
        {source.publication ? <> · <bdi>{source.publication}</bdi></> : null}
        {source.reference_period ? <> · <bdi>{source.reference_period}</bdi></> : null}
        {source.publication_date ? <> · {t('library.published', { date: day(source.publication_date, language) })}</> : null}
        {source.accessed_on ? <> · {t('library.accessed', { date: day(source.accessed_on, language) })}</> : null}
        {source.retrieved_at ? <> · {t('library.retrieved', { date: day(source.retrieved_at, language) })}</> : null}
      </p>
      {source.published_records != null ? <p className="mt-0.5 text-xs">{t('library.records', { count: source.published_records })}</p> : null}
      {source.kind === 'web_found' ? (
        <p className="mt-0.5 text-xs">
          {t('library.figures', { found: source.figures_found ?? 0, accepted: source.figures_accepted ?? 0 })}
          {source.figures_pending != null ? <> · {t('library.pending', { count: source.figures_pending })}</> : null}
        </p>
      ) : null}
    </li>
  );
}

function SourcesTab() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [q, setQ] = useState('');
  const [cls, setCls] = useState<SourceFilter | ''>('');
  const query = useSourceLibrary(q, cls);
  const searchId = useId();
  const labels: Record<SourceFilter, string> = {
    official: t('library.cls.official'),
    international: t('library.cls.international'),
    research: t('library.cls.research'),
    secondary: t('library.cls.secondary'),
    reference_pack: t('library.kind.reference_pack'),
    dataset: t('library.kind.dataset'),
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <label htmlFor={searchId} className="text-xs font-medium text-muted-foreground">{t('library.search')}</label>
          <input id={searchId} type="search" value={q} onChange={(e) => setQ(e.target.value.slice(0, 100))} dir="auto"
            className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm" data-testid="library-search" />
        </div>
        <SelectField className="w-full sm:w-56" label={t('library.classFilter')} value={cls}
          onValueChange={(v) => setCls(SOURCE_FILTERS.find((f) => f === v) ?? '')}
          options={[{ value: '', label: t('library.allClasses') }, ...SOURCE_FILTERS.map((f) => ({ value: f, label: labels[f] }))]}
          data-testid="library-class" />
      </div>
      {query.data ? <p className="text-xs text-muted-foreground">{language === 'ar' ? query.data.note.ar : query.data.note.en}</p> : null}
      {query.isPending ? <StatePanel kind="loading" skeleton="lines" />
        : query.isError ? <StatePanel kind="error" detail={query.error.message} onRetry={() => void query.refetch()} />
          : query.data.sources.length === 0 ? <p className="text-sm" role="status">{t('library.noSources')}</p>
            : (
              <ul className="grid gap-2 md:grid-cols-2" aria-busy={query.isFetching}>
                {query.data.sources.map((s, i) => <SourceRow key={`${s.kind}-${s.code ?? s.url ?? i}`} source={s} />)}
              </ul>
            )}
    </div>
  );
}

// ------------------------------------------------------------------ saved research

function SavedItem({ item }: { item: SavedResearch }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const update = useUpdateSaved();
  const remove = useDeleteSaved();
  const [title, setTitle] = useState(item.title);
  const [note, setNote] = useState(item.note ?? '');
  const [confirm, setConfirm] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const titleId = useId();
  const noteId = useId();
  const changed = title.trim() !== item.title || note !== (item.note ?? '');
  const download = (format: 'html' | 'md') => {
    setDownloadError(null);
    downloadBrief(item.id, format).catch((e: Error) => setDownloadError(e.message));
  };
  return (
    <li className="flex flex-col gap-2 rounded-md border border-border bg-card p-3 text-sm" data-testid="saved-item">
      <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        {item.mode ? <Badge variant="outline">{t(`assistant.mode.${item.mode as 'ask'}`)}</Badge> : null}
        <DataModeBadge mode={item.data_mode} />
        <span>{t('library.savedOn', { date: day(item.created_at, language) })}</span>
        <span>· {t('library.sourcesCount', { count: item.source_count })}</span>
        {item.recommendation_count ? <span>· {t('library.cardsCount', { count: item.recommendation_count })}</span> : null}
      </p>
      <p className="text-xs"><span className="font-semibold">{t('library.question')}:</span> <bdi dir="auto">{item.question}</bdi></p>
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor={titleId} className="text-xs font-medium text-muted-foreground">{t('library.rename')}</label>
          <input id={titleId} value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} dir="auto"
            className="h-9 rounded-md border border-border-strong bg-background px-2 text-sm" />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={noteId} className="text-xs font-medium text-muted-foreground">{t('library.noteLabel')}</label>
          <input id={noteId} value={note} maxLength={4000} onChange={(e) => setNote(e.target.value)} dir="auto"
            className="h-9 rounded-md border border-border-strong bg-background px-2 text-sm" />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={!changed || !title.trim() || update.isPending}
          onClick={() => update.mutate({ id: item.id, title: title.trim(), note })}>{t('library.saveChanges')}</Button>
        <Button size="sm" variant="outline" onClick={() => download('html')} data-testid="brief-html"><Download aria-hidden="true" />{t('library.downloadHtml')}</Button>
        <Button size="sm" variant="outline" onClick={() => download('md')} data-testid="brief-md"><Download aria-hidden="true" />{t('library.downloadMd')}</Button>
        <Button size="sm" variant={confirm ? 'default' : 'ghost'} disabled={remove.isPending} data-testid="saved-remove"
          onClick={() => { if (!confirm) { setConfirm(true); return; } remove.mutate(item.id); }}>
          <Trash2 aria-hidden="true" />{confirm ? t('library.confirmRemove') : t('library.remove')}
        </Button>
      </div>
      {update.error || remove.error || downloadError ? (
        <p className="text-xs text-destructive" role="alert">{update.error?.message ?? remove.error?.message ?? downloadError}</p>
      ) : null}
    </li>
  );
}

function SavedTab({ signedIn }: { signedIn: boolean }) {
  const { t } = useTranslation();
  const saved = useSavedResearch(signedIn);
  if (!signedIn) return <SignInNeeded />;
  if (saved.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (saved.isError) return <StatePanel kind="error" detail={saved.error.message} onRetry={() => void saved.refetch()} />;
  if (!saved.data.length) return <p className="text-sm" role="status" data-testid="saved-empty">{t('library.savedEmpty')}</p>;
  return <ul className="flex flex-col gap-2">{saved.data.map((s) => <SavedItem key={s.id} item={s} />)}</ul>;
}

// ------------------------------------------------------------------ watchlist and alerts

function RuleRow({ rule, unit }: { rule: AlertRule; unit: string }) {
  const { t } = useTranslation();
  const update = useUpdateRule();
  const remove = useDeleteRule();
  // The requested state shows at once; the saved rule replaces it when the server answers
  // (on failure the saved state comes back with the error).
  const [requested, setRequested] = useState<boolean | null>(null);
  const enabled = requested ?? rule.enabled;
  return (
    <li className="flex flex-wrap items-center gap-2 text-xs" data-testid="alert-rule" data-kind={rule.kind}>
      <span className="font-medium">{t(`library.ruleKind.${rule.kind}`)}</span>
      {rule.threshold != null ? <span className="tabular-nums" dir="ltr">{rule.threshold} {unit}</span> : null}
      <Badge variant="muted">{t(`library.channel.${rule.channel}`)}</Badge>
      <label className="ms-auto flex items-center gap-1">
        <input type="checkbox" className="size-4 accent-primary" checked={enabled} aria-busy={update.isPending}
          onChange={(e) => {
            setRequested(e.target.checked);
            update.mutate({ id: rule.id, enabled: e.target.checked }, { onSettled: () => setRequested(null) });
          }} />
        {enabled ? t('library.enabled') : t('library.disabled')}
      </label>
      <Button size="sm" variant="ghost" onClick={() => remove.mutate(rule.id)} disabled={remove.isPending} aria-label={t('library.deleteRule')}>
        <Trash2 aria-hidden="true" />
      </Button>
      {update.error ? <span className="w-full text-destructive" role="alert">{update.error.message}</span> : null}
    </li>
  );
}

function AddRule({ item, unit }: { item: WatchItem; unit: string }) {
  const { t } = useTranslation();
  const add = useAddRule();
  const [kind, setKind] = useState<AlertRule['kind']>('new_data');
  const [channel, setChannel] = useState<AlertRule['channel']>('in_app');
  const [threshold, setThreshold] = useState('');
  const thresholdId = useId();
  const needsThreshold = kind !== 'new_data';
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => {
      e.preventDefault();
      add.mutate({ itemId: item.id, kind, channel, threshold: needsThreshold ? threshold : undefined },
        { onSuccess: () => setThreshold('') });
    }}>
      <SelectField className="w-44" label={t('library.rules')} value={kind} onValueChange={(v) => setKind(v === 'above' || v === 'below' ? v : 'new_data')}
        options={(['new_data', 'above', 'below'] as const).map((k) => ({ value: k, label: t(`library.ruleKind.${k}`) }))} />
      {needsThreshold ? (
        <div className="flex flex-col gap-1.5">
          <label htmlFor={thresholdId} className="text-xs font-medium text-muted-foreground">{t('library.threshold', { unit })}</label>
          <input id={thresholdId} inputMode="decimal" required value={threshold} dir="ltr"
            onChange={(e) => setThreshold(e.target.value.replace(/[^\d.-]/g, '').slice(0, 20))}
            className="h-10 w-32 rounded-md border border-border-strong bg-card px-2 text-sm tabular-nums" />
        </div>
      ) : null}
      <SelectField className="w-40" label={t('library.channel.in_app')} labelClassName="sr-only" value={channel}
        onValueChange={(v) => setChannel(v === 'email' ? 'email' : 'in_app')}
        options={(['in_app', 'email'] as const).map((c) => ({ value: c, label: t(`library.channel.${c}`) }))} />
      <Button size="sm" type="submit" disabled={add.isPending || (needsThreshold && !threshold)}>{t('library.addRule')}</Button>
      {add.error ? <p className="w-full text-xs text-destructive" role="alert">{add.error.message}</p> : null}
    </form>
  );
}

function WatchRow({ item }: { item: WatchItem }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const unwatch = useUnwatch();
  const unit = item.unit ? (language === 'ar' ? item.unit.label_ar : item.unit.label_en) : '';
  const name = (n: { en: string; ar: string } | null, code: string) => (n ? (language === 'ar' ? n.ar : n.en) : code);
  return (
    <li className="flex flex-col gap-2 rounded-md border border-border bg-card p-3 text-sm" data-testid="watch-item">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{name(item.indicator.name, item.indicator.code)} · {name(item.area.name, item.area.code)}</p>
          <p className="text-xs text-muted-foreground">
            <DataModeBadge mode={item.data_mode} /> {item.latest ? t('library.latest', {
              value: `${item.latest.value_operator ?? ''}${item.latest.value == null ? '—' : formatDecimal(item.latest.value, language, 4) ?? ''}`,
              unit,
              period: formatPeriod(item.latest.period_start, item.latest.period_end, language),
            }) : t('library.noValue')}
          </p>
          {item.change?.percent != null ? (
            <p className="text-xs">{t('library.change', { value: formatDecimal(item.change.percent, language, 2) ?? '' })}</p>
          ) : null}
        </div>
        <Button size="sm" variant="ghost" onClick={() => unwatch.mutate(item.id)} disabled={unwatch.isPending} data-testid="unwatch">
          {t('library.unwatch')}
        </Button>
      </div>
      {item.rules.length ? <ul className="flex flex-col gap-1 border-t border-border pt-2">{item.rules.map((r) => <RuleRow key={r.id} rule={r} unit={unit} />)}</ul> : null}
      <AddRule item={item} unit={unit} />
    </li>
  );
}

function AlertsList({ signedIn }: { signedIn: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const alerts = useAlerts(signedIn);
  const read = useMarkAlertsRead();
  if (!alerts.data) return null;
  return (
    <section aria-labelledby="alerts-heading" className="flex flex-col gap-2" data-testid="alerts-list">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="alerts-heading" className="text-base font-semibold">{t('library.alertsTitle')}</h2>
        <span className="text-xs text-muted-foreground" role="status">{t('library.unread', { count: alerts.data.unread })}</span>
        {alerts.data.unread ? <Button size="sm" variant="outline" className="ms-auto" onClick={() => read.mutate(undefined)}>{t('library.markAllRead')}</Button> : null}
      </div>
      {alerts.data.events.length === 0 ? <p className="text-sm">{t('library.noAlerts')}</p> : (
        <ul className="flex flex-col gap-1.5">
          {alerts.data.events.map((e) => (
            <li key={e.id} className={cn('rounded-md border p-2 text-xs', e.read_at ? 'border-border' : 'border-primary/50 bg-primary/5')} data-testid="alert-event">
              <p dir="auto">{language === 'ar' ? e.message.ar : e.message.en}</p>
              <p className="mt-0.5 text-muted-foreground">{day(e.created_at, language)} · {t(`library.delivery.${e.delivery}`)}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function WatchTab({ signedIn }: { signedIn: boolean }) {
  const { t } = useTranslation();
  const watchlist = useWatchlist(signedIn);
  if (!signedIn) return <SignInNeeded />;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground">{t('library.alertsNote')}</p>
      {watchlist.isPending ? <StatePanel kind="loading" skeleton="lines" />
        : watchlist.isError ? <StatePanel kind="error" detail={watchlist.error.message} onRetry={() => void watchlist.refetch()} />
          : watchlist.data.length === 0 ? <p className="flex items-center gap-1 text-sm" role="status"><Eye aria-hidden="true" className="size-4" />{t('library.watchEmpty')}</p>
            : <ul className="flex flex-col gap-2">{watchlist.data.map((w) => <WatchRow key={w.id} item={w} />)}</ul>}
      <AlertsList signedIn={signedIn} />
    </div>
  );
}

// ------------------------------------------------------------------ page

export function LibraryPage() {
  const { t } = useTranslation();
  const me = useMe();
  const signedIn = Boolean(me.data?.authenticated);
  const [params, setParams] = useSearchParams();
  const tab: Tab = TABS.find((x) => x === params.get('tab')) ?? 'sources';
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const baseId = useId();
  const choose = (next: Tab) => setParams((p) => {
    const copy = new URLSearchParams(p);
    if (next === 'sources') copy.delete('tab');
    else copy.set('tab', next);
    return copy;
  }, { replace: true });
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const rtl = getComputedStyle(event.currentTarget).direction === 'rtl';
    const i = TABS.indexOf(tab);
    let next = i;
    if (event.key === (rtl ? 'ArrowLeft' : 'ArrowRight')) next = (i + 1) % TABS.length;
    else if (event.key === (rtl ? 'ArrowRight' : 'ArrowLeft')) next = (i - 1 + TABS.length) % TABS.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = TABS.length - 1;
    else return;
    event.preventDefault();
    const target = TABS[next];
    if (target) choose(target);
    refs.current[next]?.focus();
  };
  return (
    <>
      <PageHeader title={t('library.title')} intro={t('library.intro')} />
      <div role="tablist" aria-label={t('library.title')} className="mb-4 flex flex-wrap gap-1 border-b border-border">
        {TABS.map((x, i) => {
          const Icon = TAB_ICON[x];
          return (
            <button key={x} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" id={`${baseId}-${x}`}
              aria-selected={tab === x} aria-controls={`${baseId}-${x}-panel`} tabIndex={tab === x ? 0 : -1}
              onClick={() => choose(x)} onKeyDown={onKeyDown} data-testid={`library-tab-${x}`}
              className={cn('-mb-px inline-flex min-h-10 items-center gap-1.5 border-b-2 px-3 py-2 text-sm',
                tab === x ? 'border-primary font-semibold text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground')}>
              <Icon aria-hidden="true" className="size-4" />{t(TAB_LABEL[x])}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${baseId}-${tab}-panel`} aria-labelledby={`${baseId}-${tab}`} tabIndex={0}>
        {tab === 'sources' ? <SourcesTab /> : tab === 'saved' ? <SavedTab signedIn={signedIn} /> : <WatchTab signedIn={signedIn} />}
      </div>
    </>
  );
}
