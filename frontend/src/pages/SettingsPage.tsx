import { CalendarClock, CircleHelp, Play, ServerCog, Trash2, UserRound } from 'lucide-react';
import { useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useAssistantStatus, useVoiceStatus } from '@/api/assistant';
import { hasPermission, useMe } from '@/api/auth';
import { SECTORS, type Sector } from '@/api/balance';
import { adapterKind } from '@/api/config';
import {
  SOURCE_SCOPES, useRetrievalStatus, useScheduleMutation, useSchedules, type ReportSchedule, type SourceScope,
} from '@/api/researchJobs';
import { ServiceChip } from '@/components/assistant/AssistantIdentityCard';
import { PageHeader } from '@/components/common/PageHeader';
import { ProviderReadiness } from '@/components/common/ProviderReadiness';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SelectField } from '@/components/ui/select';
import { formatDate } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * Settings: preferences; what is set up on this server (the answer service with its latest
 * outcome, voice, web search, page retrieval), with setup notes that name settings but never
 * show their values; scheduled reports for administrators (off by default); and help.
 */
export function SettingsPage() {
  const { t } = useTranslation();
  const me = useMe();
  const to = usePreservedSearch();
  const api = adapterKind === 'http';
  const admin = hasPermission(me.data, 'user.manage');
  const auditor = hasPermission(me.data, 'audit.read');
  return (
    <>
      <PageHeader title={t('settingsPage.title')} intro={t('settingsPage.intro')} />
      <div className="grid max-w-5xl gap-6">
        <p>
          <Link to={to('/account')} className="inline-flex items-center gap-1.5 text-sm text-primary underline underline-offset-2" data-testid="settings-account">
            <UserRound aria-hidden="true" className="size-4" />{t('settingsPage.account')}
          </Link>
        </p>
        <SettingsSection />
        {api ? <Services admin={admin} /> : null}
        {api && auditor ? <ProviderReadiness enabled={auditor} canTest={admin} /> : null}
        {api && admin ? <Schedules /> : null}
        <Help />
      </div>
    </>
  );
}

function Row({ label, children, testid }: { label: string; children: ReactNode; testid: string }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2 border-t border-border py-2 first:border-0" data-testid={testid}>
      <span className="text-sm font-medium">{label}</span>
      <span className="flex max-w-xl flex-col items-end gap-1 text-end text-sm">{children}</span>
    </div>
  );
}

function Services({ admin }: { admin: boolean }) {
  const { t } = useTranslation();
  const status = useAssistantStatus();
  const voice = useVoiceStatus();
  const retrieval = useRetrievalStatus(admin);
  const s = status.data;
  const failing = s?.health?.state === 'failing' ? s.health.category : null;
  return (
    <section className="surface-card flex flex-col gap-2 p-5" aria-labelledby="services-h" data-testid="settings-services">
      <h2 id="services-h" className="flex items-center gap-2 text-lg font-semibold"><ServerCog aria-hidden="true" className="size-5" />{t('settingsPage.services')}</h2>
      <Row label={t('settingsPage.answers')} testid="service-answers">
        <ServiceChip />
        {s?.provider ? <span className="text-xs text-muted-foreground" dir="ltr">{s.provider} · {s.model}</span> : null}
        {failing ? <span className="text-xs">{t(`assistant.health.category.${failing}`, { defaultValue: '' })} {t(`settingsPage.fix.${failing}`, { defaultValue: t('settingsPage.fix.other') })}</span> : null}
        {s && !s.configured ? <span className="text-xs text-muted-foreground">{t('settingsPage.fix.not_configured')}</span> : null}
      </Row>
      <Row label={t('settingsPage.voice')} testid="service-voice">
        <Badge variant={voice.data?.configured ? 'verified' : 'muted'}>{voice.data?.configured ? t('voicePanel.ready') : t('voicePanel.notConfigured')}</Badge>
        {voice.data && !voice.data.configured ? <span className="text-xs text-muted-foreground">{t('voicePanel.setup')}</span> : null}
      </Row>
      <Row label={t('settingsPage.search')} testid="service-search">
        <Badge variant={!s?.web_research ? 'muted' : s.search_health?.state === 'failing' ? 'sand' : 'verified'} data-state={s?.search_health?.state}>
          {s?.web_research ? `${s.web_research_provider ?? t('settingsPage.on')}${s.search_health?.state === 'failing' ? ` · ${t('settingsPage.failing')}` : ''}` : t('settingsPage.notSetUp')}
        </Badge>
        {s?.search_health?.state === 'failing' && s.search_health.category ? (
          <span className="text-xs">{t(`assistant.health.category.${s.search_health.category}`, { defaultValue: '' })} {t('settingsPage.fix.search')}</span>
        ) : null}
        {s && !s.web_research ? <span className="text-xs text-muted-foreground">{t('settingsPage.fix.search')}</span> : null}
      </Row>
      {admin && retrieval.data ? (
        <Row label={t('settingsPage.retrieval')} testid="service-retrieval">
          <Badge variant={retrieval.data.retrieval.firecrawl === 'configured' ? 'verified' : 'muted'} data-state={retrieval.data.retrieval.firecrawl}>
            {t(`settingsPage.firecrawl.${retrieval.data.retrieval.firecrawl}`)}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {t('settingsPage.limits', { pages: retrieval.data.limits.max_pages, depth: retrieval.data.limits.max_depth,
              seconds: retrieval.data.limits.max_runtime_seconds, credits: retrieval.data.limits.max_credits })}
          </span>
          {retrieval.data.retrieval.firecrawl !== 'configured' ? <span className="text-xs text-muted-foreground">{t('settingsPage.fix.firecrawl')}</span> : null}
        </Row>
      ) : null}
    </section>
  );
}

