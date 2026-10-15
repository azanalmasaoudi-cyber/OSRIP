import { Check, ExternalLink, FileSearch, Loader2, Search, TriangleAlert } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { StudyEvidence } from '@/api/studyEvents';
import { DataStatusBadge } from '@/components/common/DataStatusBadge';
import { Badge } from '@/components/ui/badge';
import { Dialog } from '@/components/ui/dialog';
import { formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import type { LiveStudyState } from '@/state/liveStudy';

/** The steps the study has actually reached, newest last (from the server, never a timer). */
export function ProgressStages({ study }: { study: LiveStudyState }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const running = study.status === 'running' || study.status === 'connecting';
  const stages = study.stages.filter((s, i, all) => all.findIndex((x) => x.stage === s.stage) === i || s.stage === 'validating_data');
  return (
    <ol className="flex flex-col gap-1 text-sm" data-testid="study-progress" aria-label={t('workspace.study.progress')}>
      {stages.map((s, i) => {
        const current = running && i === stages.length - 1;
        return (
          <li key={`${s.stage}-${i}`} className="flex items-center gap-2" data-stage={s.stage} aria-current={current ? 'step' : undefined}>
            {current ? <Loader2 aria-hidden="true" className="size-4 animate-spin text-primary motion-reduce:animate-none" />
              : <Check aria-hidden="true" className="size-4 text-verified-foreground" />}
            <span className={current ? 'font-medium' : 'text-muted-foreground'}>{s.label[language]}</span>
          </li>
        );
      })}
      {study.status === 'connecting' && !stages.length ? (
        <li className="flex items-center gap-2 text-muted-foreground"><Loader2 aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" />{t('workspace.study.connecting')}</li>
      ) : null}
    </ol>
  );
}

/** Partial failures and searches: shown, never hidden. */
export function StudyNotices({ study }: { study: LiveStudyState }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  if (!study.warnings.length && !study.searches.length) return null;
  return (
    <ul className="flex flex-col gap-1 text-sm" data-testid="study-notices">
      {study.searches.map((s) => (
        <li key={s.evidence_id} className={cn('flex items-start gap-2', s.status === 'ok' || s.status === 'no_results' ? 'text-muted-foreground' : 'text-destructive')}
          data-testid="study-search" data-status={s.status}>
          <Search aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span dir="auto">{t(s.status === 'ok' ? 'workspace.search.ok' : s.status === 'no_results' ? 'workspace.search.none' : 'workspace.search.failed', { query: s.query ?? '' })}
            {s.display_only ? ` ${t('workspace.search.shownApart')}` : ''}</span>
        </li>
      ))}
      {study.warnings.map((w) => (
        <li key={w.seq} className="flex items-start gap-2 text-destructive" role="status" data-testid="study-warning" data-code={w.code}>
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>{w.code === 'dataset_rejected_client' ? t('workspace.study.rejectedHere') : w.detail[language]}</span>
        </li>
      ))}
    </ul>
  );
}

function evidenceLine(e: StudyEvidence, language: 'en' | 'ar'): string {
  const parts = [
    e.area?.[language],
    e.period_start && e.period_end ? formatPeriod(e.period_start, e.period_end, language) : null,
    e.value != null ? `${e.value_operator ?? ''}${formatDecimal(e.value, language, 4) ?? e.value}${e.unit ? ` ${e.unit[language]}` : ''}` : null,
  ];
  return parts.filter(Boolean).join(' · ');
}

/**
 * Sources as they are retrieved (each appears when its event arrives). Each opens a detail
 * dialog; closing it returns focus to the source that was opened.
 */
export function EvidenceList({ evidence, cited }: { evidence: readonly StudyEvidence[]; cited: ReadonlySet<string> }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [open, setOpen] = useState<StudyEvidence | null>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  if (!evidence.length) return <p className="text-sm text-muted-foreground" role="status">{t('workspace.evidence.none')}</p>;
  return (
    <>
      <ul className="flex flex-col gap-1.5" data-testid="study-evidence" aria-live="polite">
        <AnimatePresence initial={false}>
          {evidence.map((e) => {
            const on = cited.has(e.evidence_id);
            return (
              <motion.li key={e.evidence_id} layout="position" initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2 }} data-testid="study-source" data-evidence={e.evidence_id} data-highlighted={on ? 'true' : undefined}
                className={cn('rounded-md border border-border bg-background text-sm', on && 'border-copper bg-copper-subtle/50')}>
                <button type="button" className="flex w-full flex-col items-start gap-0.5 p-2 text-start hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring"
                  onClick={(ev) => { opener.current = ev.currentTarget; setOpen(e); }}
                  aria-label={t('workspace.evidence.inspect', { id: e.evidence_id, title: e.title[language] })}>
                  <span className="flex flex-wrap items-center gap-1.5 text-xs">
                    <span className="font-mono" dir="ltr">{e.evidence_id}</span>
                    <DataStatusBadge status={e.data_status} showReference />
                    <span className="text-muted-foreground">{t(`workspace.evidence.kind.${e.kind}`)}</span>
                  </span>
                  <span className="font-medium" dir="auto">{e.title[language]}</span>
                  {evidenceLine(e, language) ? <span className="text-xs text-muted-foreground" dir="auto">{evidenceLine(e, language)}</span> : null}
                </button>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ul>
      <Dialog open={open !== null} onClose={() => { setOpen(null); requestAnimationFrame(() => opener.current?.focus()); }}
        title={open ? `${open.evidence_id} · ${open.title[language]}` : ''} description={t('workspace.evidence.dialogNote')}>
        {open ? <SourceDetails e={open} /> : null}
      </Dialog>
    </>
  );
}

function SourceDetails({ e }: { e: StudyEvidence }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const rows: [string, string | null | undefined][] = [
    [t('workspace.evidence.status'), t(`assistant.dataStatus.${e.data_status}`)],
    [t('workspace.evidence.area'), e.area?.[language]],
    [t('workspace.evidence.period'), e.period_start && e.period_end ? formatPeriod(e.period_start, e.period_end, language) : null],
    [t('workspace.evidence.value'), e.value != null ? `${e.value_operator ?? ''}${formatDecimal(e.value, language, 6) ?? e.value}${e.unit ? ` ${e.unit[language]}` : ''}` : null],
    [t('workspace.evidence.publisher'), e.source?.publisher],
    [t('workspace.evidence.dataset'), e.source?.dataset_version],
    [t('workspace.evidence.record'), e.source?.record_ref],
    [t('workspace.evidence.published'), e.published],
    [t('workspace.evidence.retrieved'), e.retrieved_at?.slice(0, 10)],
    [t('workspace.evidence.summaryBy'), e.summary_by],
  ];
  return (
    <div className="flex flex-col gap-3 text-sm" data-testid="study-source-details">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        {rows.filter(([, v]) => v).map(([k, v]) => (
          <div key={k} className="contents"><dt className="text-muted-foreground">{k}</dt><dd dir="auto">{v}</dd></div>
        ))}
      </dl>
      {e.source?.url ? (
        <a href={e.source.url} target="_blank" rel="noreferrer noopener" className="inline-flex w-fit items-center gap-1 text-primary underline underline-offset-2">
          <FileSearch aria-hidden="true" className="size-4" /><bdi>{e.source.title ?? e.source.url}</bdi><ExternalLink aria-hidden="true" className="size-3" />
        </a>
      ) : e.source?.title ? <p><bdi>{e.source.title}</bdi></p> : null}
      {e.excerpt ? (
        <div>
          <p className="text-xs font-medium">{e.kind === 'web' ? t('workspace.evidence.untrusted') : t('workspace.evidence.excerpt')}</p>
          <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-muted/50 p-2 text-xs" dir="auto">{e.excerpt}</p>
        </div>
      ) : null}
      {e.inputs.length ? <p className="text-xs text-muted-foreground">{t('workspace.evidence.inputs', { ids: e.inputs.join(', ') })}</p> : null}
      {e.content_kind === 'provider_summary' ? <Badge variant="sand" className="w-fit">{t('web.summaryText')}</Badge> : null}
    </div>
  );
}
