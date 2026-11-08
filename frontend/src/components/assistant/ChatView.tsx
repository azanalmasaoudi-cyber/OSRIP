import {
  ArrowDown, ArrowUp, BarChart3, BookOpen, Check, CircleHelp, Copy, EyeOff, Globe, Loader2, MessageSquare, MessageSquarePlus, Mic, MicOff,
  PanelLeft, RotateCcw, Settings2, SlidersHorizontal, Sparkles, Square, Trash2, Volume2, VolumeX, X,
} from 'lucide-react';
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useAssistantUi } from './AssistantContext';
import { AssistantAvatar, ORB_STATE_KEY } from './AssistantAvatar';
import { AssistantStatusBar } from './AssistantStatusBar';
import type { ChatVoice } from './AssistantPanel';
import {
  EvidenceItem, GroundedContext, pick, SAVEABLE, SaveResearchButton, SearchLog, STATUS_BADGE, WebEvidenceItem,
} from './Evidence';
import { AnswerReportButton } from './AnswerReportButton';
import { ChatDataCharts, ChatDataTables, ResearchSummary } from './ChatData';
import { GeneratedImages, ResearchCharts, ResearchDiagrams, ResearchPlan, ResearchTables } from './ResearchVisuals';
import { asksForChart, chartPoints, InlineChart } from './InlineChart';
import { IntroPlayer } from './IntroPlayer';
import { Markdown } from './Markdown';
import { AboutMulhim, MemoryPanel } from './MulhimPanels';
import { usePersona } from './persona';
import { PersonaImage } from './PersonaImage';
import { StreamingAnswer } from './StreamingAnswer';
import {
  CitationChip, DataReportNotice, evidenceAnchor, SourcesShown, StructuredParts, WebNotice, withoutMarkers,
} from './StructuredReply';
import { VoicePanel } from './VoicePanel';
import { VoiceVolume } from './VoiceVolume';
import {
  DATA_MODES, INTERNET_MODES, isInternetMode, useAssistantStatus, useCancelRequest, useVoiceStatus,
  type Allowance, type AskSelection, type AssistantMessage, type ConversationSummary, type Evidence, type RequestMode,
} from '@/api/assistant';
import { ApiRequestError } from '@/api/client';
import type { DataMode } from '@/domain/types';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import { Segmented } from '@/components/ui/segmented';
import { formatDate, formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/** Everything the conversation needs from the chat's state (AssistantChat owns it). */
export interface ChatModel {
  language: 'en' | 'ar';
  setLanguage: (language: 'en' | 'ar') => void;
  dataMode: DataMode;
  messages: AssistantMessage[];
  pending: boolean;
  /** The question being answered, until the conversation returns it. */
  asking: { text: string; requestId: string | null; echo: boolean } | null;
  guest: boolean;
  error: Error | null;
  send: (text: string) => void;
  retry: () => void;
  draft: string;
  type: (text: string) => void;
  max: number;
  inputId: string;
  viaVoice: boolean;
  canAsk: boolean;
  needsAccount: boolean;
  signedIn: boolean;
  allowance: Allowance | null;
  signInPrompt: ReactNode;
  voice: ChatVoice;
  speak: ((message: AssistantMessage) => void) | null;
  web: { available: boolean; on: boolean; set: (on: boolean) => void };
  mode: { value: RequestMode; set: (mode: RequestMode) => void };
  crossCheck: { available: boolean; on: boolean; set: (on: boolean) => void };
  /** A signed-in person's saved conversations (null for guests). */
  conversations: {
    list: ConversationSummary[]; activeId: string | null; loading: boolean; removing: boolean;
    select: (id: string | null) => void; remove: (id: string) => void;
  } | null;
  /** A guest's one conversation in this browser tab, if started. */
  guestConversationId: string | null;
  newConversation: () => void;
  linkPrompt: ReactNode;
  memory: { guestExpires: string | null; guestConversationId: string | null; onGuestDeleted: () => void; onAllDeleted: () => void };
  selection: { value: AskSelection | null; label?: string; clear: () => void };
  brief: ReactNode;
  openStudy: (id: string) => void;
  activeStudyId: string | null;
  suggestions: string[];
  /** Page-specific tools (shortage and surplus analysis, a full study), in the Tools menu. */
  tools?: ReactNode;
}

const NEAR_BOTTOM = 96; // px: closer than this to the end counts as reading the latest message

/**
 * The one Al Mulhim conversation. On the AI Assistant page ("page"): the conversation history
 * beside it (a drawer on narrower screens), a compact header, one scrolling conversation centred
 * at most 52rem wide, and a large message box at the bottom with Tools, the microphone and Send
 * (Stop while an answer is written). Before the first message: a centred welcome and examples.
 * In the workspace ("embedded") the same chat, without the history column.
 *
 * Answers are written as they arrive (StreamingAnswer: the real stage, then the checked
 * sentences), with tables, charts and diagrams inline. Sources, citation markers and search
 * logs stay hidden until the person asks (Show sources, or asking in words). Answers built from
 * OSRIP's synthetic demonstration data say so; internet research answers carry no data-mode
 * label. Settings and the optional Tools menu are drawers, not part of the conversation.
 */
export function ChatView({ chat, layout = 'page' }: { chat: ChatModel; layout?: 'page' | 'embedded' }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const ui = useAssistantUi();
  const { persona } = usePersona();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const page = layout === 'page';

  // One scrolling area. New messages scroll into view only while the person is at the end;
  // otherwise a "New messages" button appears.
  const scroller = useRef<HTMLDivElement>(null);
  const [atEnd, setAtEnd] = useState(true);
  // The person's own question always brings the end into view.
  const [follow, setFollow] = useState(false);
  const [unseen, setUnseen] = useState(false);
  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    const end = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM;
    setAtEnd(end);
    if (end) {
      setUnseen(false);
      setFollow(false);
    }
  };
  const toEnd = () => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
    setAtEnd(true);
    setUnseen(false);
  };
  const echo = chat.asking?.echo ? chat.asking : null;
  const items = chat.messages.length + (echo ? 1 : 0) + (chat.pending ? 1 : 0) + (chat.error ? 1 : 0);
  const [shownItems, setShownItems] = useState(items);
  if (items !== shownItems) {
    // Something new arrived (adjusting state while rendering, not in an effect).
    setShownItems(items);
    if (!atEnd && !follow) setUnseen(true);
  }
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && (atEnd || follow)) el.scrollTop = el.scrollHeight;
  }, [items, atEnd, follow]);

  const send = (text: string) => {
    setFollow(true);
    chat.send(text);
  };
  const startNew = () => {
    chat.newConversation();
    toEnd();
  };
  const started = chat.messages.length > 0 || Boolean(echo) || chat.pending;
  const name = persona.name[language];

  return (
    <div className="flex min-h-0 flex-1 gap-4 xl:gap-6" data-testid="assistant-panel" data-variant="chat" data-layout={layout} lang={chat.language}>
      {page ? (
        <aside className="glass-card hidden w-68 shrink-0 flex-col overflow-hidden rounded-3xl border lg:flex" data-testid="chat-history"
          aria-label={t('chat.history.title')}>
          <ChatHistory chat={chat} onNew={startNew} />
        </aside>
      ) : null}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="mx-auto flex w-full max-w-[52rem] shrink-0 items-center gap-2 pb-2" data-testid="chat-header">
          {page ? (
            <Button type="button" variant="ghost" size="sm" className="w-9 shrink-0 px-0 lg:hidden" onClick={() => setHistoryOpen(true)}
              data-testid="chat-history-open" title={t('chat.history.open')} aria-haspopup="dialog">
              <PanelLeft aria-hidden="true" className="rtl:-scale-x-100" /><span className="sr-only">{t('chat.history.open')}</span>
            </Button>
          ) : null}
          <AssistantAvatar state={ui.state} size="2.25rem" decorative={false} />
          <div className="flex min-w-0 flex-1 flex-col leading-tight">
            <h1 className="truncate text-base font-semibold sm:text-lg" data-testid="mulhim-name" data-persona={persona.code}>{name}</h1>
            <span className="truncate text-xs text-muted-foreground" role="status" data-testid="chat-state" data-state={ui.state}>
              {ui.state === 'idle' ? t('assistant.aiAssistant') : t(ORB_STATE_KEY[ui.state])}
            </span>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={startNew} data-testid="chat-new" title={t('chat.newConversation')}>
            <MessageSquarePlus aria-hidden="true" /><span className={page ? 'max-sm:sr-only' : 'sr-only'}>{t('chat.newConversation')}</span>
          </Button>
          <Button type="button" variant="ghost" size="sm" className="w-9 px-0" onClick={() => setSettingsOpen(true)} data-testid="chat-settings"
            title={t('chat.settings')} aria-haspopup="dialog">
            <Settings2 aria-hidden="true" /><span className="sr-only">{t('chat.settings')}</span>
          </Button>
        </header>

        <div className="relative min-h-0 flex-1">
          <div ref={scroller} onScroll={onScroll} className="h-full overflow-y-auto" data-testid="assistant-messages" aria-live="polite">
            <div className="mx-auto flex min-h-full w-full max-w-[52rem] flex-col gap-6 px-1 py-5">
              {!started && chat.canAsk && !chat.needsAccount ? (
                <Welcome chat={chat} compact={!page} onAsk={send} />
              ) : null}
              {chat.linkPrompt}
              <ol className="flex flex-col gap-6">
                {chat.messages.map((m, i) => (
                  <ChatMessage key={m.id} message={m} question={i > 0 ? chat.messages[i - 1]?.content : undefined}
                    chat={chat} onAsk={send} />
                ))}
                {echo ? <UserBubble text={echo.text} pending /> : null}
                {chat.pending ? <StreamingAnswer requestId={chat.asking?.requestId ?? null} guest={chat.guest} /> : null}
              </ol>
              {chat.needsAccount ? chat.signInPrompt : null}
              {chat.error ? (
                <div role="alert" className="flex flex-wrap items-center gap-2 rounded-2xl border border-destructive/40 bg-destructive/5 px-4 py-3 text-base text-destructive"
                  data-testid="assistant-error">
                  <p>{chat.error instanceof ApiRequestError && chat.error.code === 'network_unavailable' ? t('chat.errorNetwork') : chat.error.message}</p>
                  <Button variant="outline" size="sm" onClick={chat.retry} data-testid="error-retry"><RotateCcw aria-hidden="true" />{t('states.retry')}</Button>
                </div>
              ) : null}
            </div>
          </div>
          {unseen ? (
            <button type="button" onClick={toEnd} data-testid="chat-new-messages"
              className="glass-card absolute inset-x-0 bottom-3 mx-auto flex w-fit items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium shadow-raised hover:bg-muted">
              <ArrowDown aria-hidden="true" className="size-3.5" />{t('chat.newMessages')}
            </button>
          ) : null}
        </div>

        <Composer chat={chat} onSend={send} onTools={() => setToolsOpen(true)} />
      </div>

      {page ? (
        <Dialog open={historyOpen} onClose={() => setHistoryOpen(false)} title={t('chat.history.title')} placement="end">
          <ChatHistory chat={chat} onNew={() => { startNew(); setHistoryOpen(false); }} onPicked={() => setHistoryOpen(false)} />
        </Dialog>
      ) : null}
      <Dialog open={settingsOpen} onClose={() => setSettingsOpen(false)} title={t('chat.settings')} placement="end">
        <SettingsSheet chat={chat} />
      </Dialog>
      <Dialog open={toolsOpen} onClose={() => setToolsOpen(false)} title={t('chat.tools')} description={t('chat.toolsIntro')} placement="end">
        {/* After the brief fills the box: close the drawer, then put the person in the box (the
            modal drawer keeps focus inside until it is closed). */}
        <ToolsSheet chat={chat} onClose={() => setToolsOpen(false)} onBriefUsed={() => {
          setToolsOpen(false);
          window.setTimeout(() => document.getElementById(chat.inputId)?.focus(), 30);
        }} />
      </Dialog>
    </div>
  );
}

