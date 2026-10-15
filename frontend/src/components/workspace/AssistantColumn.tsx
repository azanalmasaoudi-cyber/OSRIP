import { MessageSquareText } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { adapterKind } from '@/api/config';
import { useAssistantUi } from '@/components/assistant/AssistantContext';
import { AssistantAvatar, ORB_STATE_KEY } from '@/components/assistant/AssistantAvatar';
import { AssistantChat } from '@/components/assistant/AssistantPanel';
import { PersonaPicker, usePersona } from '@/components/assistant/persona';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * The assistant beside the analysis: the chosen persona's portrait (a generated image of a
 * fictional person, always labelled as an AI assistant) with its real state, and the chat.
 * The chat mounts only when the person starts it, so merely opening the workspace creates no
 * guest session. Asking here starts a live study shown in the Study tab.
 */
export function AssistantColumn({ startOpen = false, figure = true }: { startOpen?: boolean; figure?: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const ui = useAssistantUi();
  const { persona } = usePersona();
  const [started, setStarted] = useState(startOpen || ui.studies.length > 0);
  const name = persona.name[language];
  if (adapterKind !== 'http') return <StatePanel kind="not_implemented" />;
  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="workspace-assistant" data-persona={persona.code}>
      <div className="flex flex-col items-center gap-2 border-b border-border px-4 py-4 text-center">
        {figure ? (
          <div className="max-lg:hidden" data-testid="workspace-avatar">
            <AssistantAvatar state={ui.state} size="min(11rem, 22vh)" shape="figure" decorative={false} />
          </div>
        ) : null}
        <div className={figure ? 'flex items-center gap-2 lg:hidden' : 'flex items-center gap-2'}>
          <AssistantAvatar state={ui.state} size="3rem" decorative={false} />
        </div>
        <p className="flex flex-wrap items-center justify-center gap-2">
          <span className="font-semibold">{name}</span>
          <Badge variant="accent">{t('assistant.aiAssistant')}</Badge>
        </p>
        <p className="text-sm font-medium" role="status" data-testid="workspace-assistant-state" data-state={ui.state}>
          {t(ORB_STATE_KEY[ui.state])}
        </p>
        <PersonaPicker compact />
        <p className="max-w-xs text-xs text-muted-foreground">{t('workspace.assistant.note', { name })}</p>
      </div>
      {started ? (
        <div className="flex min-h-[28rem] flex-1 flex-col">
          <AssistantChat showIdentity={false} />
        </div>
      ) : (
        <div className="flex flex-col items-start gap-3 p-4">
          <p className="text-sm">{t('workspace.assistant.intro', { name })}</p>
          <Button type="button" onClick={() => setStarted(true)} data-testid="workspace-start-chat">
            <MessageSquareText aria-hidden="true" />{t('workspace.assistant.start', { name })}
          </Button>
        </div>
      )}
    </div>
  );
}
