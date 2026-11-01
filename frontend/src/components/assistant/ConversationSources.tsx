import { BookOpen, ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { AssistantMessage, Evidence } from '@/api/assistant';
import { DataStatusBadge } from '@/components/common/DataStatusBadge';
import { Badge } from '@/components/ui/badge';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

import { pick } from './Evidence';

type SourceClass = 'official' | 'international' | 'research' | 'secondary' | 'record';

interface Source {
  key: string;
  title: string;
  publisher: string;
  url: string | null;
  cls: SourceClass;
  status: string | undefined;
}

/** Official Omani publishers first, then international bodies, research, other web pages. */
const ORDER: Record<SourceClass, number> = { official: 0, record: 1, international: 2, research: 3, secondary: 4 };

function sourceOf(e: Evidence, language: 'en' | 'ar'): Source | null {
  if (e.kind === 'search' || e.kind === 'note') return null;
  if (e.kind === 'web') {
    const title = (typeof e.title === 'string' ? e.title : pick(e.title, language)) || e.host || '';
    const publisher = typeof e.publisher === 'string' ? e.publisher : pick(e.publisher, language);
    return { key: e.url ?? title, title, publisher, url: e.url ?? null, cls: e.source_class ?? 'secondary', status: e.data_status };
  }
  if (!e.source) return null;
  // A published record of the platform: approved official observations rank with official pages.
  const cls: SourceClass = e.data_status === 'approved_official' ? 'official' : 'record';
  return { key: e.source.url ?? e.source.title, title: e.source.title, publisher: e.source.publisher ?? '', url: e.source.url, cls, status: e.data_status };
}

/**
 * Every source the assistant's answers in this conversation relied on, once each, official
 * sources first, with the kind of each (approved official observation, unreviewed web evidence,
 * synthetic demonstration data…). Shown beside the conversation on wide screens; on smaller
 * screens each answer lists its own sources under "Sources".
 */
export function ConversationSources({ messages, className }: { messages: readonly AssistantMessage[]; className?: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const seen = new Map<string, Source>();
  for (const m of messages) {
    if (m.role === 'user') continue;
    for (const e of m.evidence) {
      const s = sourceOf(e, language);
      if (s && s.key && !seen.has(s.key)) seen.set(s.key, s);
    }
  }
  const sources = [...seen.values()].sort((a, b) => ORDER[a.cls] - ORDER[b.cls]);
  return (
    <aside aria-labelledby="conversation-sources-h" className={cn('min-h-0 flex-col gap-3 overflow-y-auto rounded-lg border border-border bg-card p-4 shadow-card', className)}
      data-testid="conversation-sources">
      <h2 id="conversation-sources-h" className="flex items-center gap-2 text-base font-semibold">
        <BookOpen aria-hidden="true" className="size-4 text-primary" />{t('chat.sourcesPanel')}
        {sources.length ? <span className="text-xs font-normal text-muted-foreground">({sources.length})</span> : null}
      </h2>
      {sources.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('chat.sourcesPanelEmpty')}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {sources.map((s) => (
            <li key={s.key} className="flex flex-col gap-1 rounded-md border border-border bg-background p-2.5 text-xs" data-class={s.cls}>
              <p className="flex flex-wrap items-center gap-1">
                <Badge variant={s.cls === 'official' ? 'verified' : s.cls === 'record' || s.cls === 'international' ? 'outline' : 'sand'}>
                  {t(`chat.sourceClass.${s.cls}`)}
                </Badge>
                <DataStatusBadge status={s.status} />
              </p>
              {s.url && /^https?:\/\//.test(s.url) ? (
                <a href={s.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-start gap-1 font-medium text-primary underline underline-offset-2">
                  <bdi>{s.title}</bdi><ExternalLink aria-hidden="true" className="mt-0.5 size-3 shrink-0" />
                </a>
              ) : <p className="font-medium"><bdi>{s.title}</bdi></p>}
              {s.publisher ? <p className="text-muted-foreground"><bdi>{s.publisher}</bdi></p> : null}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
