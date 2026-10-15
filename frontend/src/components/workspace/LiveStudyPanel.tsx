import { ChevronLeft, ChevronRight, Pause, Play, Square } from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { useCancelRequest, useVoiceStatus } from '@/api/assistant';
import { useAssistantUi } from '@/components/assistant/AssistantContext';
import { usePersona } from '@/components/assistant/persona';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SelectField } from '@/components/ui/select';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { useLiveStudy, type LiveStudyState } from '@/state/liveStudy';

import { DatasetView, type DatasetState } from './DatasetView';
import { EvidenceList, ProgressStages, StudyNotices } from './StudyParts';
import { useNarration } from './useNarration';

const STATUS_VARIANT = { running: 'sand', connecting: 'muted', completed: 'verified', cancelled: 'muted', failed: 'accent', none: 'muted', idle: 'muted' } as const;

function datasetState(study: LiveStudyState, id: string): DatasetState {
  if (study.status === 'completed') return study.completion?.final_datasets.includes(id) ? 'final' : 'unused';
  if (study.status === 'cancelled' || study.status === 'failed') return 'stopped';
  return 'provisional';
}

/**
 * The assistant's study as it happens: the steps really reached, sources as they arrive,
 * tables (and the charts drawn from them) once validated, and, when the study completes, the
 * validated findings with the narration generated from them. While the study runs everything
 * is labelled provisional; after a stop or a failure nothing becomes final. The person can
 * stop the research, stop or step through the narration, inspect any source and return to an
 * earlier study of this session.
 */
