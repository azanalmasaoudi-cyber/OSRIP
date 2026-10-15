import { TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useReferencePack } from '@/api/referencePack';
import type { SectionCode } from '@/domain/types';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * The reference pack's documented conflicts, revisions and limitations for one
 * section (Q01…). They are shown beside the data, never resolved silently: a
 * superseded figure stays documented here even though it is not imported.
 */
export function DataQualityNotes({ section }: { section: SectionCode }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const query = useReferencePack();
  const pack = query.data?.pack;
  const notes = (query.data?.notes ?? []).filter((n) => n.sections.includes(section));
  if (!pack || notes.length === 0) return null;
  return (
    <section aria-labelledby={`quality-notes-${section}`} className="rounded-lg border border-sand/60 bg-sand-subtle/40 p-5" data-testid="data-quality-notes">
      <h3 id={`quality-notes-${section}`} className="flex items-center gap-2 font-semibold">
        <TriangleAlert aria-hidden="true" className="size-4 text-sand-foreground" />
        {t('dataQuality.heading')}
      </h3>
      <p className="mt-1 max-w-3xl text-xs text-muted-foreground">
        {t('dataQuality.intro', { cutoff: pack.research_cutoff })}
      </p>
      <ul className="mt-3 flex flex-col gap-2">
        {notes.map((n) => (
          <li key={n.code}>
            <details className="group rounded-md bg-card/70 px-3 py-2 text-sm" data-testid="data-quality-note" data-code={n.code}>
              <summary className="cursor-pointer font-medium marker:text-muted-foreground">
                <span className="me-2 font-mono text-xs text-muted-foreground" dir="ltr">{n.code}</span>
                {n.title[language]}
              </summary>
              <p className="mt-2 max-w-prose text-muted-foreground">{n.body[language]}</p>
              {n.source_codes.length ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {t('dataQuality.references')}: <span dir="ltr">{n.source_codes.join(', ')}</span>
                </p>
              ) : null}
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}
