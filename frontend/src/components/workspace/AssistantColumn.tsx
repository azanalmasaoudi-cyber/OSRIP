import { MessageSquareText, Mic, PanelRightOpen } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
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
import { usePreservedSearch } from '@/state/usePreservedSearch';

/**
 * The compact assistant beside the analysis: the chosen persona's portrait (a generated image
 * of a fictional person, always labelled as an AI assistant) with its real state, the persona
 * choice, links to the full conversation and to Talk, and the chat. The chat mounts only when
 * the person starts it, so merely opening the workspace creates no guest session. Asking here
 * starts a live study shown in the Study tab.
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
      <div className="flex flex-col gap-3 border-b border-border p-4">
        <div className="flex items-center gap-3">
          <div data-testid="workspace-avatar">
            <AssistantAvatar state={ui.state} size="3rem" decorative={false} />
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
        </div>
        <PersonaPicker compact />
        <p className="text-xs text-muted-foreground">{t('workspace.assistant.note', { name })}</p>
        <div className="flex flex-wrap gap-2">
          <Link to={to('/assistant')} className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs font-medium hover:bg-muted"
            data-testid="workspace-open-full">
            <PanelRightOpen aria-hidden="true" className="size-3.5 rtl:-scale-x-100" />{t('workspace.assistant.openFull')}
          </Link>
          <Link to={to('/talk')} className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs font-medium hover:bg-muted"
            data-testid="workspace-open-talk">
            <Mic aria-hidden="true" className="size-3.5" />{t('workspace.assistant.talk')}
          </Link>
        </div>
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
