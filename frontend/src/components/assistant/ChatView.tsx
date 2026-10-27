import {
  ArrowDown, Check, CircleHelp, Copy, Loader2, MessageSquarePlus, Mic, MicOff, RotateCcw, Send, Settings2, SlidersHorizontal,
  Sparkles, Square, Trash2, Volume2, VolumeX, X,
} from 'lucide-react';
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useAssistantUi } from './AssistantContext';
import { AssistantAvatar } from './AssistantAvatar';
import { ServiceChip } from './AssistantIdentityCard';
import { AssistantStatusBar } from './AssistantStatusBar';
import type { ChatVoice } from './AssistantPanel';
import {
  EvidenceItem, GroundedContext, pick, SAVEABLE, SaveResearchButton, SearchLog, STATUS_BADGE, WebEvidenceItem,
} from './Evidence';
import { AnswerReportButton } from './AnswerReportButton';
import { ChatDataCharts, ChatDataTables, ResearchSummary } from './ChatData';
import { asksForChart, chartPoints, InlineChart } from './InlineChart';
import { IntroPlayer } from './IntroPlayer';
import { Markdown } from './Markdown';
import { AboutMulhim, MemoryPanel } from './MulhimPanels';
import { PersonaSwitch, usePersona } from './persona';
import { PersonaImage } from './PersonaImage';
import { CitationChip, DataReportNotice, evidenceAnchor, StructuredParts, WebNotice } from './StructuredReply';
import { VoicePanel } from './VoicePanel';
import { VoiceVolume } from './VoiceVolume';
import {
  ASSISTANT_MODES, PROGRESS_STAGES, useAssistantStatus, useCancelRequest, useRequestProgress, useVoiceStatus,
  type Allowance, type AskSelection, type AssistantMessage, type ConversationSummary, type Evidence, type RequestMode,
} from '@/api/assistant';
import { ApiRequestError } from '@/api/client';
import type { DataMode } from '@/domain/types';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import { formatDecimal, formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/** Everything the conversation page needs from the chat's state (AssistantChat owns it). */
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
  conversations: { list: ConversationSummary[]; activeId: string | null; select: (id: string | null) => void; remove: () => void; removing: boolean } | null;
  newConversation: () => void;
  linkPrompt: ReactNode;
  memory: { guestExpires: string | null; guestConversationId: string | null; onGuestDeleted: () => void; onAllDeleted: () => void };
  selection: { value: AskSelection | null; label?: string; clear: () => void };
  brief: ReactNode;
  openStudy: (id: string) => void;
  activeStudyId: string | null;
  suggestions: string[];
  /** Page-specific tools (shortage and surplus analysis, a full study), in the tools drawer. */
  tools?: ReactNode;
}

const NEAR_BOTTOM = 96; // px: closer than this to the end counts as reading the latest message

/**
 * The AI Assistant page: one conversation, centred and at most 800px wide. A compact header
 * (portrait, name, honest service status, Al Mulhim / Ilham, New conversation, Settings), the
 * messages in one scrolling area, and one message box at the bottom with Send, Speak and an
 * optional Tools drawer. Before the first message only a welcome and up to three examples are
 * shown. Explanations, voice and conversation settings, research modes, the research brief and
 * the analysis forms are in the Settings and Tools drawers, not in the conversation.
 */
