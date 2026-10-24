import {
  BookOpenCheck,
  Calculator,
  CircleHelp,
  Globe,
  Loader2,
  MessageSquarePlus,
  Mic,
  MicOff,
  Pause,
  Play,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  Trash2,
  Volume2,
  VolumeX,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useAssistantUi } from './AssistantContext';
import { ChatView } from './ChatView';
import { AssistantAvatar, ORB_STATE_KEY } from './AssistantAvatar';
import {
  EvidenceItem, GroundedContext, pick, SAVEABLE, SaveResearchButton, SearchLog, STATUS_BADGE, WebEvidenceItem,
} from './Evidence';
import { AboutMulhim, MemoryPanel } from './MulhimPanels';
import { PersonaPicker, usePersona } from './persona';
import { PersonaImage } from './PersonaImage';
import { ResearchBriefBuilder } from './ResearchBriefBuilder';
import { ResearchProgress } from './ResearchProgress';
import { CitedText, DataReportNotice, evidenceAnchor, ModeSelector, StructuredParts, WebNotice } from './StructuredReply';
import { VoiceVolume } from './VoiceVolume';
import {
  ASSISTANT_MODES,
  speakMessage,
  transcribe,
  useAsk,
  useAssistantStatus,
  useConversation,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useGuestAsk,
  useGuestConversation,
  useGuestStatus,
  useLinkGuestHistory,
  useVoiceStatus,
  type Allowance,
  type AssistantMessage,
  type AssistantMode,
  type Evidence,
  type RequestMode,
  type AskSelection,
} from '@/api/assistant';
import { hasPermission, useMe, useProviders } from '@/api/auth';
import { ApiRequestError } from '@/api/client';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import { formatDecimal, formatPeriod } from '@/lib/format';
import { recordingSupported, startRecording, type Recording, type RecorderError } from '@/lib/recorder';
import {
  createRecognizer,
  noVoiceForLanguage,
  noVoiceOfGender,
  onVoicesChanged,
  PERMISSION_ERRORS,
  recognitionSupported,
  speak,
  stopSpeaking,
  voiceFor,
  type PersonaGender,
  type Recognizer,
} from '@/lib/speech';
import { playAudio, type Playback } from '@/lib/voicePlayer';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';


// Kept across sign-in (same tab): the unsent draft and the guest conversation.
const DRAFT_KEY = 'osrip.assistant.draft';
const GUEST_CONVERSATION_KEY = 'osrip.assistant.guestConversation';
const MUTE_KEY = 'osrip.assistant.muted';
const WEB_KEY = 'osrip.assistant.web';
const MODE_KEY = 'osrip.assistant.mode';

/** The avatar reads the playing audio's loudness from this CSS variable (0-1). */
function setVoiceLevel(level: number): void {
  document.documentElement.style.setProperty('--assistant-voice', level.toFixed(3));
}

function readStore(storage: 'session' | 'local', key: string): string | null {
  try {
    return (storage === 'session' ? window.sessionStorage : window.localStorage).getItem(key);
  } catch {
    return null;
  }
}

function writeStore(storage: 'session' | 'local', key: string, value: string | null): void {
  try {
    const store = storage === 'session' ? window.sessionStorage : window.localStorage;
    if (value === null) store.removeItem(key);
    else store.setItem(key, value);
  } catch {
    // Storage can be unavailable (private mode); the chat still works without it.
  }
}