const EMPTY = { name: '', sector: 'water' as Sector, question: '', frequency: 'monthly' as const, source_scope: 'none' as SourceScope,
  max_pages: 5, max_credits_per_run: 25, max_credits_per_month: 100, allow_paid: false };

function Schedules() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const status = useRetrievalStatus(true);
  const list = useSchedules(true);
  const mutate = useScheduleMutation();
  const [form, setForm] = useState(EMPTY);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    mutate.mutate({ body: { ...form, area: 'OM', data_mode: mode, language, question: form.question || t(`jobs.defaultQuestion.${form.sector}`), enabled: false } },
      { onSuccess: () => setForm(EMPTY) });
  };
  const toggle = (s: ReportSchedule) => mutate.mutate({ id: s.id, body: { enabled: !s.enabled } });
  return (
    <section className="surface-card flex flex-col gap-3 p-5" aria-labelledby="schedules-h" data-testid="settings-schedules">
      <h2 id="schedules-h" className="flex items-center gap-2 text-lg font-semibold"><CalendarClock aria-hidden="true" className="size-5" />{t('schedules.title')}</h2>
      <p className="text-sm text-muted-foreground">{t('schedules.intro')}</p>
      {status.data && !status.data.scheduler_enabled ? (
        <p className="rounded-md border border-dashed border-border-strong/60 p-2 text-sm" role="status" data-testid="scheduler-off">{t('schedules.serverOff')}</p>
      ) : null}
      <ul className="flex flex-col divide-y divide-border">
        {(list.data ?? []).map((s) => (
          <li key={s.id} className="flex flex-wrap items-center gap-2 py-2 text-sm" data-testid="schedule-row" data-enabled={s.enabled ? 'true' : 'false'}>
            <span className="min-w-0 flex-1">
              <span className="font-medium">{s.name}</span>
              <span className="block text-xs text-muted-foreground">
                {t(`balance.sectors.${s.sector}`, { defaultValue: s.sector })} · {t(`schedules.frequency.${s.frequency}`)} · {t(`jobs.scope.${s.source_scope}`)}
                {s.paid ? ` · ${t('schedules.paid')}` : ''} · {t('schedules.credits', { used: s.credits_this_month ?? 0, cap: s.max_credits_per_month })}
                {s.next_run_at ? ` · ${t('schedules.next', { date: formatDate(s.next_run_at, language) })}` : ''}
              </span>
            </span>
            <Badge variant={s.enabled ? 'verified' : 'muted'}>{s.enabled ? t('schedules.enabled') : t('schedules.disabled')}</Badge>
            <Button type="button" size="sm" variant="outline" disabled={mutate.isPending || (s.paid && !s.allow_paid && !s.enabled)} onClick={() => toggle(s)} data-testid="schedule-toggle">
              {s.enabled ? t('schedules.disable') : t('schedules.enable')}
            </Button>
            <Button type="button" size="sm" variant="ghost" disabled={mutate.isPending} onClick={() => mutate.mutate({ id: s.id, action: 'run' })} data-testid="schedule-run">
              <Play aria-hidden="true" />{t('schedules.runNow')}
            </Button>
            <Button type="button" size="sm" variant="ghost" aria-label={`${t('schedules.delete')}: ${s.name}`} disabled={mutate.isPending}
              onClick={() => mutate.mutate({ id: s.id, action: 'delete' })}>
              <Trash2 aria-hidden="true" className="size-4" />
            </Button>
          </li>
        ))}
      </ul>
      {mutate.isError ? <p role="alert" className="text-sm text-destructive">{mutate.error.message}</p> : null}
      <form onSubmit={submit} className="grid gap-3 rounded-md border border-border p-3 sm:grid-cols-2" data-testid="schedule-form">
        <label className="flex flex-col gap-1 text-xs font-medium">{t('schedules.name')}
          <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value.slice(0, 120) })} className="h-9 rounded-md border border-border-strong bg-card px-2 text-sm" data-testid="schedule-name" />
        </label>
        <SelectField label={t('balance.sector')} value={form.sector} onValueChange={(v) => setForm({ ...form, sector: v as Sector })}
          options={SECTORS.map((s) => ({ value: s, label: t(`balance.sectors.${s}`) }))} />
        <SelectField label={t('schedules.frequencyLabel')} value={form.frequency} onValueChange={(v) => setForm({ ...form, frequency: v as typeof form.frequency })}
          options={(['weekly', 'monthly', 'quarterly'] as const).map((f) => ({ value: f, label: t(`schedules.frequency.${f}`) }))} />
        <SelectField label={t('jobs.scope.label')} value={form.source_scope} onValueChange={(v) => setForm({ ...form, source_scope: v as SourceScope })}
          options={SOURCE_SCOPES.map((s) => ({ value: s, label: t(`jobs.scope.${s}`) }))} data-testid="schedule-scope" />
        {(['max_pages', 'max_credits_per_run', 'max_credits_per_month'] as const).map((k) => (
          <label key={k} className="flex flex-col gap-1 text-xs font-medium">{t(`schedules.${k}`)}
            <input type="number" min={0} value={form[k]} onChange={(e) => setForm({ ...form, [k]: Number(e.target.value) })} dir="ltr"
              className="h-9 rounded-md border border-border-strong bg-card px-2 text-sm" />
          </label>
        ))}
        <label className="flex items-center gap-2 text-xs font-medium sm:col-span-2">
          <input type="checkbox" checked={form.allow_paid} onChange={(e) => setForm({ ...form, allow_paid: e.target.checked })} className="size-4 accent-primary" data-testid="schedule-allow-paid" />
          {t('schedules.allowPaid')}
        </label>
        <p className="text-xs text-muted-foreground sm:col-span-2">{t('schedules.createdOff')}</p>
        <Button type="submit" className="w-fit" disabled={mutate.isPending} data-testid="schedule-create">{t('schedules.create')}</Button>
      </form>
    </section>
  );
}

function Help() {
  const { t } = useTranslation();
  const items = ['dataReport', 'evidence', 'microphone', 'voices', 'introClips', 'portrait', 'studies', 'retrieval'] as const;
  return (
    <section className="surface-card flex flex-col gap-2 p-5" aria-labelledby="help-h" data-testid="settings-help">
      <h2 id="help-h" className="flex items-center gap-2 text-lg font-semibold"><CircleHelp aria-hidden="true" className="size-5" />{t('settingsPage.help')}</h2>
      {items.map((k) => (
        <details key={k} className="rounded-md border border-border px-3 py-2 text-sm" data-testid={`help-${k}`}>
          <summary className="cursor-pointer font-medium">{t(`settingsPage.helpItems.${k}.q`)}</summary>
          <p className="mt-1 text-muted-foreground">{t(`settingsPage.helpItems.${k}.a`)}</p>
        </details>
      ))}
    </section>
  );
}
