import { motion } from 'motion/react';
import { Link, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useAssistantUi } from './AssistantContext';
import { AssistantAvatar, ORB_STATE_KEY } from './AssistantAvatar';
import { usePersona } from './persona';
import { adapterKind } from '@/api/config';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const MotionLink = motion.create(Link);

/**
 * Floating shortcut to the one Al Mulhim conversation (/assistant): the assistant's fictional
 * face with a visible "AI Assistant" label, at the inline end of the screen (right in English,
 * left in Arabic), above the page but below dialogs. It opens the conversation page; there is no
 * second chat in a side panel. The page keeps bottom padding for it (AppShell), so it never
 * covers the last content. Hidden where the conversation is already on screen: the assistant
 * page and the workspace.
 */
export function AssistantOrb() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { persona } = usePersona();
  const ui = useAssistantUi();
  const { pathname } = useLocation();
  const to = usePreservedSearch();
  if (adapterKind !== 'http' || pathname === '/assistant' || pathname === '/workspace') return null;
  const busy = ui.state !== 'idle';
  return (
    <div className="pointer-events-none fixed end-4 bottom-4 z-40 sm:end-6 sm:bottom-6 print:hidden">
      <MotionLink
        to={to('/assistant')}
        data-testid="open-assistant"
        data-state={ui.state}
        whileHover={{ y: -2 }}
        whileTap={{ scale: 0.97 }}
        transition={{ type: 'spring', stiffness: 400, damping: 28 }}
        className="glass-card pointer-events-auto flex items-center gap-2 rounded-full border py-1 ps-1 pe-3 text-start shadow-raised focus-visible:outline-3 focus-visible:outline-offset-4 focus-visible:outline-ring sm:gap-2.5 sm:py-1.5 sm:ps-1.5 sm:pe-4"
      >
        <AssistantAvatar state={ui.state} size="2.5rem" className="sm:hidden" />
        <AssistantAvatar state={ui.state} size="3rem" className="hidden sm:inline-block" />
        <span className="flex flex-col leading-tight">
          <span className="text-xs font-semibold text-foreground sm:text-sm" data-testid="orb-persona-name">{persona.name[language]}</span>
          <span className={busy ? 'text-xs text-muted-foreground' : 'hidden text-xs text-muted-foreground sm:block'} aria-live="polite">
            {/* Idle: the AI disclosure; otherwise the real state (listening, speaking, ...). */}
            {busy ? t(ORB_STATE_KEY[ui.state]) : t('assistant.aiAssistant')}
          </span>
        </span>
        <span className="sr-only">{busy ? '' : ` — ${t('assistant.open')}`}</span>
      </MotionLink>
    </div>
  );
}