/** A random idempotency key. randomUUID needs a secure context; plain-HTTP LAN tests fall back. */
function newRequestId(): string {
  const source = globalThis.crypto as { randomUUID?: () => string; getRandomValues: Crypto['getRandomValues'] };
  if (typeof source.randomUUID === 'function') return source.randomUUID();
  const bytes = source.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function MessageView({ message, onAsk, onRetry, onSpeak, canSave, onOpenStudy, activeStudyId }: {
  message: AssistantMessage;
  onAsk: (q: string) => void;
  onRetry: () => void;
  onSpeak: ((message: AssistantMessage) => void) | null;
  canSave: boolean;
  onOpenStudy: (id: string) => void;
  activeStudyId: string | null;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { byCode } = usePersona();
  if (message.role === 'user') {
    return (
      <li className="ms-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground" dir="auto" data-testid="user-message">
        {message.content}
      </li>
    );
  }
  // Who gave this reply (a conversation may switch persona; replies keep their author).
  const author = byCode(message.persona);
  const badge = message.status ? STATUS_BADGE[message.status] : null;
  const searches = message.evidence.filter((e) => e.kind === 'search');
  const evidence = message.evidence.filter((e) => e.kind !== 'search');
  const byId = new Map(evidence.map((e) => [e.id, e]));
  const shown = message.citations.length ? message.citations.map((c) => byId.get(c)).filter((e): e is Evidence => Boolean(e)) : evidence;
  const hasWeb = shown.some((e) => e.kind === 'web');
  // Chips link only to evidence listed below this reply (or to its calculations).
  const known = new Set([...shown.map((e) => e.id), ...message.calculations.map((c) => c.id)]);
  const anchor = (id: string) => evidenceAnchor(message.id, id);
  return (
    <li className="me-auto flex max-w-[95%] flex-col gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm"
      data-testid="assistant-message" data-status={message.status ?? ''} data-persona={author.code}>
      <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1 font-semibold text-foreground" data-testid="message-persona">
          <PersonaImage src={author.avatar.portrait} alt="" width={20} height={20} className="size-5 rounded-full object-cover object-top" draggable={false} />
          {author.name[language]}
        </span>
        {message.ai_generated ? (
          <Badge variant="accent" data-testid="ai-label"><Sparkles aria-hidden="true" />{t('assistant.aiLabel')}</Badge>
        ) : <Badge variant="muted" data-testid="non-ai-label">
          {message.status === 'lookup' ? t('assistant.lookupLabel') : message.status === 'profile' ? t('assistant.profileLabel')
            : message.status === 'data_report' ? t('assistant.dataReportLabel') : t('assistant.systemLabel')}
        </Badge>}
        {badge ? <Badge variant="sand">{t(badge)}</Badge> : null}
        {message.mode && message.mode !== 'ask' ? <Badge variant="outline" data-testid="reply-mode">{t(`assistant.mode.${message.mode}`)}</Badge> : null}
        {onSpeak && message.content ? (
          <button type="button" onClick={() => onSpeak(message)} className="ms-auto inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-muted"
            data-testid="read-aloud">
            <Volume2 aria-hidden="true" className="size-3.5" />{t('voice.readAloud')}
          </button>
        ) : null}
      </p>
      <p className="whitespace-pre-wrap" dir="auto" data-testid="assistant-text">
        <CitedText text={message.content} messageId={message.id} known={known} />
      </p>
      {message.structured.data_report ? <DataReportNotice report={message.structured.data_report} /> : null}
      {message.structured.web_notice ? <WebNotice notice={message.structured.web_notice} /> : null}
      {message.status === 'unavailable' || message.status === 'data_report' ? (
        <Button variant="outline" size="sm" className="w-fit" onClick={onRetry} data-testid="retry-answer">
          <RotateCcw aria-hidden="true" />{message.status === 'data_report' ? t('assistant.dataReport.retryAi') : t('states.retry')}
        </Button>
      ) : null}
      {message.structured && Object.keys(message.structured).length ? (
        <StructuredParts structured={message.structured} messageId={message.id} known={known} />
      ) : null}
      <SearchLog items={searches} />
      {shown.length > 0 ? (
        <div>
          <p className="mb-1 text-xs font-semibold">
            {message.status === 'unverified' ? t('assistant.retrievedEvidence') : message.status === 'lookup' || message.status === 'data_report' ? t('assistant.records') : t('assistant.sources')}
          </p>
          <ul className="flex flex-col gap-1.5">
            {shown.map((e) => (e.kind === 'web'
              ? <WebEvidenceItem key={e.id} item={e} anchor={anchor(e.id)} />
              : <EvidenceItem key={e.id} item={e} anchor={anchor(e.id)} />))}
          </ul>
          {hasWeb ? <p className="mt-1.5 flex items-start gap-1 text-xs text-muted-foreground"><Globe aria-hidden="true" className="mt-0.5 size-3 shrink-0" />{t('web.reviewNote')}</p> : null}
        </div>
      ) : null}
      {message.structured.grounded_context?.length ? <GroundedContext entries={message.structured.grounded_context} /> : null}
      {message.calculations.length > 0 ? (
        <details className="rounded-md border border-border p-2 text-xs" data-testid="how-calculated">
          <summary className="flex cursor-pointer items-center gap-1 font-semibold"><Calculator aria-hidden="true" className="size-3.5" />{t('assistant.howCalculated')}</summary>
          <ul className="mt-2 flex flex-col gap-2">
            {message.calculations.map((c) => (
              <li key={c.id} id={anchor(c.id)} tabIndex={-1} className="scroll-mt-4 focus-visible:outline-2">
                <p className="font-mono">[{c.id}] {c.calculation}</p>
                <p>{pick(c.formula, language)}</p>
                {c.inputs?.length ? <p className="text-muted-foreground">{t('assistant.inputs')}: {c.inputs.map((i) => `[${i}]`).join(' ')}</p> : null}
                {c.value != null ? (
                  <p>{t('analysis.result')}: <span className="tabular-nums" dir="ltr">{formatDecimal(c.value, language, 4)}</span> {c.unit === 'percent' ? '%' : c.unit}</p>
                ) : c.reason ? <p className="text-muted-foreground">{pick(c.reason, language)}</p> : null}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-muted-foreground">{t('assistant.calculatedByPlatform')}</p>
        </details>
      ) : null}
      {canSave && message.status && SAVEABLE.has(message.status) ? <SaveResearchButton messageId={message.id} /> : null}
      {message.structured.study_id ? (
        <button type="button" onClick={() => onOpenStudy(message.structured.study_id ?? '')} data-testid="open-study"
          aria-pressed={activeStudyId === message.structured.study_id}
          className="inline-flex w-fit items-center gap-1 rounded-md border border-border-strong/50 px-2.5 py-1 text-xs font-medium hover:bg-muted aria-pressed:border-primary aria-pressed:bg-primary/5">
          <BookOpenCheck aria-hidden="true" className="size-3.5" />
          {activeStudyId === message.structured.study_id ? t('workspace.study.shown') : t('workspace.study.open')}
        </button>
      ) : null}
      {message.suggestions.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {message.suggestions.map((s) => (
            <button key={s} type="button" onClick={() => onAsk(s)} className="rounded-full border border-border-strong/50 px-2.5 py-1 text-xs hover:bg-muted" dir="auto">{s}</button>
          ))}
        </div>
      ) : null}
    </li>
  );
}

// ------------------------------------------------------------------ voice

type VoiceNotice = 'denied' | 'no_speech' | 'language' | 'failed' | 'no_voice' | 'no_device' | 'too_long' | 'unavailable' | 'playback' | null;

function speechErrorNotice(error: unknown): VoiceNotice {
  const code = error instanceof ApiRequestError ? error.code : '';
  if (code === 'speech_no_speech') return 'no_speech';
  if (code === 'speech_too_long' || code === 'speech_invalid_audio') return 'too_long';
  // Not configured, provider down, network or anything else on the server path (never
  // the browser's own speech service, which server mode does not use).
  return 'unavailable';
}

/**
 * Microphone and speech playback.
 *  - Server mode (OSRIP speech service configured and the browser can record): the
 *    microphone opens only from the mic button, the recording is sent once for
 *    transcription and is not stored, and the text fills the box for review (never sent by
 *    itself). Replies are synthesised by the server and the avatar follows their loudness.
 *  - Browser mode: the browser's own Web Speech API, where available.
 *  - Otherwise text only. Listening stops before playback; mute stops all speech output.
 */
function useVoice(
  language: 'en' | 'ar', onTranscript: (text: string) => void, maxSeconds: number, server: boolean, gender: PersonaGender,
) {
  const ui = useAssistantUi();
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [paused, setPaused] = useState(false); // server audio paused by the person
  const [preparing, setPreparing] = useState(false); // spoken answer requested, not playing yet
  const [notice, setNotice] = useState<VoiceNotice>(null);
  const [muted, setMutedState] = useState(() => readStore('local', MUTE_KEY) === '1');
  const [voices, setVoices] = useState(0);
  const recognizer = useRef<Recognizer | null>(null);
  const recording = useRef<Recording | null>(null);
  const pendingStop = useRef(false);
  const attempts = useRef(0); // bumped by every cancel, so a late-opening microphone is closed
  const playback = useRef<Playback | null>(null);
  const aborter = useRef<AbortController | null>(null);
  const serverMode = server && recordingSupported();
  const canListen = serverMode || recognitionSupported();
  useEffect(() => onVoicesChanged(() => setVoices((n) => n + 1)), []);
  // Each persona speaks only with a voice of its gender: the server uses the voice configured
  // for it in the profile; the browser fallback picks by gender (see lib/speech.ts).
  const canSpeak = server || (voices >= 0 && voiceFor(language, gender) !== null);
  const noVoice = !server && voices >= 0 && noVoiceOfGender(language, gender);
  const noLanguageVoice = !server && voices >= 0 && noVoiceForLanguage(language);

  // Only the stable callbacks: the ui object changes with every state change, and a
  // cleanup keyed on it would cancel the recording or request it is reporting on.
  const { setActivity } = ui;
  useEffect(() => setActivity('listening', listening || transcribing), [listening, transcribing, setActivity]);
  useEffect(() => setActivity('speaking', speaking), [speaking, setActivity]);
  useEffect(() => () => {
    // Unmount only: stop the microphone, any request in flight and any playback.
    attempts.current += 1;
    recognizer.current?.abort();
    recording.current?.cancel();
    aborter.current?.abort();
    playback.current?.stop();
    stopSpeaking();
    setVoiceLevel(0);
    setActivity('listening', false);
    setActivity('speaking', false);
  }, [setActivity]);

  const stopPlayback = useCallback(() => {
    playback.current?.stop();
    playback.current = null;
    aborter.current?.abort();
    stopSpeaking();
    setVoiceLevel(0);
    setSpeaking(false);
    setPaused(false);
    setPreparing(false);
  }, []);
  const pausePlayback = useCallback(() => playback.current?.pause(), []);
  const resumePlayback = useCallback(() => playback.current?.resume(), []);

  const finishRecording = async () => {
    const rec = recording.current;
    if (!rec) {
      // Stop pressed while the microphone is still opening: stop as soon as it is ready,
      // instead of silently dropping the press and leaving the microphone on.
      pendingStop.current = true;
      return;
    }
    recording.current = null;
    setListening(false);
    const audio = await rec.stop();
    if (!audio) { setNotice('no_speech'); return; }
    const controller = new AbortController();
    aborter.current = controller;
    setTranscribing(true);
    try {
      onTranscript(await transcribe(audio, language, controller.signal));
    } catch (error) {
      if (!controller.signal.aborted) {
        setNotice(speechErrorNotice(error));
        ui.reportError();
      }
    } finally {
      setTranscribing(false);
    }
  };

  const start = () => {
    stopPlayback();
    setNotice(null);
    if (serverMode) {
      setListening(true); // shown at once; the browser asks for permission now, after the click
      pendingStop.current = false;
      const attempt = ++attempts.current;
      startRecording({ maxSeconds, onLimit: () => void finishRecording() })
        .then((rec) => {
          // Cancelled (or the call ended) while the microphone was opening: close it at once.
          if (attempt !== attempts.current) { rec.cancel(); return; }
          recording.current = rec;
          if (pendingStop.current) {
            pendingStop.current = false;
            void finishRecording();
          }
        })
        .catch((error: { code?: RecorderError }) => {
          pendingStop.current = false;
          setListening(false);
          setNotice(error.code === 'denied' ? 'denied' : error.code === 'no_device' ? 'no_device' : 'failed');
        });
      return;
    }
    const rec = createRecognizer(language, {
      onText: (text) => onTranscript(text),
      onError: (code) => {
        setNotice(PERMISSION_ERRORS.has(code) ? 'denied' : code === 'no-speech' ? 'no_speech' : code === 'language-not-supported' ? 'language' : code === 'aborted' ? null : 'failed');
        if (code !== 'aborted' && code !== 'no-speech') ui.reportError();
      },
      onEnd: () => setListening(false),
    });
    if (!rec) return;
    recognizer.current = rec;
    try {
      rec.start(); // the browser asks for microphone permission here, after the click
      setListening(true);
    } catch {
      setNotice('failed');
    }
  };
  // Keeps the words heard so far for review.
  const stop = () => (serverMode ? void finishRecording() : recognizer.current?.stop());
  const cancel = () => {
    recognizer.current?.abort();
    recording.current?.cancel();
    recording.current = null;
    pendingStop.current = false;
    attempts.current += 1;
    aborter.current?.abort();
    onTranscript('');
    setListening(false);
    setTranscribing(false);
  };

  /** Read a reply aloud in the voice of the persona that gave it (``voiceGender``). */
  const say = (message: AssistantMessage, voiceGender: PersonaGender = gender) => {
    if (muted) return;
    attempts.current += 1;
    recognizer.current?.abort(); // never listen while speaking
    recording.current?.cancel();
    setListening(false);
    stopPlayback();
    setNotice(null);
    if (server) {
      const controller = new AbortController();
      aborter.current = controller;
      // "Speaking" only once sound actually plays; until then the audio is being prepared.
      setPreparing(true);
      speakMessage(message.id, language, controller.signal)
        .then((audio) => {
          if (controller.signal.aborted) return;
          playback.current = playAudio(audio, {
            onStart: () => { setPreparing(false); setSpeaking(true); },
            onLevel: setVoiceLevel,
            onEnd: () => { setPreparing(false); setSpeaking(false); setPaused(false); },
            onError: () => { setPreparing(false); setSpeaking(false); setPaused(false); setNotice('playback'); ui.reportError(); },
            onPause: setPaused,
          });
        })
        .catch((error: unknown) => {
          setPreparing(false);
          if (!controller.signal.aborted) { setNotice(speechErrorNotice(error)); ui.reportError(); }
        });
      return;
    }
    const started = speak(message.content, language, voiceGender, {
      onStart: () => setSpeaking(true),
      onEnd: () => setSpeaking(false),
      onError: () => {
        setSpeaking(false);
        setNotice('failed');
        ui.reportError();
      },
    });
    if (!started) setNotice('no_voice');
  };
  const setMuted = (value: boolean) => {
    setMutedState(value);
    writeStore('local', MUTE_KEY, value ? '1' : null);
    if (value) stopPlayback();
  };
  const cancelAll = useCallback(() => {
    attempts.current += 1;
    pendingStop.current = false;
    recognizer.current?.abort();
    recording.current?.cancel();
    recording.current = null;
    setListening(false);
    setTranscribing(false);
    stopPlayback();
  }, [stopPlayback]);
  return {
    canListen, canSpeak, noVoice, noLanguageVoice, serverMode, listening, transcribing, preparing, speaking: speaking || preparing, notice, muted,
    paused, canPause: server && speaking, start, stop, cancel, cancelAll, say, stopPlayback, pausePlayback, resumePlayback, setMuted,
  };
}

/** The chat's voice state and actions (listening, speaking, mute), as the conversation page uses them. */
export type ChatVoice = ReturnType<typeof useVoice>;

// ------------------------------------------------------------------ allowance and sign-in

function AllowanceMeter({ allowance, notice }: { allowance: Allowance; notice: { en: string; ar: string } }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border bg-background p-3 text-xs" data-testid="guest-allowance"
      data-remaining={allowance.remaining}>
      <p className="font-medium" role="status">
        {t('guest.remaining', { remaining: allowance.remaining, limit: allowance.limit })}
      </p>
      <div className="flex gap-1" aria-hidden="true">
        {Array.from({ length: allowance.limit }, (_, i) => (
          <span key={i} className={i < allowance.used ? 'h-1.5 flex-1 rounded-full bg-copper/70' : 'h-1.5 flex-1 rounded-full bg-primary/25'} />
        ))}
      </div>
      <details>
        <summary className="cursor-pointer text-muted-foreground">{t('guest.howCounted')}</summary>
        <p className="mt-1 text-muted-foreground">{pick(notice, language)}</p>
      </details>
    </div>
  );
}

function SignInPrompt({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  const providers = useProviders();
  const p = providers.data;
  return (
    <div className="flex flex-col gap-3 rounded-md border border-copper/40 bg-copper-subtle/40 p-4 text-sm" data-testid="assistant-sign-in" role="status">
      <p className="font-semibold">{t('guest.limitReachedTitle')}</p>
      <p>{t('guest.limitReached')}</p>
      <div className="flex flex-wrap gap-2">
        <Link to={to('/sign-in')} onClick={onNavigate} className="rounded-md bg-primary px-3 py-2 font-medium text-primary-foreground" data-testid="guest-sign-in">
          {t('auth.signIn')}
        </Link>
        {p?.registration ? (
          <Link to={to('/register')} onClick={onNavigate} className="rounded-md border border-border-strong px-3 py-2 font-medium">
            {t('guest.registerEmail')}
          </Link>
        ) : null}
        {p?.sms.available ? (
          <Link to={{ ...to('/register'), search: `${to('/register').search ? `${to('/register').search}&` : '?'}method=phone` }} onClick={onNavigate}
            className="rounded-md border border-border-strong px-3 py-2 font-medium">
            {t('guest.registerPhone')}
          </Link>
        ) : null}
      </div>
      <p className="text-xs text-muted-foreground">{t('guest.keptNote')}</p>
    </div>
  );
}

// ------------------------------------------------------------------ the chat

/** Asks a question from outside the chat (a suggested question, or "Run analysis"). */
export type AskFromOutside = (question: string, mode?: AssistantMode) => void;

/** The chat itself, used by the side panel and by the full AI Assistant page. */
export function AssistantChat({ onClose, initialDraft = '', active = true, showIdentity = true, askRef, selection = null, selectionLabel, variant = 'panel', tools }: {
  onClose?: () => void;
  initialDraft?: string;
  /** Asked from a sector page: its applied selection, sent with each question until removed. */
  selection?: AskSelection | null;
  selectionLabel?: string;
  active?: boolean;
  /** False in the Talk workspace, which shows the large portrait and state itself. */
  showIdentity?: boolean;
  /** "talk": compact for the Talk page (one row of controls; help, setup and voice notes are in
   * Settings, with a one-line notice and a link when no voice can read the answers). */
  variant?: 'panel' | 'talk' | 'chat';
  /** "chat" only: page tools for the Tools drawer (analysis, a full study). */
  tools?: ReactNode;
  /** Filled with this chat's send function, so a page can ask a question in it. */
  askRef?: { current: AskFromOutside | null };
}) {
  const { t } = useTranslation();
  const appLanguage = useAppLanguage();
  const [mode] = useDataMode();
  const ui = useAssistantUi();
  const { persona, byCode } = usePersona();
  const me = useMe();
  const status = useAssistantStatus();
  const signedIn = Boolean(me.data?.authenticated);
  const allowed = hasPermission(me.data, 'assistant.use');
  const guestStatus = useGuestStatus(!me.isPending);

  // Chat language: follows the interface language until the reader picks one here.
  const [chatLanguage, setChatLanguage] = useState<'en' | 'ar'>(appLanguage);
  const pickedLanguage = useRef(false);
  useEffect(() => {
    if (!pickedLanguage.current) setChatLanguage(appLanguage);
  }, [appLanguage]);

  // Account conversations.
  const conversations = useConversations(signedIn && allowed);
  const [activeId, setActiveId] = useState<string | null>(null);
  const conversation = useConversation(signedIn ? activeId : null);
  const create = useCreateConversation();
  const accountAsk = useAsk(activeId);
  const remove = useDeleteConversation();
  const link = useLinkGuestHistory();

  // Guest conversation (kept in this tab across sign-in pages).
  const [guestId, setGuestIdState] = useState<string | null>(() => readStore('session', GUEST_CONVERSATION_KEY));
  const setGuestId = (id: string | null) => {
    setGuestIdState(id);
    writeStore('session', GUEST_CONVERSATION_KEY, id);
  };
  const guestConversation = useGuestConversation(!signedIn ? guestId : null);
  const guestAsk = useGuestAsk();
  const [scope, setScope] = useState<AskSelection | null>(selection);
  const [shownSelection, setShownSelection] = useState(selection);
  if (shownSelection !== selection) {
    // A new selection from the page (adjusting state while rendering, not in an effect).
    setShownSelection(selection);
    setScope(selection);
  }
  const scoped = scope ?? undefined;

  const [draft, setDraftState] = useState(() => initialDraft || readStore('session', DRAFT_KEY) || '');
  const setDraft = (value: string) => {
    setDraftState(value);
    writeStore('session', DRAFT_KEY, value || null);
  };
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [viaVoice, setViaVoice] = useState(false);
  const last = useRef<{ text: string; requestId: string; mode: RequestMode } | null>(null);
  // The question being answered (shown at once on the conversation page) and the size of the
  // conversation when it was sent: it is shown until the conversation returns it.
  const [asked, setAsked] = useState<{ text: string; requestId: string; base: number; echo: boolean } | null>(null);
  const spokenFor = useRef<number | null>(null);
  const listRef = useRef<HTMLOListElement>(null);
  const inputId = useId();
  const max = status.data?.max_message_chars ?? 1000;
  const voiceStatus = useVoiceStatus();
  const voice = useVoice(chatLanguage, (text) => {
    setDraft(text.slice(0, max));
    setViaVoice(Boolean(text));
  }, voiceStatus.data?.max_seconds ?? 60, Boolean(voiceStatus.data?.configured), persona.gender);
  // Web research: on by default where the server offers it; the reader can switch it off.
  const webAvailable = Boolean(status.data?.web_research);
  const [webOn, setWebOn] = useState(() => readStore('local', WEB_KEY) !== '0');
  // Answer mode (remembered on this device). Research mode always asks for web research.
  const [answerMode, setAnswerModeState] = useState<AssistantMode>(() => {
    const stored = readStore('local', MODE_KEY);
    return ASSISTANT_MODES.find((m) => m === stored) ?? 'ask';
  });
  const setAnswerMode = (value: AssistantMode) => {
    setAnswerModeState(value);
    writeStore('local', MODE_KEY, value === 'ask' ? null : value);
  };
  // The conversation page asks with "auto" (the server infers the mode from the question)
  // unless the person picks one in Tools, for this visit only.
  const chatPage = variant === 'chat';
  const [chatMode, setChatMode] = useState<RequestMode>('auto');
  const effectiveMode: RequestMode = chatPage ? chatMode : answerMode;
  const webResearch = webAvailable && (webOn || effectiveMode === 'research');
  // Research mode only: a second search route as a cross-check, when the person asks for one
  // (never on by default; it uses more of the limits and is not independent evidence).
  const crossCheckAvailable = Boolean(status.data?.cross_check_available) && effectiveMode === 'research';
  const [crossCheckOn, setCrossCheckOn] = useState(false);
  const crossCheck = crossCheckAvailable && crossCheckOn;

  const guestData = guestStatus.data && !guestStatus.data.authenticated ? guestStatus.data : null;
  const allowance = guestData?.allowance ?? null;
  const exhaustedError = guestAsk.error instanceof ApiRequestError && guestAsk.error.code === 'guest_allowance_exhausted';
  const needsAccount = !signedIn && (Boolean(allowance?.authentication_required) || exhaustedError);
  const pending = accountAsk.isPending || create.isPending || guestAsk.isPending;
  const error = signedIn ? accountAsk.error : exhaustedError ? null : guestAsk.error;
  const messages = (signedIn ? conversation.data?.messages : guestConversation.data?.messages) ?? [];

  const { setActivity, reportError } = ui; // stable callbacks (the ui object is not)
  // Processing: a question in flight, or a spoken answer being prepared (not yet playing).
  const preparingSpeech = voice.preparing;
  useEffect(() => setActivity('processing', pending || preparingSpeech), [pending, preparingSpeech, setActivity]);
  // Closing the panel ends listening and speech (the chat itself stays mounted).
  const { cancelAll } = voice;
  useEffect(() => {
    if (!active) cancelAll();
  }, [active, cancelAll]);
  useEffect(() => {
    if (error) reportError();
  }, [error, reportError]);
  useEffect(() => {
    listRef.current?.lastElementChild?.scrollIntoView({ block: 'end' });
  }, [messages.length, pending]);

  // A reply to a spoken question is read aloud (unless muted); its text stays on screen.
  const lastMessage = messages[messages.length - 1];
  useEffect(() => {
    if (!viaVoice || !lastMessage || lastMessage.role !== 'assistant' || spokenFor.current === lastMessage.id) return;
    spokenFor.current = lastMessage.id;
    setViaVoice(false);
    if (lastMessage.status === 'lookup' || lastMessage.status === 'unavailable' || lastMessage.status === 'cancelled') return;
    voice.say(lastMessage, byCode(lastMessage.persona).gender);
  }, [lastMessage, viaVoice, voice, byCode]);

  // New account conversations: created first, the question is sent once the id is known.
  const pendingRef = useRef<{ text: string; requestId: string; mode: RequestMode } | null>(null);
  const { startStudy } = ui;
  const dispatch = (text: string, requestId: string, askMode: RequestMode) => {
    const checked = crossCheck && askMode === 'research';
    // The question is followed as a live study (the workspace shows its progress and results).
    startStudy({ id: requestId, guest: !signedIn, question: text });
    if (signedIn) {
      if (!activeId) {
        pendingRef.current = { text, requestId, mode: askMode };
        create.mutate({ language: chatLanguage, data_mode: mode }, { onSuccess: (conv) => setActiveId(conv.id) });
        return;
      }
      accountAsk.mutate({
        content: text, language: chatLanguage, request_id: requestId, web_research: webResearch, mode: askMode, persona: persona.code,
        cross_check: checked, selection: scoped,
      });
      return;
    }
    guestAsk.mutate(
      {
        content: text, language: chatLanguage, request_id: requestId, conversation_id: guestId, data_mode: mode,
        web_research: webResearch, mode: askMode, persona: persona.code, cross_check: checked, selection: scoped,
      },
      { onSuccess: (result) => setGuestId(result.conversation_id) },
    );
  };
  useEffect(() => {
    if (activeId && pendingRef.current) {
      const q = pendingRef.current;
      pendingRef.current = null;
      accountAsk.mutate({
        content: q.text, language: chatLanguage, request_id: q.requestId, web_research: webResearch, mode: q.mode, persona: persona.code,
        cross_check: crossCheck && q.mode === 'research', selection: scoped,
      });
    }
  }, [activeId, accountAsk, chatLanguage, webResearch, persona.code, crossCheck, scoped]);

  const send = (question: string, modeOverride?: RequestMode) => {
    const text = question.trim();
    if (!text || pending || needsAccount) return;
    if (voice.listening) voice.stop();
    const askMode = modeOverride ?? effectiveMode;
    last.current = { text, requestId: newRequestId(), mode: askMode };
    setAsked({ text, requestId: last.current.requestId, base: messages.length, echo: true });
    setDraft('');
    dispatch(text, last.current.requestId, askMode);
  };
  // The page may ask through this chat; the latest send (with the current state) is exposed.
  useEffect(() => {
    if (askRef) askRef.current = send;
  });
  useEffect(() => () => {
    if (askRef) askRef.current = null;
  }, [askRef]);
  // Retrying the same failed question reuses its request id (and mode): it is never charged twice.
  const retry = () => {
    if (!last.current || pending) return;
    // The draft was given back after a failure: sending it again by Retry empties it.
    if (draft === last.current.text) setDraft('');
    setAsked({ text: last.current.text, requestId: last.current.requestId, base: messages.length, echo: !messages.length });
    dispatch(last.current.text, last.current.requestId, last.current.mode);
  };
  // Conversation page: a question that could not be sent goes back into the box (unless the
  // person has typed something new), so nothing is lost; Retry sends it again.
  const [seenError, setSeenError] = useState<unknown>(null);
  if (chatPage && error && error !== seenError) {
    setSeenError(error);
    if (!draft && asked) setDraftState(asked.text);
  }
  const submit = (event: FormEvent) => {
    event.preventDefault();
    send(draft);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  // Return to a reply's study in the workspace (opening it there from any other page).
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const preserved = usePreservedSearch();
  const openStudyHere = (id: string) => {
    ui.openStudy(id, !signedIn);
    if (pathname !== '/workspace') {
      onClose?.();
      void navigate(preserved('/workspace'));
    }
  };

  const suggestions = status.data?.suggestions[chatLanguage] ?? [];
  const configured = status.data?.configured ?? false;
  const canAsk = signedIn ? allowed : true;
  const linkable = signedIn && guestStatus.data?.authenticated === true && guestStatus.data.linkable_history && !link.isSuccess;
  const speakHandler = voice.canSpeak && !voice.muted
    ? (m: AssistantMessage) => voice.say(m, byCode(m.persona).gender)
    : null;
  const talk = variant === 'talk';
  // A study request to review and edit: it fills the box and the mode, and sends nothing. Above
  // the message box; in Talk at the top of the conversation, so the pinned composer stays small.
  const linkUi = (
    <>
      {linkable ? (
        <div className="mb-3 flex flex-col gap-2 rounded-md border border-primary/30 bg-primary/5 p-3 text-sm" data-testid="link-guest-history">
          <p>{t('guest.linkPrompt')}</p>
          <Button size="sm" className="w-fit" disabled={link.isPending}
            onClick={() => link.mutate(undefined, { onSuccess: () => { if (guestId) setActiveId(guestId); setGuestId(null); } })}>
            {t('guest.linkAction')}
          </Button>
        </div>
      ) : null}
      {link.isSuccess ? <p className="mb-3 text-sm" role="status" data-testid="link-guest-done">{t('guest.linkDone', { count: link.data.linked_conversations })}</p> : null}
    </>
  );
  const brief = (
    <ResearchBriefBuilder language={chatLanguage} disabled={pending || needsAccount} maxLength={max}
      onDraft={(text, briefMode) => {
        setDraft(text);
        if (chatPage) setChatMode(briefMode);
        else setAnswerMode(briefMode);
        setViaVoice(false);
        document.getElementById(inputId)?.focus();
      }} />
  );

  if (chatPage) {
    const asking = asked && !error && (pending || messages.length <= asked.base)
      ? { text: asked.text, requestId: asked.requestId, echo: asked.echo } : null;
    return (
      <ChatView chat={{
        language: chatLanguage,
        setLanguage: (l) => { pickedLanguage.current = true; setChatLanguage(l); },
        dataMode: (signedIn ? conversation.data?.data_mode : guestConversation.data?.data_mode) ?? mode,
        messages, pending, asking, guest: !signedIn, error, send, retry,
        draft, type: (text) => { setDraft(text); setViaVoice(false); }, max, inputId, viaVoice,
        canAsk, needsAccount, signedIn, allowance, signInPrompt: <SignInPrompt onNavigate={onClose} />,
        voice, speak: speakHandler,
        web: { available: webAvailable, on: webOn, set: (on) => { setWebOn(on); writeStore('local', WEB_KEY, on ? null : '0'); } },
        mode: { value: chatMode, set: setChatMode },
        crossCheck: { available: crossCheckAvailable, on: crossCheckOn, set: setCrossCheckOn },
        conversations: signedIn && allowed ? {
          list: conversations.data ?? [], activeId, select: setActiveId, removing: remove.isPending,
          remove: () => { if (activeId) remove.mutate(activeId, { onSuccess: () => setActiveId(null) }); },
        } : null,
        newConversation: () => { if (signedIn) setActiveId(null); else setGuestId(null); setAsked(null); },
        linkPrompt: linkUi,
        memory: { guestExpires: guestData?.expires_at ?? null, guestConversationId: signedIn ? null : guestId,
          onGuestDeleted: () => setGuestId(null), onAllDeleted: () => setActiveId(null) },
        selection: { value: scope, label: selectionLabel, clear: () => setScope(null) },
        // This page shows no study panel: a reply's study always opens in the workspace.
        brief, openStudy: openStudyHere, activeStudyId: null, suggestions, tools,
      }} />
    );
  }

  return (
    // Narrow screens: the whole chat scrolls as one column (the composer stays pinned at the
    // bottom), so the header and answer modes never squeeze the messages out of view. Talk keeps
    // one compact row of controls instead, and only the message list scrolls at every width.
    <div className={cn('flex min-h-0 flex-1 flex-col', !talk && 'max-sm:overflow-y-auto')} data-testid="assistant-panel" lang={chatLanguage}>
      {/* Who is speaking: the chosen persona's portrait (a fictional person), always labelled
          as an AI assistant, and the choice between the two personas. */}
      <div className={cn('flex flex-col gap-3 border-b border-border bg-muted/50 px-4 py-3', !showIdentity && 'hidden')} data-testid="assistant-identity">
        <div className="flex items-center gap-3">
          <AssistantAvatar state={ui.state} size="4rem" decorative={false} />
          <div className="min-w-0 text-xs">
            <p className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-foreground" data-testid="mulhim-name" data-persona={persona.code}>{persona.name[appLanguage]}</span>
              <Badge variant="accent">{t('assistant.aiAssistant')}</Badge>
              <span className="font-medium" role="status" data-testid="assistant-state" data-state={ui.state}>{t(ORB_STATE_KEY[ui.state])}</span>
            </p>
          </div>
        </div>
        {showIdentity ? <PersonaPicker /> : null /* Talk has its own, beside the portrait */}
      </div>
      {/* Talk: the answer modes and the toolbar share one wrapped row (elsewhere `contents`). */}
      <div className={talk ? 'flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border px-3 py-2' : 'contents'} data-testid="assistant-controls">
      {/* Answer mode: the same assistant (and the same avatar) for all five modes. */}
      {canAsk ? (
        <div className={talk ? 'min-w-0' : 'border-b border-border px-4 py-2.5'}>
          <ModeSelector value={answerMode} onChange={setAnswerMode} compact={talk} />
          {answerMode === 'research' && status.data && !webAvailable ? (
            <p className="mt-1 text-xs text-destructive" role="status" data-testid="research-unavailable">{t('assistant.researchNeedsSearch')}</p>
          ) : null}
          {crossCheckAvailable ? (
            <div className="mt-2 text-xs">
              <label className="flex items-center gap-2 font-medium">
                <input type="checkbox" checked={crossCheckOn} onChange={(e) => setCrossCheckOn(e.target.checked)}
                  aria-describedby={`${inputId}-cross-check`} className="size-4 accent-primary" data-testid="cross-check-toggle" />
                {t('assistant.crossCheck')}
              </label>
              <p id={`${inputId}-cross-check`} className="ms-6 text-muted-foreground">{t('assistant.crossCheckHint')}</p>
            </div>
          ) : null}
        </div>
      ) : null}
      {/* Toolbar: answer language, web research, voice output */}
      <div className={talk ? 'contents' : 'flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border px-4 py-2.5'}>
        {webAvailable ? (
          <label className="flex items-center gap-2 text-xs font-medium" title={t('assistant.webToggleHint')}>
            <input type="checkbox" checked={webOn} className="size-4 accent-primary" data-testid="web-toggle"
              onChange={(e) => { setWebOn(e.target.checked); writeStore('local', WEB_KEY, e.target.checked ? null : '0'); }} />
            <Globe aria-hidden="true" className="size-3.5" />{t('assistant.webToggle')}
          </label>
        ) : null}
        <Segmented
          className="ms-auto"
          label={t('assistant.language')}
          value={chatLanguage}
          onChange={(v) => { pickedLanguage.current = true; setChatLanguage(v === 'ar' ? 'ar' : 'en'); }}
          options={[{ value: 'en', label: 'English' }, { value: 'ar', label: 'العربية' }]}
          testId="assistant-language"
        />
        {voice.canSpeak ? (
          <>
            <Button variant="ghost" size="sm" aria-pressed={voice.muted} onClick={() => voice.setMuted(!voice.muted)} data-testid="voice-mute"
              title={talk ? (voice.muted ? t('voice.unmute') : t('voice.mute')) : undefined} className={cn(talk && 'w-8 px-0')}>
              {voice.muted ? <VolumeX aria-hidden="true" /> : <Volume2 aria-hidden="true" />}
              <span className={cn(talk && 'sr-only')}>{voice.muted ? t('voice.unmute') : t('voice.mute')}</span>
            </Button>
            {/* Talk on a phone or a short screen: Mute and the device's own volume, to keep the
                controls to one row. */}
            <span className={cn(talk && 'max-sm:hidden short:hidden')}><VoiceVolume testId="voice-volume-replies" compact={talk} /></span>
          </>
        ) : null}
        {voice.canPause ? (
          <Button variant="ghost" size="sm" onClick={voice.paused ? voice.resumePlayback : voice.pausePlayback}
            aria-pressed={voice.paused} data-testid="voice-pause">
            {voice.paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}
            {voice.paused ? t('voicePanel.resume') : t('voicePanel.pause')}
          </Button>
        ) : null}
        {voice.speaking ? (
          <Button variant="outline" size="sm" onClick={voice.stopPlayback} data-testid="voice-stop-speaking">
            <Square aria-hidden="true" />{t('voice.stopSpeaking')}
          </Button>
        ) : null}
      </div>
      </div>

      {signedIn && allowed ? (
        <div className="flex flex-wrap items-end gap-2 border-b border-border px-4 py-3">
          <SelectField className="min-w-0 flex-1" label={t('assistant.conversation')} value={activeId ?? ''}
            onValueChange={(v) => { setActiveId(v || null); setConfirmDelete(false); }}
            options={[{ value: '', label: t('assistant.newConversation') }, ...(conversations.data ?? []).map((c) => ({ value: c.id, label: c.title }))]}
            data-testid="conversation-select" />
          <Button variant="outline" size="sm" onClick={() => { setActiveId(null); setConfirmDelete(false); }}>
            <MessageSquarePlus aria-hidden="true" />{t('assistant.new')}
          </Button>
          {activeId ? (
            <Button variant={confirmDelete ? 'default' : 'ghost'} size="sm" data-testid="delete-conversation"
              onClick={() => {
                if (!confirmDelete) { setConfirmDelete(true); return; }
                remove.mutate(activeId, { onSuccess: () => { setActiveId(null); setConfirmDelete(false); } });
              }}>
              <Trash2 aria-hidden="true" />{confirmDelete ? t('assistant.confirmDelete') : t('assistant.delete')}
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className={cn('min-h-0 flex-1 overflow-y-auto px-4 py-3', !talk && 'max-sm:min-h-[45dvh] max-sm:flex-none max-sm:overflow-visible')} aria-live="polite"
        data-testid="assistant-messages">
        <p className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <DataModeBadge mode={(signedIn ? conversation.data?.data_mode : guestConversation.data?.data_mode) ?? mode} />
          <span data-testid="assistant-disclaimer-short">{t('assistant.disclaimerShort')}</span>
        </p>
        {status.data && !configured ? (
          <p role="status" className="mb-2 rounded-md border border-dashed border-border-strong/50 px-3 py-2 text-sm" data-testid="assistant-unconfigured">
            {t('assistant.notConfiguredShort')}
          </p>
        ) : null}
        {/* Explanations and limits, collapsed: the conversation comes first. Talk links to
            Settings for them instead. */}
        {talk ? null : (
        <div className="mb-3 flex flex-col gap-2">
          <details className="rounded-md border border-border px-3 py-2 text-xs" data-testid="assistant-help">
            <summary className="flex cursor-pointer items-center gap-1.5 font-semibold">
              <CircleHelp aria-hidden="true" className="size-3.5" />{t('assistant.help.title')}
            </summary>
            <ul className="mt-2 flex list-disc flex-col gap-1 ps-4 text-muted-foreground">
              <li>{t('assistant.disclaimer', { name: persona.name[appLanguage] })}</li>
              <li>{t('assistant.help.dataReport')}</li>
              {status.data?.research_cutoff ? (
                <li data-testid="research-cutoff">
                  {t('assistant.cutoff', { date: formatPeriod(status.data.research_cutoff, status.data.research_cutoff, appLanguage) })}
                </li>
              ) : null}
              {status.data && !configured ? <li>{t('assistant.notConfiguredLookup')}</li> : null}
              {status.data && configured && !webAvailable ? <li data-testid="web-unavailable">{t('assistant.webUnavailable')}</li> : null}
              {webResearch ? <li>{t('assistant.webToggleHint')}</li> : null}
              <li>{t('assistant.avatarNote')}</li>
              {voice.canSpeak ? <li>{t('voice.animationNote')}</li> : null}
              <li>{voice.serverMode ? t('voice.serverDisclosure') : voice.canListen ? t('voice.disclosure') : t('voice.unsupported')}</li>
            </ul>
          </details>
          <AboutMulhim />
          <MemoryPanel signedIn={signedIn} guestExpires={guestData?.expires_at ?? null} guestConversationId={signedIn ? null : guestId}
            onGuestDeleted={() => setGuestId(null)} onAllDeleted={() => setActiveId(null)} />
        </div>
        )}
        {talk && canAsk ? <div className="mb-3">{brief}</div> : null}
        {signedIn && !allowed ? <p className="mb-3 text-sm">{t('assistant.noPermission')}</p> : null}
        {!signedIn && allowance && guestData ? <div className="mb-3"><AllowanceMeter allowance={allowance} notice={guestData.notice} /></div> : null}
        {linkUi}
        {messages.length === 0 && !pending && canAsk && !needsAccount ? (
          <div className="flex flex-col gap-2" data-testid="suggestions">
            <p className="text-xs font-semibold">{t('assistant.suggested')}</p>
            {suggestions.map((s) => (
              <button key={s} type="button" onClick={() => send(s)}
                className="rounded-md border border-border-strong/50 px-3 py-2 text-start text-sm hover:bg-muted disabled:opacity-60" dir="auto">{s}</button>
            ))}
          </div>
        ) : null}
        <ol ref={listRef} className="flex flex-col gap-3">
          {messages.map((m) => (
            <MessageView key={m.id} message={m} onAsk={send} onRetry={retry} onSpeak={speakHandler} canSave={signedIn && allowed}
              onOpenStudy={openStudyHere} activeStudyId={ui.activeStudy?.id ?? null} />
          ))}
          {pending ? (
            <ResearchProgress requestId={(signedIn ? accountAsk.variables?.request_id : guestAsk.variables?.request_id) ?? null} guest={!signedIn} />
          ) : null}
        </ol>
        {needsAccount ? <div className="mt-3"><SignInPrompt onNavigate={onClose} /></div> : null}
        {error ? (
          <div role="alert" className="mt-3 flex flex-col gap-2 text-sm text-destructive" data-testid="assistant-error">
            <p>{error.message}</p>
            <Button variant="outline" size="sm" className="w-fit" onClick={retry}><RotateCcw aria-hidden="true" />{t('states.retry')}</Button>
          </div>
        ) : null}
      </div>

      {canAsk ? (
        <form onSubmit={submit} className={cn('flex flex-col gap-2 border-t border-border bg-card px-4 py-3', !talk && 'max-sm:sticky max-sm:bottom-0 max-sm:z-10')}>
          {talk ? null : brief}
          {scope ? (
            <p className="flex flex-wrap items-center gap-2 rounded-md border border-primary/40 bg-primary/5 px-2 py-1 text-xs" data-testid="assistant-selection">
              <span>{t('assistant.selectionApplied', { selection: selectionLabel ?? `${scope.indicator} · ${scope.area} · ${scope.period_from} – ${scope.period_to}` })}</span>
              <button type="button" className="text-primary underline underline-offset-2" onClick={() => setScope(null)} data-testid="assistant-selection-clear">
                {t('assistant.selectionClear')}
              </button>
            </p>
          ) : null}
          <label htmlFor={inputId} className="sr-only">{t('assistant.question')}</label>
          <textarea id={inputId} value={draft} onChange={(e) => { setDraft(e.target.value.slice(0, max)); setViaVoice(false); }} onKeyDown={onKeyDown}
            rows={2} dir="auto" placeholder={needsAccount ? t('guest.inputLocked') : t('assistant.placeholder')} disabled={needsAccount}
            className={cn('w-full resize-none rounded-md border border-border-strong bg-card px-3 py-2 text-sm', talk && 'short:h-10')} data-testid="assistant-input" />
          {voice.notice ? (
            <p className="text-xs text-destructive" role="alert" data-testid="voice-notice">{t(`voice.notice.${voice.notice}`)}</p>
          ) : null}
          {voice.serverMode && voice.listening ? (
            <p className="text-xs font-medium" role="status" data-testid="voice-recording">{t('voice.recording', { seconds: voiceStatus.data?.max_seconds ?? 60 })}</p>
          ) : null}
          {voice.transcribing ? (
            <p className="flex items-center gap-1 text-xs" role="status" data-testid="voice-transcribing">
              <Loader2 aria-hidden="true" className="size-3 animate-spin motion-reduce:animate-none" />{t('voice.transcribing')}
            </p>
          ) : null}
          {viaVoice && draft && !voice.listening && !voice.transcribing ? (
            <p className="text-xs text-muted-foreground" role="status" data-testid="voice-review">{t('voice.review')}</p>
          ) : null}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {voice.canListen ? (
                voice.listening || voice.transcribing ? (
                  <>
                    <Button type="button" size="sm" variant="default" onClick={voice.stop} disabled={voice.transcribing} data-testid="voice-stop">
                      <MicOff aria-hidden="true" />{t('voice.stopListening')}
                    </Button>
                    <Button type="button" size="sm" variant="ghost" onClick={voice.cancel} data-testid="voice-cancel">
                      <X aria-hidden="true" />{t('voice.cancel')}
                    </Button>
                  </>
                ) : (
                  <Button type="button" size="sm" variant="outline" onClick={voice.start} disabled={needsAccount} data-testid="voice-start">
                    <Mic aria-hidden="true" />{t('voice.speak')}
                  </Button>
                )
              ) : null}
              <span className="text-xs text-muted-foreground">{draft.length}/{max}</span>
            </div>
            <Button type="submit" size="sm" disabled={!draft.trim() || pending || needsAccount} data-testid="assistant-send">
              <Send aria-hidden="true" className="rtl:-scale-x-100" />{t('assistant.send')}
            </Button>
          </div>
          {talk ? (
            // One line, only when answers cannot be read aloud here; the explanation is in Settings.
            voice.noVoice || voice.noLanguageVoice ? (
              <p className="text-xs text-muted-foreground" role="status" data-testid="talk-no-voice">
                {t('talk.noVoice')}{' '}
                <Link to={preserved('/settings')} className="font-medium text-primary underline underline-offset-2">{t('talk.howToFix')}</Link>
              </p>
            ) : null
          ) : (
            <p className="text-xs text-muted-foreground" data-testid="voice-support">
              {voice.serverMode ? t('voice.consentServer') : voice.canListen ? t('voice.consentBrowser') : t('voice.unsupported')}
            </p>
          )}
          {!talk && voice.noLanguageVoice ? (
            <p className="text-xs text-muted-foreground" data-testid="voice-no-language" data-language={chatLanguage}>
              {t(`voice.noLanguageVoice.${chatLanguage}`)}
            </p>
          ) : null}
          {!talk && voice.noVoice ? (
            <p className="text-xs text-muted-foreground" data-testid={persona.gender === 'female' ? 'voice-no-female' : 'voice-no-male'}>
              {t(persona.gender === 'female' ? 'voice.noFemaleVoice' : 'voice.noMaleVoice', { name: persona.name[appLanguage] })}
            </p>
          ) : null}
        </form>
      ) : null}
    </div>
  );
}

export function AssistantPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { persona } = usePersona();
  return (
    <Dialog open={open} onClose={onClose} title={t('assistant.title', { name: persona.name[language] })} description={t('assistant.subtitle')} placement="end">
      <AssistantChat onClose={onClose} active={open} />
    </Dialog>
  );
}
