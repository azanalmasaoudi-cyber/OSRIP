import { ClipboardCheck, Play } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { InputsTable, Limitations, ResultValue } from './CalculationCard';
import { useAddReview, useReviewCards, useReviews, useRunRules, type ReviewCard } from '@/api/analysis';
import { hasPermission, useMe } from '@/api/auth';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { SelectField } from '@/components/ui/select';
import type { DataMode, SectionCode } from '@/domain/types';
import { useAppLanguage } from '@/lib/useAppLanguage';

const STATUS_VARIANT = { open: 'accent', under_review: 'sand', explained: 'verified', dismissed: 'muted' } as const;

function ReviewHistory({ card }: { card: ReviewCard }) {
  const { t } = useTranslation();
  const me = useMe();
  const canRead = hasPermission(me.data, 'recommendation.review') || hasPermission(me.data, 'analysis.run');
  const canWrite = hasPermission(me.data, 'recommendation.review');
  const history = useReviews(card.id, canRead);
  const add = useAddReview(card.id);
  const [status, setStatus] = useState('under_review');
  const [reason, setReason] = useState('');
  const reasonId = useId();

  if (!canRead) return <p className="text-xs text-muted-foreground">{t('cards.protected')}</p>;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.mutate({ status, reason }, { onSuccess: () => setReason('') });
  };

  return (
    <div className="flex flex-col gap-3 border-t border-border pt-3">
      <p className="text-xs font-semibold">{t('cards.history')}</p>
      {history.data && history.data.length === 0 ? <p className="text-xs text-muted-foreground">{t('cards.noHistory')}</p> : null}
      {history.data && history.data.length > 0 ? (
        <ol className="flex flex-col gap-1.5 text-xs" data-testid="review-history">
          {history.data.map((r) => (
            <li key={r.id} className="rounded-md border border-border p-2">
              <span className="font-medium">{t(`cards.status.${r.status as ReviewCard['status']}`)}</span>
              {' · '}{r.reviewer}{' · '}<span dir="ltr">{r.created_at.slice(0, 16).replace('T', ' ')}</span>
              <p className="mt-0.5">{r.reason}</p>
            </li>
          ))}
        </ol>
      ) : null}
      {canWrite ? (
        <form onSubmit={submit} className="flex flex-col gap-2" data-testid="review-form">
          <SelectField label={t('cards.newStatus')} value={status} onValueChange={setStatus}
            options={(['under_review', 'explained', 'dismissed'] as const).map((s) => ({ value: s, label: t(`cards.status.${s}`) }))} />
          <div className="flex flex-col gap-1.5">
            <label htmlFor={reasonId} className="text-xs font-medium text-muted-foreground">{t('cards.reason')}</label>
            <input id={reasonId} value={reason} onChange={(e) => setReason(e.target.value)} required
              className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm" />
          </div>
          <Button type="submit" size="sm" className="w-fit" disabled={!reason.trim() || add.isPending}>{t('cards.submit')}</Button>
          {add.isError ? <p role="alert" className="text-xs text-destructive">{add.error.message}</p> : null}
        </form>
      ) : null}
    </div>
  );
}

