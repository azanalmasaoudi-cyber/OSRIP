import { Mic } from 'lucide-react';
import { Link, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import { AssistantChat } from '@/components/assistant/AssistantPanel';
import { usePersona } from '@/components/assistant/persona';
import { PageHeader } from '@/components/common/PageHeader';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/** Full-page assistant. A question passed as ?q= (e.g. "explain this forecast") is prefilled, not sent. */
export function AssistantPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { persona } = usePersona();
  const name = persona.name[language];
  const to = usePreservedSearch();
  const [params] = useSearchParams();
  const question = (params.get('q') ?? '').slice(0, 1000);
  return (
    <>
      <PageHeader title={t('assistant.title', { name })} intro={t('assistant.subtitle')}>
        <Link to={to('/talk')} data-testid="open-talk"
          className="mt-1 inline-flex w-fit items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary-hover">
          <Mic aria-hidden="true" className="size-4" />{t('talk.open', { name })}
        </Link>
      </PageHeader>
      <div className="flex h-[min(44rem,calc(100dvh-14rem))] min-h-[28rem] flex-col overflow-hidden rounded-lg border border-border bg-card">
        <AssistantChat initialDraft={question} />
      </div>
    </>
  );
}
