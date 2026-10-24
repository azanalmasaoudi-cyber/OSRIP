import { motion } from 'motion/react';
import { useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useAssistantUi } from './AssistantContext';
import { AssistantAvatar, ORB_STATE_KEY } from './AssistantAvatar';
import { AssistantPanel } from './AssistantPanel';
import { usePersona } from './persona';
import { adapterKind } from '@/api/config';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * Floating entry point to the assistant: the AI Assistant's fictional face with a visible
 * "AI Assistant" label, at the inline end of the screen (right in English, left in
 * Arabic), above the page but below dialogs. The page keeps bottom padding for it
 * (AppShell), so it never covers the last content, forms or charts. Hidden on the full
 * assistant page and the workspace, where the chat is already on screen.
 *
 * The panel mounts on first open (so visitors who never open it get no guest session)
 * and then stays mounted: closing goes through the native dialog's close(), and focus
 * returns to this button.
 */
export function AssistantOrb() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { persona } = usePersona();
  const ui = useAssistantUi();
  const { pathname } = useLocation();
  const button = useRef<HTMLButtonElement>(null);
  const [mounted, setMounted] = useState(false);
  if (ui.open && !mounted) setMounted(true); // adjusting state while rendering (React docs pattern)
  // Hidden where the chat is already on screen: the assistant page and the workspace (where
  // the assistant sits beside the analysis, or in its own tab on phones).
  if (adapterKind !== 'http' || pathname === '/assistant' || pathname === '/workspace') return null;
  const busy = ui.state !== 'idle';
  const close = () => {
    ui.setOpen(false);
    requestAnimationFrame(() => button.current?.focus());
  };
  return (
    <>
      <div className="pointer-events-none fixed end-4 bottom-4 z-40 sm:end-6 sm:bottom-6 print:hidden">
        <motion.button
          ref={button}
          type="button"
          onClick={() => ui.setOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={ui.open}
          data-testid="open-assistant"
          data-state={ui.state}
          whileHover={{ y: -2 }}
          whileTap={{ scale: 0.97 }}
          transition={{ type: 'spring', stiffness: 400, damping: 28 }}
          className="pointer-events-auto flex items-center gap-2 rounded-full border border-border bg-card py-1 ps-1 pe-3 text-start shadow-raised focus-visible:outline-3 focus-visible:outline-offset-4 focus-visible:outline-ring sm:gap-2.5 sm:py-1.5 sm:ps-1.5 sm:pe-4"
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
          <span className="sr-only">
            {busy ? '' : ` — ${t('assistant.open')}`}
          </span>
        </motion.button>
      </div>
      {mounted ? <AssistantPanel open={ui.open} onClose={close} /> : null}
    </>
  );
}
