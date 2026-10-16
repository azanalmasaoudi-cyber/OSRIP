import { ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { adapterKind } from '@/api/config';
import { useStudyPreview } from '@/api/studies';
import { ReviewCards } from '@/components/analysis/ReviewCards';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import type { DataMode, SectionCode } from '@/domain/types';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * The deterministic study of the current selection (the trend of the chosen indicator and
 * area), computed by the server from published observations and not stored: findings,
 * method, assumptions, limitations and references, with the rule-based recommendations of the
 * section, which need a person's review before anyone acts on them.
 */
export function SelectionStudy({ indicator, area, periodKind, mode, section }: {
  indicator: string | null;
  area: string;
  periodKind: string;
  mode: DataMode;
  section: SectionCode | null;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const kind = ['annual', 'year_to_date', 'quarterly', 'monthly'].includes(periodKind) ? periodKind : 'annual';
  const preview = useStudyPreview('trend', indicator ? { indicator, area, period_kind: kind } : null, mode);
  if (adapterKind !== 'http') return <StatePanel kind="not_implemented" />;
  if (!indicator) return <StatePanel kind="empty"><p className="text-sm text-muted-foreground">{t('workspace.selection.choose')}</p></StatePanel>;
  if (preview.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (preview.isError) return <StatePanel kind="error" detail={preview.error.message} onRetry={() => void preview.refetch()} />;
  const study = preview.data.study;
  return (
    <article className="@container flex flex-col gap-5" data-testid="selection-study" data-status={study.status}>
      <header className="flex flex-col gap-1">
        <p className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant="outline">{t(`studies.kinds.${study.kind}`)}</Badge>
          <Badge variant={study.status === 'ok' ? 'verified' : 'sand'}>{t(`studies.statusLabel.${study.status}`)}</Badge>
          <span className="text-muted-foreground">{t('workspace.selection.computed')}</span>
        </p>
        <h3 className="text-lg font-semibold">{study.title[language]}</h3>
        <p className="text-sm text-muted-foreground">{study.question[language]}</p>
      </header>
      {study.reason ? <p className="rounded-md border border-sand/60 bg-sand-subtle/60 p-3 text-sm" role="status">{study.reason[language]}</p> : null}
      <section className="flex flex-col gap-1" data-testid="selection-findings">
        <h4 className="font-semibold">{t('workspace.study.findings')}</h4>
        {study.findings.length ? (
          <ul className="list-disc ps-5 text-sm">{study.findings.map((f, i) => (
            <li key={i}>{f.text[language]}{f.evidence.length ? <span className="ms-1 font-mono text-xs text-muted-foreground" dir="ltr">[{f.evidence.join(', ')}]</span> : null}</li>
          ))}</ul>
        ) : <p className="text-sm text-muted-foreground">{t('workspace.study.noFindings')}</p>}
      </section>
      <section className="grid gap-4 text-sm @lg:grid-cols-2">
        <div data-testid="selection-method">
          <h4 className="font-semibold">{t('workspace.study.method')}</h4>
          <p className="mt-1 text-muted-foreground">{study.method[language]}</p>
        </div>
        <div>
          <h4 className="font-semibold">{t('workspace.study.assumptions')}</h4>
          {study.assumptions.length ? <ul className="mt-1 list-disc ps-5 text-muted-foreground">{study.assumptions.map((a, i) => <li key={i}>{a[language]}</li>)}</ul>
            : <p className="mt-1 text-muted-foreground">{t('workspace.selection.noAssumptions')}</p>}
        </div>
        {study.limitations.length ? (
          <div><h4 className="font-semibold">{t('studies.limitations')}</h4>
            <ul className="mt-1 list-disc ps-5 text-muted-foreground">{study.limitations.map((a, i) => <li key={i}>{a[language]}</li>)}</ul></div>
        ) : null}
        <div data-testid="selection-references">
          <h4 className="font-semibold">{t('workspace.study.references')}</h4>
          <ul className="mt-1 flex flex-col gap-1 text-muted-foreground">
            {study.evidence.slice(0, 12).map((e) => (
              <li key={e.id}>
                <span className="font-mono text-xs" dir="ltr">{e.id}</span>{' '}
                {e.source_url ? (
                  <a href={e.source_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-primary underline underline-offset-2">
                    <bdi>{e.source_title}</bdi><ExternalLink aria-hidden="true" className="size-3" />
                  </a>
                ) : <bdi>{e.source_title}</bdi>}
                <span className="text-xs" dir="ltr"> · {e.period_start} – {e.period_end} · {e.dataset_version}</span>
              </li>
            ))}
            {study.evidence.length > 12 ? <li className="text-xs">{t('workspace.selection.more', { count: study.evidence.length - 12 })}</li> : null}
          </ul>
        </div>
      </section>
      <section className="flex flex-col gap-2" data-testid="selection-recommendations">
        <h4 className="font-semibold">{t('workspace.study.recommendations')}</h4>
        <p className="text-xs text-muted-foreground">{t('workspace.selection.recommendationsNote')}</p>
        {section ? <ReviewCards mode={mode} section={section} headingLevel={4} compact /> : null}
      </section>
    </article>
  );
}
