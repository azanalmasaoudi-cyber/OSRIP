import { useTranslation } from 'react-i18next';

import { useReferencePack } from '@/api/referencePack';
import { formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * Every reference in the loaded pack, including crosschecks that supply no imported
 * value, with the number of its records published in verified-source mode.
 */
export function ReferencePackSources() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const query = useReferencePack();
  const pack = query.data?.pack;
  const sources = query.data?.sources ?? [];
  if (!pack) return null;
  return (
    <section aria-labelledby="reference-pack-heading" data-testid="reference-pack">
      <h2 id="reference-pack-heading" className="mb-2 text-xl font-semibold">{t('referencePack.heading')}</h2>
      <p className="mb-1 max-w-3xl text-sm text-muted-foreground">{pack.status_note[language]}</p>
      <p className="mb-4 text-xs text-muted-foreground">
        {t('referencePack.summary', {
          published: pack.published_records,
          total: pack.record_count,
          cutoff: formatPeriod(pack.research_cutoff, pack.research_cutoff, language),
        })}
      </p>
      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <caption className="sr-only">{t('referencePack.heading')}</caption>
          <thead>
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th scope="col" className="px-3 py-2 text-start font-medium">{t('provenance.sourceCode')}</th>
              <th scope="col" className="px-3 py-2 text-start font-medium">{t('referencePack.publication')}</th>
              <th scope="col" className="px-3 py-2 text-start font-medium">{t('provenance.sourceRole')}</th>
              <th scope="col" className="px-3 py-2 text-end font-medium">{t('referencePack.records')}</th>
              <th scope="col" className="px-3 py-2 text-start font-medium">{t('table.accessDate')}</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => (
              <tr key={s.code} className="border-b border-border align-top last:border-0" data-testid="reference-source" data-code={s.code}>
                <td className="px-3 py-2 font-mono text-xs" dir="ltr">{s.code}</td>
                <td className="px-3 py-2">
                  <span className="font-medium">{s.publisher}</span> — {s.title}
                  {s.publication ? <span className="block text-xs text-muted-foreground">{s.publication}</span> : null}
                  {s.url ? (
                    <a href={s.url} target="_blank" rel="noreferrer" className="block break-all text-xs text-primary underline underline-offset-2" dir="ltr">
                      {s.url}
                    </a>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-xs">{s.role.replaceAll('_', ' ')}</td>
                <td className="px-3 py-2 text-end tabular-nums" dir="ltr">{s.published_records}</td>
                <td className="px-3 py-2 text-xs whitespace-nowrap" dir="ltr">{s.accessed_on}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
