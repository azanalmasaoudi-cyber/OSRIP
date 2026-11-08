import { MessageSquareText, PanelRightOpen } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { adapterKind } from '@/api/config';
import { useAssistantUi } from '@/components/assistant/AssistantContext';
import { AssistantAvatar, ORB_STATE_KEY } from '@/components/assistant/AssistantAvatar';
import { AssistantChat } from '@/components/assistant/AssistantPanel';
import { usePersona } from '@/components/assistant/persona';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * Al Mulhim beside the analysis: the same conversation as the AI Assistant page, embedded
 * (compact, without the history column), with the assistant's real state and a link to the
 * full conversation. The chat mounts only when the person starts it, so merely opening the
 * workspace creates no guest session. Asking here starts a live study shown in the Study tab.
 */
export function AssistantColumn({ startOpen = false }: { startOpen?: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const ui = useAssistantUi();
  const { persona } = usePersona();
  const to = usePreservedSearch();
  const [started, setStarted] = useState(startOpen || ui.studies.length > 0);
  const name = persona.name[language];
  if (adapterKind !== 'http') return <StatePanel kind="not_implemented" />;
  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="workspace-assistant" data-persona={persona.code}>
      <div className="flex items-center gap-3 border-b border-border p-4">
        <div data-testid="workspace-avatar">
          <AssistantAvatar state={ui.state} size="2.75rem" decorative={false} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold">{name}</span>
            <Badge variant="accent">{t('assistant.aiAssistant')}</Badge>
          </p>
          <p className="text-xs font-medium text-muted-foreground" role="status" data-testid="workspace-assistant-state" data-state={ui.state}>
            {t(ORB_STATE_KEY[ui.state])}
          </p>
        </div>
        <Link to={to('/assistant')} className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs font-medium hover:bg-muted"
          data-testid="workspace-open-full">
          <PanelRightOpen aria-hidden="true" className="size-3.5 rtl:-scale-x-100" />{t('workspace.assistant.openFull')}
        </Link>
      </div>
      {started ? (
        <div className="flex min-h-[28rem] flex-1 flex-col px-3 pt-3">
          <AssistantChat layout="embedded" />
        </div>
      ) : (
        <div className="flex flex-col items-start gap-3 p-4">
          <p className="text-xs text-muted-foreground">{t('workspace.assistant.note', { name })}</p>
          <p className="text-sm">{t('workspace.assistant.intro', { name })}</p>
          <Button type="button" onClick={() => setStarted(true)} data-testid="workspace-start-chat">
            <MessageSquareText aria-hidden="true" />{t('workspace.assistant.start', { name })}
          </Button>
        </div>
      )}
    </div>
  );
}