/** Before the first message: who answers, what to ask, and a few examples to start from. */
function Welcome({ chat, compact, onAsk }: { chat: ChatModel; compact: boolean; onAsk: (text: string) => void }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const ui = useAssistantUi();
  const { persona } = usePersona();
  const examples = chat.suggestions.slice(0, compact ? 3 : 4);
  return (
    <section className={cn('flex flex-1 flex-col items-center justify-center text-center', compact ? 'gap-3 py-4' : 'gap-6 py-10')}
      data-testid="chat-welcome">
      <div className="relative">
        <span aria-hidden="true" className="absolute -inset-3 rounded-full bg-gradient-to-br from-brand/35 via-brand-2/15 to-transparent blur-xl" />
        <AssistantAvatar state={ui.state} size={compact ? '3.25rem' : '4.75rem'} className="relative" />
      </div>
      <div className="flex max-w-2xl flex-col gap-2">
        <p className="text-sm font-semibold tracking-wide text-brand">{persona.name[language]} · {t('assistant.aiAssistant')}</p>
        <p className={cn('font-semibold tracking-tight text-balance', compact ? 'text-xl' : 'text-3xl sm:text-4xl')} data-testid="chat-greeting">
          {t('chat.welcome')}
        </p>
        <p className="text-base text-pretty text-muted-foreground" data-testid="chat-welcome-lead">{t('chat.welcomeLead')}</p>
      </div>
      {examples.length ? (
        <ul className={cn('grid w-full gap-2.5 text-start', compact ? 'max-w-xl' : 'max-w-3xl sm:grid-cols-2')} data-testid="suggestions">
          {examples.map((s) => (
            <li key={s}>
              <button type="button" onClick={() => onAsk(s)} dir="auto" data-testid="suggestion"
                className="glass-card group flex h-full w-full items-start gap-2.5 rounded-2xl border px-4 py-3 text-start text-sm leading-snug transition-[border-color,transform] hover:-translate-y-0.5 hover:border-brand/50 motion-reduce:transition-none motion-reduce:hover:translate-y-0 focus-visible:outline-2 focus-visible:outline-ring sm:text-base">
                <Sparkles aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-brand" />
                <span>{s}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** The conversation history: a new conversation, then the saved ones (newest first). */
function ChatHistory({ chat, onNew, onPicked }: { chat: ChatModel; onNew: () => void; onPicked?: () => void }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const [confirming, setConfirming] = useState<string | null>(null);
  const conv = chat.conversations;
  const item = 'flex min-w-0 flex-1 items-center gap-2 rounded-xl px-3 py-2 text-start text-sm transition-colors motion-reduce:transition-none';
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3" data-testid="chat-history-body">
      <Button type="button" onClick={onNew} className="w-full justify-start rounded-xl" data-testid="history-new">
        <MessageSquarePlus aria-hidden="true" />{t('chat.newConversation')}
      </Button>
      {conv ? (
        <nav className="flex min-h-0 flex-1 flex-col gap-1" aria-label={t('chat.history.title')}>
          <p className="px-3 text-xs font-semibold text-muted-foreground">{t('chat.history.recent')}</p>
          {conv.loading ? (
            <p className="px-3 text-sm text-muted-foreground" role="status">{t('chat.history.loading')}</p>
          ) : conv.list.length === 0 ? (
            <p className="px-3 text-sm text-muted-foreground" data-testid="conversation-list-empty">{t('chat.history.empty')}</p>
          ) : (
            <ul className="-mx-1 flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-1" data-testid="conversation-list">
              {conv.list.map((c) => {
                const active = c.id === conv.activeId;
                return (
                  <li key={c.id} className="group flex items-center gap-1" data-testid="conversation-item" data-active={active}>
                    <button type="button" aria-current={active ? 'true' : undefined} data-testid="conversation-open"
                      onClick={() => { conv.select(c.id); setConfirming(null); onPicked?.(); }}
                      className={cn(item, active ? 'bg-primary-soft font-medium text-foreground' : 'hover:bg-muted')}>
                      <MessageSquare aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
                      <span className="flex min-w-0 flex-col">
                        <span className="truncate" dir="auto">{c.title}</span>
                        <span className="text-xs text-muted-foreground">{formatDate(c.updated_at, language)}</span>
                      </span>
                    </button>
                    {confirming === c.id ? (
                      <Button type="button" size="sm" variant="outline" className="shrink-0 text-destructive" disabled={conv.removing}
                        data-testid="conversation-delete-confirm" onClick={() => { conv.remove(c.id); setConfirming(null); }}>
                        {t('chat.history.confirmDelete')}
                      </Button>
                    ) : (
                      <Button type="button" size="sm" variant="ghost" className="w-8 shrink-0 px-0 opacity-70 group-hover:opacity-100 focus-visible:opacity-100"
                        data-testid="conversation-delete" title={t('chat.history.delete')} onClick={() => setConfirming(c.id)}>
                        <Trash2 aria-hidden="true" /><span className="sr-only">{t('chat.history.delete')}: {c.title}</span>
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </nav>
      ) : (
        <div className="flex flex-col gap-2" data-testid="history-guest">
          {chat.guestConversationId ? (
            <p className={cn(item, 'bg-primary-soft font-medium')} aria-current="true" data-testid="conversation-item" data-active="true">
              <MessageSquare aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />{t('chat.history.current')}
            </p>
          ) : null}
          <p className="px-3 text-sm text-muted-foreground" data-testid="history-guest-note">
            {t('chat.history.guestNote')}{' '}
            <Link to={to('/sign-in')} className="font-medium text-primary underline underline-offset-2">{t('chat.history.signIn')}</Link>
          </p>
        </div>
      )}
    </div>
  );
}

function UserBubble({ text, pending = false }: { text: string; pending?: boolean }) {
  return (
    <li className="ms-auto max-w-[85%] rounded-3xl rounded-ee-lg border border-brand/25 bg-primary-soft px-4 py-2.5 text-base whitespace-pre-wrap shadow-card"
      dir="auto" data-testid="user-message" data-pending={pending ? 'true' : undefined}>
      {text}
    </li>
  );
}

function ChatMessage({ message, question, chat, onAsk }: {
  message: AssistantMessage; question: string | undefined; chat: ChatModel; onAsk: (q: string) => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { byCode } = usePersona();
  const [copied, setCopied] = useState(false);
  // Sources, citation markers and the search log are shown only when asked for: with the Show
  // sources button, or by asking in words (a 'sources' reply, shown with its list).
  const [sourcesOpen, setSourcesOpen] = useState(message.status === 'sources');
  // A chart is offered under an answer that has chartable figures, and drawn only when the
  // person asks: in words ("show a chart of …") or with the Show chart button.
  const [chartOpen, setChartOpen] = useState(() => asksForChart(question) && message.status !== 'clarification');
  if (message.role === 'user') return <UserBubble text={message.content} />;
  const author = byCode(message.persona);
  const badge = message.status ? STATUS_BADGE[message.status] : null;
  const searches = message.evidence.filter((e) => e.kind === 'search');
  const evidence = message.evidence.filter((e) => e.kind !== 'search');
  const byId = new Map(evidence.map((e) => [e.id, e]));
  const shown = message.citations.length ? message.citations.map((c) => byId.get(c)).filter((e): e is Evidence => Boolean(e)) : evidence;
  const known = new Set([...shown.map((e) => e.id), ...message.calculations.map((c) => c.id)]);
  const anchor = (id: string) => evidenceAnchor(message.id, id);
  const failed = message.status === 'unavailable' || message.status === 'data_report';
  // The server's chart of the table's own rows when it built one; otherwise the cited values.
  const chartable = message.status !== 'clarification';
  const wantsChart = asksForChart(question) && chartable;
  const dataCharts = chartable ? message.structured.data_charts ?? [] : [];
  const points = chartable && !dataCharts.length ? chartPoints(shown) : null;
  const canChart = dataCharts.length > 0 || points !== null;
  const sourceNames = [...new Set(shown.map((e) => e.source?.title ?? (typeof e.title === 'string' ? e.title : pick(e.title, language))).filter(Boolean))];
  const hasSources = shown.length > 0 || searches.length > 0 || Boolean(message.structured.grounded_context?.length)
    || Boolean(message.structured.research?.sources_read.length);
  const research = message.structured.research;
  // An answer from OSRIP's own data in a synthetic conversation says so; internet answers do not
  // use OSRIP's data and carry no data-mode label.
  const fromPlatformData = !isInternetMode(message.mode ?? 'ask') && message.status !== 'profile' && message.status !== 'sources';
  const syntheticLabel = chat.dataMode === 'synthetic' && fromPlatformData;
  const copy = () => {
    const text = sourcesOpen
      ? [message.content, ...(sourceNames.length ? ['', `${t('assistant.sources')}: ${sourceNames.join(' · ')}`] : [])].join('\n')
      : withoutMarkers(message.content);
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <SourcesShown.Provider value={sourcesOpen}>
    <li className="glass-card flex flex-col gap-2.5 rounded-3xl rounded-es-lg border p-4 text-base leading-relaxed shadow-card sm:p-5" data-testid="assistant-message"
      data-status={message.status ?? ''} data-persona={author.code} data-sources={sourcesOpen ? 'shown' : 'hidden'}>
      <p className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-1.5 font-semibold text-foreground" data-testid="message-persona">
          <PersonaImage src={author.avatar.portrait} alt="" width={22} height={22} className="size-5.5 rounded-full object-cover object-top ring-1 ring-brand/30" draggable={false} />
          {author.name[language]}
        </span>
        {message.ai_generated ? (
          <span className="inline-flex items-center gap-1" data-testid="ai-label"><Sparkles aria-hidden="true" className="size-3 text-brand" />{t('assistant.aiLabel')}</span>
        ) : (
          <span data-testid="non-ai-label">
            {message.status === 'lookup' ? t('assistant.lookupLabel') : message.status === 'profile' ? t('assistant.profileLabel')
              : message.status === 'data_report' ? t('assistant.dataReportLabel')
                : message.status === 'sources' ? t('assistant.sourcesLabel') : t('assistant.systemLabel')}
          </span>
        )}
        {badge ? <Badge variant="sand">{t(badge)}</Badge> : null}
        {/* Which kind of answer was given (chosen automatically unless picked in Tools). */}
        {message.mode && message.mode !== 'ask' ? <Badge variant="outline" data-testid="reply-mode">{t(message.mode === 'research' ? 'assistant.mode.researchLong' : `assistant.mode.${message.mode}`)}</Badge> : null}
        {syntheticLabel ? <DataModeBadge mode="synthetic" compact /> : null}
      </p>
      <div className="flex flex-col gap-3" data-testid="assistant-text">
        <Markdown text={sourcesOpen ? message.content : withoutMarkers(message.content)}
          cite={(id) => <CitationChip messageId={message.id} id={id} known={known.has(id)} />} />
      </div>
      {message.structured.omitted_claims ? (
        <p className="text-sm text-muted-foreground" data-testid="omitted-claims">{t('assistant.omittedClaims', { count: message.structured.omitted_claims })}</p>
      ) : null}
      {message.structured.data_tables?.length ? <ChatDataTables blocks={message.structured.data_tables} messageId={message.id} /> : null}
      {/* Deep research: tables, charts and diagrams from verified web figures; illustrations. */}
      {message.structured.research_tables?.length ? <ResearchTables tables={message.structured.research_tables} messageId={message.id} /> : null}
      {message.structured.research_charts?.length ? <ResearchCharts charts={message.structured.research_charts} messageId={message.id} /> : null}
      {message.structured.diagrams?.length ? <ResearchDiagrams diagrams={message.structured.diagrams} messageId={message.id} /> : null}
      {message.structured.images?.length ? <GeneratedImages images={message.structured.images} messageId={message.id} /> : null}
      {message.structured.plan?.length ? <ResearchPlan plan={message.structured.plan} /> : null}
      {canChart ? (
        <Button type="button" variant="outline" size="sm" className="w-fit rounded-full" aria-expanded={chartOpen} onClick={() => setChartOpen(!chartOpen)}
          data-testid={chartOpen ? 'chat-hide-chart' : 'chat-show-chart'}>
          {chartOpen ? <EyeOff aria-hidden="true" /> : <BarChart3 aria-hidden="true" />}
          {chartOpen ? t('chart.hide') : t('chart.show')}
        </Button>
      ) : null}
      {chartOpen && dataCharts.length ? <ChatDataCharts charts={dataCharts} messageId={message.id} /> : null}
      {chartOpen && !dataCharts.length && points ? <InlineChart points={points} messageId={message.id} /> : null}
      {wantsChart && !canChart && message.status === 'answered' ? (
        <p className="text-sm text-muted-foreground" data-testid="chart-unavailable">{t('chat.chartUnavailable')}</p>
      ) : null}
      {research && sourcesOpen ? <ResearchSummary summary={research} /> : null}
      {research && !sourcesOpen && research.submitted > 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="research-review-note">{t('chat.research.sentForReview', { count: research.submitted })}</p>
      ) : null}
      {/* Figures from the web are never OSRIP's published data: one short line says where they go. */}
      {!research && shown.some((e) => e.kind === 'web') ? (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground" data-testid="web-review-note">
          <Globe aria-hidden="true" className="mt-0.5 size-3 shrink-0" />{t('web.reviewNote')}
        </p>
      ) : null}
      {message.structured.data_report ? <DataReportNotice report={message.structured.data_report} /> : null}
      {message.structured.web_notice ? <WebNotice notice={message.structured.web_notice} /> : null}
      {message.structured && Object.keys(message.structured).length ? (
        <StructuredParts structured={message.structured} messageId={message.id} known={known} />
      ) : null}
      {sourcesOpen ? <SearchLog items={searches} /> : null}
      {sourcesOpen && message.structured.grounded_context?.length ? <GroundedContext entries={message.structured.grounded_context} /> : null}
      {sourcesOpen && shown.length > 0 ? (
        <details className="group text-sm" data-testid="chat-sources" open>
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
            <span className="font-semibold">{t('chat.sourcesCount', { count: shown.length })}</span>
            {sourceNames.length ? <span className="ms-1" dir="auto">· {sourceNames.slice(0, 2).join(' · ')}{sourceNames.length > 2 ? ' …' : ''}</span> : null}
          </summary>
          <ul className="mt-2 flex flex-col gap-1.5">
            {shown.map((e) => (e.kind === 'web'
              ? <WebEvidenceItem key={e.id} item={e} anchor={anchor(e.id)} />
              : <EvidenceItem key={e.id} item={e} anchor={anchor(e.id)} />))}
          </ul>
        </details>
      ) : null}
      {message.calculations.length > 0 ? (
        <details className="text-sm" data-testid="how-calculated">
          <summary className="cursor-pointer font-semibold text-muted-foreground hover:text-foreground">{t('assistant.howCalculated')}</summary>
          <ul className="mt-2 flex flex-col gap-2">
            {message.calculations.map((c) => (
              <li key={c.id} id={anchor(c.id)} tabIndex={-1} className="scroll-mt-4 focus-visible:outline-2">
                <p className="font-mono">{sourcesOpen ? `[${c.id}] ` : ''}{c.calculation}</p>
                <p>{pick(c.formula, language)}</p>
                {c.value != null ? (
                  <p>{t('analysis.result')}: <span className="tabular-nums" dir="ltr">{formatDecimal(c.value, language, 4)}</span> {c.unit === 'percent' ? '%' : c.unit}</p>
                ) : c.reason ? <p className="text-muted-foreground">{pick(c.reason, language)}</p> : null}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-muted-foreground">{t('assistant.calculatedByPlatform')}</p>
        </details>
      ) : null}
      <div className="-ms-2 flex flex-wrap items-center gap-0.5 text-xs" data-testid="message-actions">
        {hasSources && message.status !== 'sources' ? (
          <Button type="button" variant="ghost" size="sm" aria-expanded={sourcesOpen} onClick={() => setSourcesOpen(!sourcesOpen)}
            data-testid="toggle-sources">
            <BookOpen aria-hidden="true" />{sourcesOpen ? t('chat.hideSources') : t('chat.showSources')}
          </Button>
        ) : null}
        {message.content ? (
          <Button type="button" variant="ghost" size="sm" onClick={copy} data-testid="copy-answer">
            {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}{copied ? t('chat.copied') : t('chat.copy')}
          </Button>
        ) : null}
        {chat.speak && message.content ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => chat.speak?.(message)} data-testid="read-aloud">
            <Volume2 aria-hidden="true" />{t('voice.readAloud')}
          </Button>
        ) : null}
        {failed ? (
          <Button type="button" variant="outline" size="sm" onClick={chat.retry} data-testid="retry-answer">
            <RotateCcw aria-hidden="true" />{message.status === 'data_report' ? t('assistant.dataReport.retryAi') : t('states.retry')}
          </Button>
        ) : null}
        {/* A stopped answer: the same question again, as a new request (the stopped one is settled). */}
        {message.status === 'cancelled' && question ? (
          <Button type="button" variant="outline" size="sm" onClick={() => onAsk(question)} data-testid="ask-again">
            <RotateCcw aria-hidden="true" />{t('chat.askAgain')}
          </Button>
        ) : null}
        {chat.signedIn && message.status && SAVEABLE.has(message.status) ? <SaveResearchButton messageId={message.id} /> : null}
        {chat.signedIn && message.status === 'answered' ? <AnswerReportButton messageId={message.id} /> : null}
        {message.structured.study_id ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => chat.openStudy(message.structured.study_id ?? '')} data-testid="open-study"
            aria-pressed={chat.activeStudyId === message.structured.study_id}>
            {chat.activeStudyId === message.structured.study_id ? t('workspace.study.shown') : t('workspace.study.open')}
          </Button>
        ) : null}
      </div>
      {message.suggestions.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {message.suggestions.map((s) => (
            <button key={s} type="button" onClick={() => onAsk(s)} className="rounded-full border border-border px-3 py-1 text-sm transition-colors hover:border-brand/50 hover:bg-muted motion-reduce:transition-none" dir="auto">{s}</button>
          ))}
        </div>
      ) : null}
    </li>
    </SourcesShown.Provider>
  );
}

function Composer({ chat, onSend, onTools }: { chat: ChatModel; onSend: (text: string) => void; onTools: () => void }) {
  const { t } = useTranslation();
  const cancel = useCancelRequest();
  const maxSeconds = useVoiceStatus().data?.max_seconds ?? 60;
  const box = useRef<HTMLTextAreaElement>(null);
  const sending = useRef(false);
  useEffect(() => {
    if (!chat.pending) sending.current = false;
  }, [chat.pending]);
  // The box grows with the text, up to about eight lines.
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 208)}px`;
  }, [chat.draft]);
  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const text = chat.draft.trim();
    // One submission at a time (a double Enter or tap sends once).
    if (!text || chat.pending || chat.needsAccount || sending.current) return;
    sending.current = true;
    onSend(text);
  };
  const voice = chat.voice;
  const stopping = cancel.isPending || (cancel.isSuccess && chat.pending);
  const override = chat.mode.value !== 'auto' ? chat.mode.value : null;
  if (!chat.canAsk) return null;
  return (
    <form onSubmit={submit} className="mx-auto flex w-full max-w-[52rem] shrink-0 flex-col gap-1.5 pt-2 pb-3" data-testid="chat-composer">
      {chat.selection.value ? (
        <p className="flex flex-wrap items-center gap-2 rounded-xl border border-primary/40 bg-primary/5 px-3 py-1.5 text-sm" data-testid="assistant-selection">
          <span>{t('assistant.selectionApplied', { selection: chat.selection.label ?? `${chat.selection.value.indicator} · ${chat.selection.value.area} · ${chat.selection.value.period_from} – ${chat.selection.value.period_to}` })}</span>
          <button type="button" className="text-primary underline underline-offset-2" onClick={chat.selection.clear} data-testid="assistant-selection-clear">
            {t('assistant.selectionClear')}
          </button>
        </p>
      ) : null}
      {voice.notice ? <p className="text-sm text-destructive" role="alert" data-testid="voice-notice">{t(`voice.notice.${voice.notice}`)}</p> : null}
      {voice.serverMode && voice.listening ? <p className="text-sm font-medium" role="status" data-testid="voice-recording">{t('voice.recording', { seconds: maxSeconds })}</p> : null}
      {voice.transcribing ? (
        <p className="flex items-center gap-1 text-sm" role="status" data-testid="voice-transcribing">
          <Loader2 aria-hidden="true" className="size-3 animate-spin motion-reduce:animate-none" />{t('voice.transcribing')}
        </p>
      ) : null}
      {chat.viaVoice && chat.draft && !voice.listening && !voice.transcribing ? (
        <p className="text-sm text-muted-foreground" role="status" data-testid="voice-review">{t('voice.review')}</p>
      ) : null}
      {voice.speaking ? (
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={voice.stopPlayback} data-testid="voice-stop-speaking">
            <Square aria-hidden="true" />{t('voice.stopSpeaking')}
          </Button>
        </div>
      ) : null}
      <div className="glass-card glass-strong flex flex-col gap-1 rounded-3xl border border-border-strong/60 p-2 shadow-raised transition-shadow focus-within:border-brand/60 focus-within:shadow-[0_0_0_4px_var(--primary-soft)] motion-reduce:transition-none">
        <label htmlFor={chat.inputId} className="sr-only">{t('assistant.question')}</label>
        <textarea id={chat.inputId} ref={box} value={chat.draft} rows={1} dir="auto" enterKeyHint="send"
          onChange={(e) => chat.type(e.target.value.slice(0, chat.max))}
          onKeyDown={(e) => {
            // Enter sends; Shift+Enter is a new line; never mid-composition (input methods).
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={chat.needsAccount ? t('guest.inputLocked') : t('chat.placeholder')} disabled={chat.needsAccount}
          className="max-h-52 min-h-12 w-full resize-none bg-transparent px-3 pt-2 pb-1 text-base outline-none placeholder:text-muted-foreground"
          data-testid="assistant-input" />
        <div className="flex items-center gap-1">
          <Button type="button" variant="ghost" size="sm" className="shrink-0 rounded-full" onClick={onTools} data-testid="chat-tools"
            title={t('chat.tools')} aria-haspopup="dialog">
            <SlidersHorizontal aria-hidden="true" /><span className="max-sm:sr-only">{t('chat.tools')}</span>
          </Button>
          {override ? (
            <span className="flex min-w-0 items-center gap-0.5" data-testid="chat-mode-chip">
              <Badge variant="outline" className="truncate">{t('chat.modeChip', { mode: t(`assistant.mode.${override}`) })}</Badge>
              <button type="button" onClick={() => chat.mode.set('auto')} className="inline-flex items-center rounded-full p-1 hover:bg-muted"
                data-testid="chat-mode-clear" title={t('chat.modeAuto')}>
                <X aria-hidden="true" className="size-3.5" /><span className="sr-only">{t('chat.modeAuto')}</span>
              </button>
            </span>
          ) : null}
          <span className="flex-1" />
          {voice.canListen ? (
            voice.listening || voice.transcribing ? (
              <>
                <Button type="button" size="sm" className="shrink-0 rounded-full" onClick={voice.stop} disabled={voice.transcribing} data-testid="voice-stop">
                  <MicOff aria-hidden="true" /><span className="max-sm:sr-only">{t('voice.stopListening')}</span>
                </Button>
                <Button type="button" variant="ghost" size="sm" className="w-9 shrink-0 rounded-full px-0" onClick={voice.cancel} data-testid="voice-cancel" title={t('voice.cancel')}>
                  <X aria-hidden="true" /><span className="sr-only">{t('voice.cancel')}</span>
                </Button>
              </>
            ) : (
              <Button type="button" variant="ghost" size="sm" className="w-9 shrink-0 rounded-full px-0" onClick={voice.start} disabled={chat.needsAccount}
                data-testid="voice-start" title={t('voice.speak')}>
                <Mic aria-hidden="true" /><span className="sr-only">{t('voice.speak')}</span>
              </Button>
            )
          ) : null}
          {chat.pending ? (
            <Button type="button" size="sm" variant="outline" className="shrink-0 rounded-full" disabled={stopping || !chat.asking?.requestId} data-testid="assistant-stop"
              onClick={() => { if (chat.asking?.requestId) cancel.mutate({ requestId: chat.asking.requestId, guest: chat.guest }); }}>
              <Square aria-hidden="true" className="fill-current" />{stopping ? t('workflow.stopping') : t('workflow.stop')}
            </Button>
          ) : (
            <Button type="submit" size="sm" className="size-9 shrink-0 rounded-full px-0" disabled={!chat.draft.trim() || chat.needsAccount}
              data-testid="assistant-send" title={t('assistant.send')}>
              <ArrowUp aria-hidden="true" /><span className="sr-only">{t('assistant.send')}</span>
            </Button>
          )}
        </div>
      </div>
      <p className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span data-testid="assistant-disclaimer-short">{t('assistant.disclaimerShort')}</span>
        {chat.allowance ? (
          <span data-testid="guest-allowance" data-remaining={chat.allowance.remaining}>
            {t('guest.remaining', { remaining: chat.allowance.remaining, limit: chat.allowance.limit })}
          </span>
        ) : null}
      </p>
    </form>
  );
}

/** Answer language, voice, memory, about and help: out of the conversation. */
function SettingsSheet({ chat }: { chat: ChatModel }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const status = useAssistantStatus();
  const { persona } = usePersona();
  const voice = chat.voice;
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-5 py-4 text-sm" data-testid="chat-settings-sheet">
      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold text-muted-foreground">{t('chat.answers')}</h3>
        <Segmented label={t('assistant.language')} value={chat.language} onChange={(v) => chat.setLanguage(v === 'ar' ? 'ar' : 'en')}
          options={[{ value: 'en', label: 'English' }, { value: 'ar', label: 'العربية' }]} testId="assistant-language" />
        {/* The data the answers from OSRIP's own records use (internet research does not). */}
        <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground" data-testid="chat-data-mode">
          <DataModeBadge mode={chat.dataMode} />
        </p>
      </section>
      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold text-muted-foreground">{t('chat.voice')}</h3>
        {voice.canSpeak ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" size="sm" aria-pressed={voice.muted} onClick={() => voice.setMuted(!voice.muted)} data-testid="voice-mute">
              {voice.muted ? <VolumeX aria-hidden="true" /> : <Volume2 aria-hidden="true" />}{voice.muted ? t('voice.unmute') : t('voice.mute')}
            </Button>
            <VoiceVolume testId="voice-volume-replies" />
          </div>
        ) : null}
        {voice.noVoice || voice.noLanguageVoice ? (
          <p className="text-xs text-muted-foreground" data-testid="talk-no-voice">
            {t('talk.noVoice')}{' '}
            <Link to={to('/settings')} className="font-medium text-primary underline underline-offset-2">{t('talk.howToFix')}</Link>
          </p>
        ) : null}
        {/* What is playing (with Stop for any audio), the recorded welcome when one is supplied,
            and the voice check and test. */}
        <AssistantStatusBar study={null} />
        <IntroPlayer />
        <details className="text-sm" data-testid="voice-details">
          <summary className="flex cursor-pointer items-center gap-1.5 text-xs font-semibold">
            <CircleHelp aria-hidden="true" className="size-3.5" />{t('voicePanel.details')}
          </summary>
          <div className="mt-2"><VoicePanel /></div>
        </details>
      </section>
      <MemoryPanel signedIn={chat.signedIn} guestExpires={chat.memory.guestExpires} guestConversationId={chat.memory.guestConversationId}
        onGuestDeleted={chat.memory.onGuestDeleted} onAllDeleted={chat.memory.onAllDeleted} />
      <AboutMulhim />
      <details className="rounded-md border border-border px-3 py-2 text-sm" data-testid="assistant-help">
        <summary className="flex cursor-pointer items-center gap-1.5 font-semibold">
          <CircleHelp aria-hidden="true" className="size-3.5" />{t('assistant.help.title')}
        </summary>
        <ul className="mt-2 flex list-disc flex-col gap-1 ps-4 text-muted-foreground">
          <li>{t('assistant.disclaimer', { name: persona.name[language] })}</li>
          <li>{t('assistant.help.dataReport')}</li>
          {status.data?.research_cutoff ? (
            <li data-testid="research-cutoff">{t('assistant.cutoff', { date: formatPeriod(status.data.research_cutoff, status.data.research_cutoff, language) })}</li>
          ) : null}
          {status.data && !status.data.configured ? <li>{t('assistant.notConfiguredLookup')}</li> : null}
          {status.data?.configured && !chat.web.available ? <li data-testid="web-unavailable">{t('assistant.webUnavailable')}</li> : null}
          <li>{t('assistant.avatarNote')}</li>
          {voice.canSpeak ? <li>{t('voice.animationNote')}</li> : null}
          <li>{voice.serverMode ? t('voice.serverDisclosure') : voice.canListen ? t('voice.disclosure') : t('voice.unsupported')}</li>
        </ul>
      </details>
      <Link to={to('/settings')} className="w-fit text-xs font-medium text-primary underline underline-offset-2" data-testid="chat-help-settings">
        {t('chat.moreHelp')}
      </Link>
    </div>
  );
}

/** Optional: an answer mode instead of automatic, web search, a research brief, page tools. */
function ToolsSheet({ chat, onClose, onBriefUsed }: { chat: ChatModel; onClose: () => void; onBriefUsed: () => void }) {
  const { t } = useTranslation();
  // Automatic; then the internet modes; then the modes that work from OSRIP's data.
  const groups: { key: 'auto' | 'web' | 'data'; modes: readonly RequestMode[] }[] = [
    { key: 'auto', modes: ['auto'] },
    { key: 'web', modes: INTERNET_MODES },
    { key: 'data', modes: DATA_MODES },
  ];
  const chip = (mode: RequestMode) => (
    <button key={mode} type="button" role="radio" aria-checked={chat.mode.value === mode} data-value={mode}
      onClick={() => chat.mode.set(mode)}
      className={cn('min-h-9 rounded-full border px-3 py-1 text-xs font-medium transition-colors motion-reduce:transition-none',
        chat.mode.value === mode ? 'border-primary bg-primary text-primary-foreground' : 'border-border-strong/60 hover:bg-muted')}>
      {mode === 'auto' ? t('chat.modeAuto') : t(`assistant.mode.${mode}`)}
    </button>
  );
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-5 py-4 text-sm" data-testid="chat-tools-sheet">
      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold text-muted-foreground">{t('chat.modeHeading')}</h3>
        <div role="radiogroup" aria-label={t('assistant.mode.label')} data-testid="assistant-mode" className="flex flex-col gap-2">
          {groups.map((group) => (
            <div key={group.key} role={group.key === 'auto' ? undefined : 'group'} data-group={group.key}
              aria-label={group.key === 'auto' ? undefined : t(`assistant.mode.group.${group.key}`)} className="flex flex-wrap items-center gap-1.5">
              {group.key === 'auto' ? null : (
                <span aria-hidden="true" className="w-full text-[11px] font-medium text-muted-foreground">{t(`assistant.mode.group.${group.key}`)}</span>
              )}
              {group.modes.map(chip)}
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground" data-testid="assistant-mode-hint">
          {chat.mode.value === 'auto' ? t('chat.modeAutoHint') : t(`assistant.modeHint.${chat.mode.value}`)}
        </p>
        {isInternetMode(chat.mode.value) && !chat.web.available ? (
          <p className="text-xs text-destructive" role="status" data-testid="research-unavailable">{t('assistant.researchNeedsSearch')}</p>
        ) : null}
      </section>
      {chat.web.available ? (
        <section className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-sm font-medium" title={t('assistant.webToggleHint')}>
            <input type="checkbox" checked={chat.web.on} className="size-4 accent-primary" data-testid="web-toggle"
              onChange={(e) => chat.web.set(e.target.checked)} />
            {t('assistant.webToggle')}
          </label>
          <p className="text-xs text-muted-foreground">{t('assistant.webToggleHint')}</p>
          {chat.crossCheck.available ? (
            <div className="text-xs">
              <label className="flex items-center gap-2 font-medium">
                <input type="checkbox" checked={chat.crossCheck.on} onChange={(e) => chat.crossCheck.set(e.target.checked)}
                  className="size-4 accent-primary" data-testid="cross-check-toggle" />
                {t('assistant.crossCheck')}
              </label>
              <p className="ms-6 text-muted-foreground">{t('assistant.crossCheckHint')}</p>
            </div>
          ) : null}
        </section>
      ) : null}
      {/* Filling the brief puts the request in the message box for review; nothing is sent. */}
      <div onClickCapture={(e) => { if ((e.target as HTMLElement).closest('[data-testid="research-brief-use"]')) window.setTimeout(onBriefUsed, 0); }}>
        {chat.brief}
      </div>
      {/* A page tool (analysis, a full study) opens on its own: this drawer closes first. */}
      <div onClickCapture={(e) => { if ((e.target as HTMLElement).closest('[data-close-tools]')) onClose(); }}>
        {chat.tools}
      </div>
    </div>
  );
}