export function ChatView({ chat }: { chat: ChatModel }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const ui = useAssistantUi();
  const { persona } = usePersona();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);

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
  const started = chat.messages.length > 0 || Boolean(echo) || chat.pending;

  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="assistant-panel" data-variant="chat" lang={chat.language}>
      <header className="mx-auto flex w-full max-w-[800px] shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-border pb-2" data-testid="chat-header">
        <AssistantAvatar state={ui.state} size="2.25rem" decorative={false} />
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
          <h1 className="text-base font-semibold" data-testid="mulhim-name" data-persona={persona.code}>{persona.name[language]}</h1>
          <ServiceChip />
        </div>
        {/* Phones: the choice gets its own row under the name. */}
        <div className="max-sm:order-last max-sm:flex max-sm:w-full max-sm:justify-center"><PersonaSwitch /></div>
        <div className="flex items-center gap-1">
          <Button type="button" variant="ghost" size="sm" onClick={() => { chat.newConversation(); toEnd(); }} data-testid="chat-new"
            title={t('chat.newConversation')}>
            <MessageSquarePlus aria-hidden="true" /><span className="max-sm:sr-only">{t('chat.newConversation')}</span>
          </Button>
          <Button type="button" variant="ghost" size="sm" className="w-8 px-0" onClick={() => setSettingsOpen(true)} data-testid="chat-settings"
            title={t('chat.settings')} aria-haspopup="dialog">
            <Settings2 aria-hidden="true" /><span className="sr-only">{t('chat.settings')}</span>
          </Button>
        </div>
      </header>

      <div className="relative min-h-0 flex-1">
        <div ref={scroller} onScroll={onScroll} className="h-full overflow-y-auto" data-testid="assistant-messages" aria-live="polite">
          <div className="mx-auto flex w-full max-w-[800px] flex-col gap-6 px-1 py-5">
            {!started && chat.canAsk && !chat.needsAccount ? (
              <section className="flex flex-col items-center gap-4 py-10 text-center" data-testid="chat-welcome">
                <p className="text-2xl font-semibold" data-testid="chat-greeting">{t('chat.welcome')}</p>
                {chat.suggestions.length ? (
                  <ul className="flex w-full max-w-xl flex-col gap-2" data-testid="suggestions">
                    {chat.suggestions.slice(0, 3).map((s) => (
                      <li key={s}>
                        <button type="button" onClick={() => send(s)} dir="auto" data-testid="suggestion"
                          className="w-full rounded-xl border border-border px-4 py-2.5 text-start text-sm transition-colors hover:bg-muted motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-ring">
                          {s}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>
            ) : null}
            {chat.linkPrompt}
            <ol className="flex flex-col gap-6">
              {chat.messages.map((m, i) => (
                <ChatMessage key={m.id} message={m} question={i > 0 ? chat.messages[i - 1]?.content : undefined}
                  chat={chat} onAsk={send} />
              ))}
              {echo ? (
                <li className="ms-auto max-w-[85%] rounded-2xl bg-muted px-4 py-2 text-sm whitespace-pre-wrap" dir="auto"
                  data-testid="user-message" data-pending="true">{echo.text}</li>
              ) : null}
              {chat.pending ? <Thinking requestId={chat.asking?.requestId ?? null} guest={chat.guest} /> : null}
            </ol>
            {chat.needsAccount ? chat.signInPrompt : null}
            {chat.error ? (
              <div role="alert" className="flex flex-wrap items-center gap-2 text-sm text-destructive" data-testid="assistant-error">
                <p>{chat.error instanceof ApiRequestError && chat.error.code === 'network_unavailable' ? t('chat.errorNetwork') : chat.error.message}</p>
                <Button variant="outline" size="sm" onClick={chat.retry} data-testid="error-retry"><RotateCcw aria-hidden="true" />{t('states.retry')}</Button>
              </div>
            ) : null}
          </div>
        </div>
        {unseen ? (
          <button type="button" onClick={toEnd} data-testid="chat-new-messages"
            className="absolute inset-x-0 bottom-3 mx-auto flex w-fit items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium shadow-raised hover:bg-muted">
            <ArrowDown aria-hidden="true" className="size-3.5" />{t('chat.newMessages')}
          </button>
        ) : null}
      </div>

      <Composer chat={chat} onSend={send} onTools={() => setToolsOpen(true)} />

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

/** While a question is answered: the latest real stage from the server (no simulated typing). */
function Thinking({ requestId, guest }: { requestId: string | null; guest: boolean }) {
  const { t } = useTranslation();
  const progress = useRequestProgress(requestId, guest);
  const stages = (progress.data?.stages ?? []).map((s) => s.stage)
    .filter((s): s is (typeof PROGRESS_STAGES)[number] => (PROGRESS_STAGES as readonly string[]).includes(s));
  const stage = stages[stages.length - 1];
  return (
    <li className="flex items-center gap-2 text-sm text-muted-foreground" role="status" data-testid="assistant-loading" data-stage={stage ?? ''}>
      <Loader2 aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" />
      {stage && stage !== 'received' ? t(`workflow.stage.${stage}`) : t('workflow.working')}
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
  if (message.role === 'user') {
    return (
      <li className="ms-auto max-w-[85%] rounded-2xl bg-muted px-4 py-2 text-sm whitespace-pre-wrap" dir="auto" data-testid="user-message">
        {message.content}
      </li>
    );
  }
  const author = byCode(message.persona);
  const badge = message.status ? STATUS_BADGE[message.status] : null;
  const searches = message.evidence.filter((e) => e.kind === 'search');
  const evidence = message.evidence.filter((e) => e.kind !== 'search');
  const byId = new Map(evidence.map((e) => [e.id, e]));
  const shown = message.citations.length ? message.citations.map((c) => byId.get(c)).filter((e): e is Evidence => Boolean(e)) : evidence;
  const known = new Set([...shown.map((e) => e.id), ...message.calculations.map((c) => c.id)]);
  const anchor = (id: string) => evidenceAnchor(message.id, id);
  const failed = message.status === 'unavailable' || message.status === 'data_report';
  // A chart only when this question asked for one, from the cited published values.
  const wantsChart = asksForChart(question) && message.status !== 'clarification';
  // The server's chart of the table's own rows when it built one; otherwise the cited values.
  const dataCharts = wantsChart ? message.structured.data_charts ?? [] : [];
  const points = wantsChart && !dataCharts.length ? chartPoints(shown) : null;
  const sourceNames = [...new Set(shown.map((e) => e.source?.title ?? (typeof e.title === 'string' ? e.title : pick(e.title, language))).filter(Boolean))];
  const copy = () => {
    const text = [message.content, ...(sourceNames.length ? ['', `${t('assistant.sources')}: ${sourceNames.join(' · ')}`] : [])].join('\n');
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <li className="flex flex-col gap-2 text-[0.95rem] leading-relaxed" data-testid="assistant-message" data-status={message.status ?? ''}
      data-persona={author.code}>
      <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5 font-semibold text-foreground" data-testid="message-persona">
          <PersonaImage src={author.avatar.portrait} alt="" width={20} height={20} className="size-5 rounded-full object-cover object-top" draggable={false} />
          {author.name[language]}
        </span>
        {message.ai_generated ? (
          <span className="inline-flex items-center gap-1" data-testid="ai-label"><Sparkles aria-hidden="true" className="size-3" />{t('assistant.aiLabel')}</span>
        ) : (
          <span data-testid="non-ai-label">
            {message.status === 'lookup' ? t('assistant.lookupLabel') : message.status === 'profile' ? t('assistant.profileLabel')
              : message.status === 'data_report' ? t('assistant.dataReportLabel') : t('assistant.systemLabel')}
          </span>
        )}
        {badge ? <Badge variant="sand">{t(badge)}</Badge> : null}
        {/* Which kind of answer was given (chosen automatically unless picked in Tools). */}
        {message.mode && message.mode !== 'ask' ? <Badge variant="outline" data-testid="reply-mode">{t(`assistant.mode.${message.mode}`)}</Badge> : null}
      </p>
      <div className="flex flex-col gap-3" data-testid="assistant-text">
        <Markdown text={message.content} cite={(id) => <CitationChip messageId={message.id} id={id} known={known.has(id)} />} />
      </div>
      {message.structured.data_tables?.length ? <ChatDataTables blocks={message.structured.data_tables} messageId={message.id} /> : null}
      {dataCharts.length ? <ChatDataCharts charts={dataCharts} messageId={message.id} /> : null}
      {dataCharts.length ? null : points ? <InlineChart points={points} messageId={message.id} /> : wantsChart && message.status === 'answered' ? (
        <p className="text-xs text-muted-foreground" data-testid="chart-unavailable">{t('chat.chartUnavailable')}</p>
      ) : null}
      {message.structured.research ? <ResearchSummary summary={message.structured.research} /> : null}
      {message.structured.data_report ? <DataReportNotice report={message.structured.data_report} /> : null}
      {message.structured.web_notice ? <WebNotice notice={message.structured.web_notice} /> : null}
      {message.structured && Object.keys(message.structured).length ? (
        <StructuredParts structured={message.structured} messageId={message.id} known={known} />
      ) : null}
      <SearchLog items={searches} />
      {message.structured.grounded_context?.length ? <GroundedContext entries={message.structured.grounded_context} /> : null}
      {shown.length > 0 ? (
        <details className="group text-xs" data-testid="chat-sources" open={message.status === 'unverified'}>
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
        <details className="text-xs" data-testid="how-calculated">
          <summary className="cursor-pointer font-semibold text-muted-foreground hover:text-foreground">{t('assistant.howCalculated')}</summary>
          <ul className="mt-2 flex flex-col gap-2">
            {message.calculations.map((c) => (
              <li key={c.id} id={anchor(c.id)} tabIndex={-1} className="scroll-mt-4 focus-visible:outline-2">
                <p className="font-mono">[{c.id}] {c.calculation}</p>
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
      <div className="flex flex-wrap items-center gap-1 text-xs" data-testid="message-actions">
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
        {chat.signedIn && message.status && SAVEABLE.has(message.status) ? <SaveResearchButton messageId={message.id} /> : null}
        {chat.signedIn && message.status === 'answered' ? <AnswerReportButton messageId={message.id} /> : null}
        {message.structured.study_id ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => chat.openStudy(message.structured.study_id ?? '')} data-testid="open-study">
            {chat.activeStudyId === message.structured.study_id ? t('workspace.study.shown') : t('workspace.study.open')}
          </Button>
        ) : null}
      </div>
      {message.suggestions.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {message.suggestions.map((s) => (
            <button key={s} type="button" onClick={() => onAsk(s)} className="rounded-full border border-border px-2.5 py-1 text-xs hover:bg-muted" dir="auto">{s}</button>
          ))}
        </div>
      ) : null}
    </li>
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
  // The box grows with the text, up to about six lines.
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
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
    <form onSubmit={submit} className="mx-auto flex w-full max-w-[800px] shrink-0 flex-col gap-1.5 pt-2 pb-3" data-testid="chat-composer">
      {chat.selection.value ? (
        <p className="flex flex-wrap items-center gap-2 rounded-md border border-primary/40 bg-primary/5 px-2 py-1 text-xs" data-testid="assistant-selection">
          <span>{t('assistant.selectionApplied', { selection: chat.selection.label ?? `${chat.selection.value.indicator} · ${chat.selection.value.area} · ${chat.selection.value.period_from} – ${chat.selection.value.period_to}` })}</span>
          <button type="button" className="text-primary underline underline-offset-2" onClick={chat.selection.clear} data-testid="assistant-selection-clear">
            {t('assistant.selectionClear')}
          </button>
        </p>
      ) : null}
      {override ? (
        <p className="flex items-center gap-1.5 text-xs" data-testid="chat-mode-chip">
          <Badge variant="outline">{t('chat.modeChip', { mode: t(`assistant.mode.${override}`) })}</Badge>
          <button type="button" onClick={() => chat.mode.set('auto')} className="inline-flex items-center rounded p-0.5 hover:bg-muted"
            data-testid="chat-mode-clear" title={t('chat.modeAuto')}>
            <X aria-hidden="true" className="size-3.5" /><span className="sr-only">{t('chat.modeAuto')}</span>
          </button>
        </p>
      ) : null}
      {voice.notice ? <p className="text-xs text-destructive" role="alert" data-testid="voice-notice">{t(`voice.notice.${voice.notice}`)}</p> : null}
      {voice.serverMode && voice.listening ? <p className="text-xs font-medium" role="status" data-testid="voice-recording">{t('voice.recording', { seconds: maxSeconds })}</p> : null}
      {voice.transcribing ? (
        <p className="flex items-center gap-1 text-xs" role="status" data-testid="voice-transcribing">
          <Loader2 aria-hidden="true" className="size-3 animate-spin motion-reduce:animate-none" />{t('voice.transcribing')}
        </p>
      ) : null}
      {chat.viaVoice && chat.draft && !voice.listening && !voice.transcribing ? (
        <p className="text-xs text-muted-foreground" role="status" data-testid="voice-review">{t('voice.review')}</p>
      ) : null}
      {voice.speaking ? (
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={voice.stopPlayback} data-testid="voice-stop-speaking">
            <Square aria-hidden="true" />{t('voice.stopSpeaking')}
          </Button>
        </div>
      ) : null}
      <div className="flex items-end gap-1 rounded-2xl border border-border-strong/60 bg-card px-2 py-1.5 shadow-card focus-within:border-primary">
        <Button type="button" variant="ghost" size="sm" className="w-9 shrink-0 px-0" onClick={onTools} data-testid="chat-tools"
          title={t('chat.tools')} aria-haspopup="dialog">
          <SlidersHorizontal aria-hidden="true" /><span className="sr-only">{t('chat.tools')}</span>
        </Button>
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
          className="max-h-42 min-h-9 flex-1 resize-none bg-transparent px-1 py-1.5 text-[0.95rem] outline-none placeholder:text-muted-foreground"
          data-testid="assistant-input" />
        {voice.canListen ? (
          voice.listening || voice.transcribing ? (
            <>
              <Button type="button" size="sm" className="shrink-0" onClick={voice.stop} disabled={voice.transcribing} data-testid="voice-stop">
                <MicOff aria-hidden="true" /><span className="max-sm:sr-only">{t('voice.stopListening')}</span>
              </Button>
              <Button type="button" variant="ghost" size="sm" className="w-9 shrink-0 px-0" onClick={voice.cancel} data-testid="voice-cancel" title={t('voice.cancel')}>
                <X aria-hidden="true" /><span className="sr-only">{t('voice.cancel')}</span>
              </Button>
            </>
          ) : (
            <Button type="button" variant="ghost" size="sm" className="w-9 shrink-0 px-0" onClick={voice.start} disabled={chat.needsAccount}
              data-testid="voice-start" title={t('voice.speak')}>
              <Mic aria-hidden="true" /><span className="sr-only">{t('voice.speak')}</span>
            </Button>
          )
        ) : null}
        {chat.pending ? (
          <Button type="button" size="sm" variant="outline" className="shrink-0" disabled={stopping || !chat.asking?.requestId} data-testid="assistant-stop"
            onClick={() => { if (chat.asking?.requestId) cancel.mutate({ requestId: chat.asking.requestId, guest: chat.guest }); }}>
            <Square aria-hidden="true" />{stopping ? t('workflow.stopping') : t('workflow.stop')}
          </Button>
        ) : (
          <Button type="submit" size="sm" className="shrink-0" disabled={!chat.draft.trim() || chat.needsAccount} data-testid="assistant-send">
            <Send aria-hidden="true" className="rtl:-scale-x-100" /><span className="max-sm:sr-only">{t('assistant.send')}</span>
          </Button>
        )}
      </div>
      <p className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-[0.7rem] text-muted-foreground">
        <DataModeBadge mode={chat.dataMode} />
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

/** Answer language, voice, conversations, memory, about and help: out of the conversation. */
function SettingsSheet({ chat }: { chat: ChatModel }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const status = useAssistantStatus();
  const { persona } = usePersona();
  const voice = chat.voice;
  const [confirmDelete, setConfirmDelete] = useState(false);
  const conv = chat.conversations;
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-5 py-4 text-sm" data-testid="chat-settings-sheet">
      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold text-muted-foreground">{t('chat.answers')}</h3>
        <Segmented label={t('assistant.language')} value={chat.language} onChange={(v) => chat.setLanguage(v === 'ar' ? 'ar' : 'en')}
          options={[{ value: 'en', label: 'English' }, { value: 'ar', label: 'العربية' }]} testId="assistant-language" />
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
        <Link to={to('/talk')} data-testid="open-talk" className="inline-flex w-fit items-center gap-1.5 text-primary underline underline-offset-2">
          <Mic aria-hidden="true" className="size-3.5" />{t('talk.open', { name: persona.name[language] })}
        </Link>
        {/* What is playing (with Stop for any audio), the recorded welcome when one is supplied,
            and the persona's voice check and test. */}
        <AssistantStatusBar study={null} />
        <IntroPlayer />
        <details className="text-sm" data-testid="voice-details">
          <summary className="flex cursor-pointer items-center gap-1.5 text-xs font-semibold">
            <CircleHelp aria-hidden="true" className="size-3.5" />{t('voicePanel.details')}
          </summary>
          <div className="mt-2"><VoicePanel showPicker={false} /></div>
        </details>
      </section>
      {conv ? (
        <section className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold text-muted-foreground">{t('assistant.conversation')}</h3>
          <div className="flex flex-wrap items-end gap-2">
            <SelectField className="min-w-0 flex-1" label={t('assistant.conversation')} value={conv.activeId ?? ''}
              onValueChange={(v) => { conv.select(v || null); setConfirmDelete(false); }}
              options={[{ value: '', label: t('assistant.newConversation') }, ...conv.list.map((c) => ({ value: c.id, label: c.title }))]}
              data-testid="conversation-select" />
            {conv.activeId ? (
              <Button variant={confirmDelete ? 'default' : 'ghost'} size="sm" data-testid="delete-conversation" disabled={conv.removing}
                onClick={() => {
                  if (!confirmDelete) { setConfirmDelete(true); return; }
                  conv.remove();
                  setConfirmDelete(false);
                }}>
                <Trash2 aria-hidden="true" />{confirmDelete ? t('assistant.confirmDelete') : t('assistant.delete')}
              </Button>
            ) : null}
          </div>
        </section>
      ) : null}
      <MemoryPanel signedIn={chat.signedIn} guestExpires={chat.memory.guestExpires} guestConversationId={chat.memory.guestConversationId}
        onGuestDeleted={chat.memory.onGuestDeleted} onAllDeleted={chat.memory.onAllDeleted} />
      <AboutMulhim />
      <details className="rounded-md border border-border px-3 py-2 text-xs" data-testid="assistant-help">
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
  const modes: RequestMode[] = ['auto', ...ASSISTANT_MODES];
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-5 py-4 text-sm" data-testid="chat-tools-sheet">
      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold text-muted-foreground">{t('chat.modeHeading')}</h3>
        <div role="radiogroup" aria-label={t('assistant.mode.label')} data-testid="assistant-mode" className="flex flex-wrap gap-1.5">
          {modes.map((mode) => (
            <button key={mode} type="button" role="radio" aria-checked={chat.mode.value === mode} data-value={mode}
              onClick={() => chat.mode.set(mode)}
              className={cn('min-h-9 rounded-full border px-3 py-1 text-xs font-medium transition-colors motion-reduce:transition-none',
                chat.mode.value === mode ? 'border-primary bg-primary text-primary-foreground' : 'border-border-strong/60 hover:bg-muted')}>
              {mode === 'auto' ? t('chat.modeAuto') : t(`assistant.mode.${mode}`)}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground" data-testid="assistant-mode-hint">
          {chat.mode.value === 'auto' ? t('chat.modeAutoHint') : t(`assistant.modeHint.${chat.mode.value}`)}
        </p>
        {chat.mode.value === 'research' && !chat.web.available ? (
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
