import { AlertTriangle, FlaskConical, Lightbulb, Scale } from 'lucide-react';
import { Fragment, useId, useRef, type KeyboardEvent, type ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { ASSISTANT_MODES, type AssistantMode, type StructuredReply as Structured } from '@/api/assistant';
import { Badge } from '@/components/ui/badge';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

import { MethodSummary } from './ResearchProgress';

/** The DOM id of one evidence item of one message, the target of its inline citations. */
export function evidenceAnchor(messageId: number, evidenceId: string): string {
  return `ev-${messageId}-${evidenceId}`;
}

function focusEvidence(messageId: number, evidenceId: string): void {
  const target = document.getElementById(evidenceAnchor(messageId, evidenceId));
  if (!target) return;
  target.scrollIntoView({ block: 'nearest', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  target.focus({ preventScroll: true });
}

/** A citation chip: moves focus to the cited evidence below the reply. */
export function CitationChip({ messageId, id, known }: { messageId: number; id: string; known: boolean }) {
  const { t } = useTranslation();
  if (!known) return <span className="font-mono text-xs text-muted-foreground">[{id}]</span>;
  return (
    <a href={`#${evidenceAnchor(messageId, id)}`} data-testid="citation-chip" data-evidence={id}
      onClick={(e) => { e.preventDefault(); focusEvidence(messageId, id); }}
      aria-label={t('assistant.citation', { id })}
      className="mx-0.5 inline-flex items-center rounded-sm border border-primary/40 bg-primary/5 px-1 font-mono text-[0.7rem] leading-4 text-primary no-underline hover:bg-primary/15 focus-visible:outline-2">
      {id}
    </a>
  );
}

/** Reply text with each "[E3]" marker shown as a chip next to the claim it supports. */
export function CitedText({ text, messageId, known }: { text: string; messageId: number; known: Set<string> }) {
  const parts = text.split(/\[(E\d+)\]/);
  return (
    <>
      {parts.map((part, i) => (i % 2 === 1
        ? <CitationChip key={i} messageId={messageId} id={part} known={known.has(part)} />
        : <Fragment key={i}>{part}</Fragment>))}
    </>
  );
}

function Chips({ ids, messageId, known }: { ids: string[]; messageId: number; known: Set<string> }) {
  if (!ids.length) return null;
  return <span className="ms-1 inline-flex flex-wrap gap-0.5">{ids.map((id) => <CitationChip key={id} messageId={messageId} id={id} known={known.has(id)} />)}</span>;
}

function Section({ title, icon, children, testId }: { title: string; icon?: ReactNode; children: ReactNode; testId: string }) {
  return (
    <section className="rounded-md border border-border p-2 text-xs" data-testid={testId}>
      <h4 className="mb-1.5 flex items-center gap-1 font-semibold">{icon}{title}</h4>
      {children}
    </section>
  );
}

const BASIS_VARIANT = { evidence: 'verified', hypothesis: 'sand', assumption: 'muted' } as const;
const CARD_FIELDS = ['finding', 'evidence', 'action', 'expected_benefit', 'prerequisites', 'uncertainty'] as const;

/** Validated structured parts of a reply. The server has already dropped every part whose
 * numbers or citations the evidence does not support; here they are only displayed. */
export function StructuredParts({ structured, messageId, known }: { structured: Structured; messageId: number; known: Set<string> }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const { recommendations, drivers, evidence_points: points, hypotheses, assumptions, conflicts, withheld, studies } = structured;
  const withheldCount = withheld ? Object.values(withheld).reduce((a, b) => a + b, 0) : 0;
  return (
    <div className="flex flex-col gap-2">
      {studies?.length ? (
        <Section title={t('studies.fromAssistant')} icon={<FlaskConical aria-hidden="true" className="size-3.5" />} testId="reply-studies">
          <ul className="flex flex-col gap-1">
            {studies.map((s) => (
              <li key={s.id}>
                <Link to={to(`/studies/${s.id}`)} className="text-primary underline underline-offset-2" data-testid="reply-study-link">
                  {s.title[language]}
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {conflicts?.length ? (
        <Section title={t('assistant.conflicts')} icon={<Scale aria-hidden="true" className="size-3.5" />} testId="reply-conflicts">
          <ul className="flex flex-col gap-1.5">
            {conflicts.map((c, i) => (
              <li key={i}>
                <p className="font-medium" dir="auto">{c.topic}</p>
                <ul className="mt-0.5 flex flex-wrap gap-x-3 gap-y-1">
                  {c.values.map((v) => (
                    <li key={v.evidence_id} className="tabular-nums"><bdi>{v.value_text}</bdi><Chips ids={[v.evidence_id]} messageId={messageId} known={known} /></li>
                  ))}
                </ul>
                {c.note ? <p className="mt-0.5 text-muted-foreground" dir="auto">{c.note}</p> : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {recommendations?.length ? (
        <Section title={t('assistant.recommendations')} icon={<Lightbulb aria-hidden="true" className="size-3.5" />} testId="recommendation-cards">
          <p className="mb-2 text-muted-foreground">{t('assistant.recommendationNote')}</p>
          <ol className="flex flex-col gap-2">
            {recommendations.map((card, i) => (
              <li key={i} className="rounded-md border border-border bg-background p-2" data-testid="recommendation-card">
                <dl className="grid gap-x-3 gap-y-1 sm:grid-cols-[minmax(7rem,auto)_1fr]">
                  {CARD_FIELDS.map((f) => (
                    <Fragment key={f}>
                      <dt className="font-semibold text-muted-foreground">{t(`assistant.card.${f}`)}</dt>
                      <dd dir="auto"><CitedText text={card[f]} messageId={messageId} known={known} /></dd>
                    </Fragment>
                  ))}
                  <dt className="font-semibold text-muted-foreground">{t('assistant.card.sources')}</dt>
                  <dd><Chips ids={card.citations} messageId={messageId} known={known} /></dd>
                </dl>
              </li>
            ))}
          </ol>
        </Section>
      ) : null}
      {drivers?.length ? (
        <Section title={t('assistant.drivers')} testId="reply-drivers">
          <ul className="flex flex-col gap-1.5">
            {drivers.map((d, i) => (
              <li key={i} data-basis={d.basis}>
                <span className="font-medium">{t(`assistant.driver.${d.driver}`)}</span>{' '}
                <Badge variant={BASIS_VARIANT[d.basis]}>{t(`assistant.basis.${d.basis}`)}</Badge>
                <span className="block" dir="auto"><CitedText text={d.relation} messageId={messageId} known={known} /><Chips ids={d.citations} messageId={messageId} known={known} /></span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {([
        ['evidence_points', points, 'assistant.evidencePoints'],
        ['hypotheses', hypotheses, 'assistant.hypotheses'],
        ['assumptions', assumptions, 'assistant.assumptions'],
      ] as const).map(([key, items, title]) => (items?.length ? (
        <Section key={key} title={t(title)} testId={`reply-${key}`}>
          <ul className="list-disc ps-4">
            {items.map((item, i) => (
              <li key={i} dir="auto"><CitedText text={item.statement} messageId={messageId} known={known} /><Chips ids={item.citations} messageId={messageId} known={known} /></li>
            ))}
          </ul>
        </Section>
      ) : null))}
      {withheldCount > 0 ? (
        <p className="flex items-start gap-1 text-xs text-muted-foreground" data-testid="reply-withheld">
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-3 shrink-0" />{t('assistant.withheld', { count: withheldCount })}
        </p>
      ) : null}
      {structured.method ? <MethodSummary method={structured.method} /> : null}
    </div>
  );
}

/** The five answer modes as a wrapping radio group (arrow keys move the choice). */
export function ModeSelector({ value, onChange }: { value: AssistantMode; onChange: (mode: AssistantMode) => void }) {
  const { t } = useTranslation();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const hintId = useId();
  const index = ASSISTANT_MODES.indexOf(value);
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const rtl = getComputedStyle(event.currentTarget).direction === 'rtl';
    let next = index;
    if (event.key === (rtl ? 'ArrowLeft' : 'ArrowRight') || event.key === 'ArrowDown') next = (index + 1) % ASSISTANT_MODES.length;
    else if (event.key === (rtl ? 'ArrowRight' : 'ArrowLeft') || event.key === 'ArrowUp') next = (index - 1 + ASSISTANT_MODES.length) % ASSISTANT_MODES.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = ASSISTANT_MODES.length - 1;
    else return;
    event.preventDefault();
    const mode = ASSISTANT_MODES[next];
    if (mode) onChange(mode);
    refs.current[next]?.focus();
  };
  return (
    <div className="flex flex-col gap-1">
      <div role="radiogroup" aria-label={t('assistant.mode.label')} aria-describedby={hintId} data-testid="assistant-mode"
        className="flex flex-wrap gap-1">
        {ASSISTANT_MODES.map((mode, i) => (
          <button key={mode} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={mode === value}
            tabIndex={mode === value ? 0 : -1} data-value={mode} onClick={() => onChange(mode)} onKeyDown={onKeyDown}
            className={cn('min-h-9 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
              mode === value ? 'border-primary bg-primary text-primary-foreground' : 'border-border-strong/60 bg-card hover:bg-muted')}>
            {t(`assistant.mode.${mode}`)}
          </button>
        ))}
      </div>
      <p id={hintId} className="text-xs text-muted-foreground" data-testid="assistant-mode-hint">{t(`assistant.modeHint.${value}`)}</p>
    </div>
  );
}