export function LiveStudyPanel({ onAskFollowUp }: { onAskFollowUp?: () => void }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const ui = useAssistantUi();
  const active = ui.activeStudy;
  const study = useLiveStudy(active?.id ?? null, active?.guest ?? false, active?.epoch ?? 0);
  const cancel = useCancelRequest();
  const voiceStatus = useVoiceStatus();
  const { persona } = usePersona();
  const completion = study.completion;
  const segments = useMemo(() => completion?.narration ?? [], [completion]);
  const narration = useNarration({
    segments,
    messageId: completion?.message_id ?? null,
    language: completion?.language ?? study.language ?? language,
    gender: persona.gender,
    serverSpeech: Boolean(voiceStatus.data?.configured),
  });
  // What the sentence being read is about: rows of a table, a whole table, or (no target)
  // only the finding itself (section-level highlighting).
  const current = narration.current;
  const rowHighlights = new Map<string, Set<string>>();
  const wholeTables = new Set<string>();
  for (const target of current?.targets ?? []) {
    if (target.row_ids.length) rowHighlights.set(target.dataset_id, new Set(target.row_ids));
    else wholeTables.add(target.dataset_id);
  }
  const cited = new Set(current?.evidence_ids ?? []);

  if (!active) {
    return (
      <div className="flex flex-col gap-3" data-testid="live-study" data-status="idle">
        <StatePanel kind="empty"><p className="text-sm text-muted-foreground">{t('workspace.study.noneYet')}</p></StatePanel>
        {onAskFollowUp ? <Button variant="outline" size="sm" className="w-fit" onClick={onAskFollowUp}>{t('workspace.study.askFirst')}</Button> : null}
      </div>
    );
  }

  const running = study.status === 'running' || study.status === 'connecting';
  const findingSegment = new Map(segments.flatMap((s, i) => (s.finding_id ? [[s.finding_id, { s, i }] as const] : [])));

  return (
    <section className="flex flex-col gap-5" data-testid="live-study" data-status={study.status} data-study={active.id}
      aria-labelledby="live-study-heading" aria-busy={running}>
      <header className="flex flex-col gap-2">
        <p className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant={STATUS_VARIANT[study.status]} data-testid="study-status">{t(`workspace.study.status.${study.status}`)}</Badge>
          {study.dataMode ? <Badge variant={study.dataMode === 'synthetic' ? 'synthetic' : 'verified'}>{t(`dataMode.${study.dataMode === 'synthetic' ? 'synthetic' : 'verified_source'}`)}</Badge> : null}
          {study.mode && study.mode !== 'ask' ? <Badge variant="outline">{t(`assistant.mode.${study.mode as 'research'}`)}</Badge> : null}
          <span className="font-mono text-muted-foreground" dir="ltr" title={t('workspace.study.idLabel')}>v{study.version}</span>
        </p>
        <h3 id="live-study-heading" tabIndex={-1} className="text-lg font-semibold outline-none" dir="auto">
          {active.question || t('workspace.study.untitled')}
        </h3>
        {running ? <p className="rounded-md border border-sand/60 bg-sand-subtle/60 p-2 text-sm" role="status" data-testid="study-provisional">{t('workspace.study.provisional')}</p> : null}
        {study.status === 'cancelled' ? <p className="text-sm" role="status" data-testid="study-stopped">{t('workspace.study.stoppedNote')}</p> : null}
        {study.status === 'failed' ? <p className="text-sm text-destructive" role="alert">{t('workspace.study.failedNote')}</p> : null}
        {study.status === 'none' ? <p className="text-sm text-muted-foreground" role="status">{t('workspace.study.noStudy')}</p> : null}
        {study.failure === 'stream' && running ? <p className="text-sm text-muted-foreground" role="status">{t('workspace.study.reconnecting')}</p> : null}
        <div className="flex flex-wrap items-end gap-2">
          {running ? (
            <Button type="button" variant="outline" size="sm" data-testid="study-stop" disabled={cancel.isPending}
              onClick={() => cancel.mutate({ requestId: active.id, guest: active.guest })}>
              <Square aria-hidden="true" />{t('workspace.study.stop')}
            </Button>
          ) : null}
          {onAskFollowUp ? <Button type="button" variant="ghost" size="sm" onClick={onAskFollowUp} data-testid="study-follow-up">{t('workspace.study.followUp')}</Button> : null}
          {ui.studies.length > 1 ? (
            <SelectField className="w-full sm:w-72" label={t('workspace.study.history')} value={active.id}
              onValueChange={(id) => { const s = ui.studies.find((x) => x.id === id); if (s) ui.openStudy(s.id, s.guest, s.question); }}
              options={ui.studies.map((s) => ({ value: s.id, label: s.question || s.id.slice(0, 8) }))} data-testid="study-history" />
          ) : null}
        </div>
      </header>

      <div className="grid gap-5 xl:grid-cols-2">
        <div className="flex flex-col gap-3">
          <h4 className="text-sm font-semibold">{t('workspace.study.progress')}</h4>
          <ProgressStages study={study} />
          <StudyNotices study={study} />
        </div>
        <div className="flex flex-col gap-3" data-testid="study-findings-panel">
          <h4 className="text-sm font-semibold">{t('workspace.study.findings')}</h4>
          {completion && completion.findings.length ? (
            <>
              {/* Findings and narration stay in the language of the answer (the interface may differ). */}
              <ol className="flex flex-col gap-1.5" data-testid="study-findings" lang={completion.language}>
                {completion.findings.map((f) => {
                  const seg = findingSegment.get(f.finding_id);
                  const on = Boolean(seg && narration.index === seg.i);
                  return (
                    <li key={f.finding_id} data-testid="study-finding" data-finding={f.finding_id} data-segment={seg?.s.narration_segment_id}
                      data-highlighted={on ? 'true' : undefined}
                      className={cn('rounded-md border border-transparent p-2 text-sm transition-colors motion-reduce:transition-none', on && 'border-copper bg-copper-subtle/60')}>
                      <button type="button" className="w-full text-start focus-visible:outline-2 focus-visible:outline-ring" dir="auto"
                        onClick={() => seg && narration.select(seg.i)} aria-pressed={on}>
                        {f.text}
                      </button>
                    </li>
                  );
                })}
              </ol>
              <NarrationControls narration={narration} total={segments.length} />
            </>
          ) : completion ? (
            <p className="text-sm" dir="auto" data-testid="study-status-text">{segments[0]?.text}</p>
          ) : (
            <p className="text-sm text-muted-foreground" role="status">{running ? t('workspace.study.findingsPending') : t('workspace.study.noFindings')}</p>
          )}
        </div>
      </div>

      {study.datasets.length ? (
        <div className="flex flex-col gap-4" data-testid="study-datasets">
          <h4 className="text-sm font-semibold">{t('workspace.study.tables')}</h4>
          {study.datasets.map((d) => (
            <DatasetView key={d.dataset_id} dataset={d} state={datasetState(study, d.dataset_id)} headingLevel={4}
              highlight={rowHighlights.get(d.dataset_id)} whole={wholeTables.has(d.dataset_id)} />
          ))}
        </div>
      ) : running ? <p className="text-sm text-muted-foreground">{t('workspace.study.tablesPending')}</p> : null}

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-semibold">{t('workspace.study.sources', { count: study.evidence.length })}</h4>
        <EvidenceList evidence={study.evidence} cited={cited} />
      </div>

      {completion ? (
        <div className="grid gap-4 text-sm md:grid-cols-2">
          {completion.recommendations.length ? (
            <div data-testid="study-recommendations">
              <h4 className="font-semibold">{t('workspace.study.recommendations')}</h4>
              <ul className="mt-1 flex flex-col gap-2">
                {completion.recommendations.map((r, i) => (
                  <li key={i} className="rounded-md border border-border p-2">
                    <p className="font-medium" dir="auto">{r.action}</p>
                    <p className="text-muted-foreground" dir="auto">{r.finding}</p>
                    <p className="text-xs text-muted-foreground" dir="auto">{t('assistant.card.uncertainty')}: {r.uncertainty}</p>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {completion.assumptions.length ? (
            <div><h4 className="font-semibold">{t('workspace.study.assumptions')}</h4>
              <ul className="mt-1 list-disc ps-5 text-muted-foreground">{completion.assumptions.map((a, i) => <li key={i} dir="auto">{a}</li>)}</ul></div>
          ) : null}
          <MethodLines method={completion.method} />
          <div data-testid="study-references">
            <h4 className="font-semibold">{t('workspace.study.references')}</h4>
            <ul className="mt-1 list-disc ps-5 text-muted-foreground">
              {study.evidence.filter((e) => completion.findings.some((f) => f.evidence_ids.includes(e.evidence_id))).map((e) => (
                <li key={e.evidence_id}><span className="font-mono" dir="ltr">{e.evidence_id}</span> {e.source?.title ?? e.title[language]}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function NarrationControls({ narration, total }: { narration: ReturnType<typeof useNarration>; total: number }) {
  const { t } = useTranslation();
  const i = narration.index;
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-muted/30 p-2" data-testid="narration" data-mode={narration.mode}
      data-playing={narration.playing ? 'true' : 'false'} data-segment={narration.current?.narration_segment_id ?? ''}>
      <div className="flex flex-wrap items-center gap-2">
        {narration.mode !== 'manual' ? (
          narration.playing ? (
            <Button type="button" size="sm" onClick={narration.stop} data-testid="narration-stop"><Pause aria-hidden="true" />{t('workspace.narration.stop')}</Button>
          ) : (
            <Button type="button" size="sm" onClick={narration.play} data-testid="narration-play"><Play aria-hidden="true" />{t('workspace.narration.play')}</Button>
          )
        ) : null}
        <span className="inline-flex items-center gap-1">
          <Button type="button" variant="ghost" size="sm" disabled={i === null || i <= 0} onClick={() => narration.select((i ?? 1) - 1)}
            data-testid="narration-previous" aria-label={t('workspace.narration.previous')}><ChevronLeft aria-hidden="true" className="rtl:-scale-x-100" /></Button>
          <span className="whitespace-nowrap text-xs tabular-nums" role="status" data-testid="narration-position">
            {t('workspace.narration.position', { n: i === null ? 0 : i + 1, total })}
          </span>
          <Button type="button" variant="ghost" size="sm" disabled={i !== null && i >= total - 1} onClick={() => narration.select(i === null ? 0 : i + 1)}
            data-testid="narration-next" aria-label={t('workspace.narration.next')}><ChevronRight aria-hidden="true" className="rtl:-scale-x-100" /></Button>
        </span>
      </div>
      <p className="text-xs text-muted-foreground">{t(`workspace.narration.mode.${narration.mode}`)}</p>
      {narration.failed ? <p className="text-xs text-destructive" role="alert">{t('workspace.narration.failed')}</p> : null}
    </div>
  );
}

function MethodLines({ method }: { method: Record<string, unknown> }) {
  const { t } = useTranslation();
  const num = (k: string) => {
    const v = method[k];
    return typeof v === 'number' ? v : 0;
  };
  const code = typeof method.answer_provider === 'string' ? method.answer_provider : null;
  const known = ['anthropic', 'openai', 'gemini', 'fake'] as const;
  const provider = code === null ? null
    : (known as readonly string[]).includes(code) ? t(`workflow.method.provider.${code as (typeof known)[number]}`) : code;
  return (
    <div data-testid="study-method">
      <h4 className="font-semibold">{t('workspace.study.method')}</h4>
      <ul className="mt-1 list-disc ps-5 text-muted-foreground">
        {provider ? <li>{t('workspace.method.provider', { provider })}</li> : null}
        <li>{t('workspace.method.records', { count: num('published_records') })}</li>
        <li>{t('workspace.method.calculations', { count: num('calculations') + num('studies') })}</li>
        <li>{t('workspace.method.searches', { count: num('searches'), failed: num('failed_searches') })}</li>
        <li>{t('workspace.method.validated')}</li>
      </ul>
    </div>
  );
}