export function ReviewCardView({ card, withReviews = true }: { card: ReviewCard; withReviews?: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const l = (x: { en: string; ar: string }) => (language === 'ar' ? x.ar : x.en);
  const { rule, result } = card.evidence;
  const unitLabel = result.unit ? (language === 'ar' ? result.unit.label_ar : result.unit.label_en) : '';

  return (
    <Card className="flex flex-col gap-3 p-5" data-testid="review-card" data-rule={card.rule_code}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="flex items-center gap-2 font-semibold">
          <ClipboardCheck aria-hidden="true" className="size-4 text-accent" />
          <span dir="ltr">{rule.code}</span> · {l(rule.name)}
        </p>
        <Badge variant={STATUS_VARIANT[card.status]} data-testid="card-status">{t(`cards.status.${card.status}`)}</Badge>
      </div>
      <div>
        <p className="text-xs font-semibold text-muted-foreground">{t('cards.observation')}</p>
        <p data-testid="card-observation">{l(card.observation)}</p>
      </div>
      <div className="rounded-md border-s-4 border-s-accent bg-muted/40 p-3">
        <p className="text-xs font-semibold text-muted-foreground">{t('cards.next')}</p>
        <p className="text-sm" data-testid="card-next">{l(card.next_steps)}</p>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer font-medium">{t('cards.details')}</summary>
        <div className="mt-3 flex flex-col gap-3">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            <dt className="text-muted-foreground">{t('cards.rule')}</dt>
            <dd>{t('cards.ruleVersion', { v: rule.version })}</dd>
            <dt className="text-muted-foreground">{t('cards.eligibility')}</dt>
            <dd>{l(rule.eligibility)}</dd>
            {rule.threshold ? (
              <>
                <dt className="text-muted-foreground">{t('cards.threshold')}</dt>
                <dd><span dir="ltr">{rule.threshold}</span>{rule.threshold_note ? ` — ${l(rule.threshold_note)}` : ''}</dd>
              </>
            ) : null}
          </dl>
          <p className="text-xs font-semibold">{l(card.evidence.calculation_title)}: <span className="font-normal">{l(card.evidence.formula)}</span></p>
          {result.status === 'ok' && result.value ? (
            <ResultValue value={result.value} unitCode={result.unit?.code} unitLabel={unitLabel} />
          ) : null}
          <InputsTable inputs={card.evidence.inputs} />
          <Limitations items={card.evidence.limitations} />
        </div>
      </details>
      {withReviews ? <ReviewHistory card={card} /> : null}
    </Card>
  );
}

/** Latest rule run's cards for a data mode (optionally one section). */
export function ReviewCards({ mode, section, headingLevel = 2, compact = false }: {
  mode: DataMode; section?: SectionCode; headingLevel?: 2 | 3 | 4;
  /** Inside a panel that already has its own heading (the workspace's study panel). */
  compact?: boolean;
}) {
  const Heading = `h${headingLevel}` as const;
  const { t } = useTranslation();
  const me = useMe();
  const cards = useReviewCards(mode, section);
  const run = useRunRules();
  const canRun = hasPermission(me.data, 'analysis.run');

  let body;
  if (cards.isPending) body = <StatePanel kind="loading" skeleton="lines" />;
  else if (cards.isError) body = <StatePanel kind="error" detail={cards.error.message} onRetry={() => void cards.refetch()} />;
  else if (!cards.data.run) body = <p className="text-sm text-muted-foreground" data-testid="no-rule-run">{t('cards.noRun')}</p>;
  else if (cards.data.cards.length === 0) body = <p className="text-sm text-muted-foreground">{t('cards.none')}</p>;
  else body = <div className="grid gap-4 xl:grid-cols-2">{cards.data.cards.map((c) => <ReviewCardView key={c.id} card={c} />)}</div>;

  return (
    <section aria-labelledby={`cards-${section ?? 'all'}`} className="flex flex-col gap-4" data-testid="review-cards">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Heading id={`cards-${section ?? 'all'}`} className={compact ? 'sr-only' : 'text-xl font-semibold'}>{t('cards.heading')}</Heading>
          <p className={compact ? 'max-w-3xl text-xs text-muted-foreground' : 'max-w-3xl text-sm text-muted-foreground'}>{t('cards.intro')}</p>
        </div>
        {canRun ? (
          <Button variant="outline" size="sm" onClick={() => run.mutate(mode)} disabled={run.isPending} data-testid="run-rules">
            <Play aria-hidden="true" className="rtl:-scale-x-100" />
            {run.isPending ? t('cards.running') : t('cards.run')}
          </Button>
        ) : null}
      </div>
      {run.isError ? <p role="alert" className="text-sm text-destructive">{run.error.message}</p> : null}
      {body}
    </section>
  );
}
