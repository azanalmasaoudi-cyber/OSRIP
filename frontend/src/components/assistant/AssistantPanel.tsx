import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useAssistantUi } from './AssistantContext';
import { ChatView } from './ChatView';
import { usePersona } from './persona';
import { ResearchBriefBuilder } from './ResearchBriefBuilder';
import {
  isInternetMode,
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
  type AssistantMessage,
  type AssistantMode,
  type RequestMode,
  type AskSelection,
} from '@/api/assistant';
import { hasPermission, useMe } from '@/api/auth';
import { ApiRequestError } from '@/api/client';
import { Button } from '@/components/ui/button';
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
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';

// Kept across sign-in (same tab): the unsent draft and the guest conversation.
const DRAFT_KEY = 'osrip.assistant.draft';
const GUEST_CONVERSATION_KEY = 'osrip.assistant.guestConversation';
const MUTE_KEY = 'osrip.assistant.muted';
const WEB_KEY = 'osrip.assistant.web';

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

function SignInPrompt({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  return (
    <div className="flex flex-col gap-3 rounded-md border border-copper/40 bg-copper-subtle/40 p-4 text-sm" data-testid="assistant-sign-in" role="status">
      <p className="font-semibold">{t('guest.limitReachedTitle')}</p>
      <p>{t('guest.limitReached')}</p>
      <div className="flex flex-wrap gap-2">
        <Link to={to('/sign-in')} onClick={onNavigate} className="rounded-md bg-primary px-3 py-2 font-medium text-primary-foreground" data-testid="guest-sign-in">
          {t('auth.signIn')}
        </Link>
        <Link to={to('/register')} onClick={onNavigate} className="rounded-md border border-border-strong px-3 py-2 font-medium"
          data-testid="guest-register">
          {t('account.createAccount')}
        </Link>
      </div>
      <p className="text-xs text-muted-foreground">{t('guest.keptNote')}</p>
    </div>
  );
}

// ------------------------------------------------------------------ the chat

/** Asks a question from outside the chat (a suggested question, or "Run analysis"). */
export type AskFromOutside = (question: string, mode?: AssistantMode) => void;

/**
 * The one Al Mulhim conversation: its state and actions, drawn by ChatView. "page" is the AI
 * Assistant page (with the conversation history beside it); "embedded" is the same chat in the
 * workspace's assistant column, compact, where a reply's study opens beside it.
 */
export function AssistantChat({ initialDraft = '', active = true, askRef, selection = null, selectionLabel, layout = 'page', tools }: {
  initialDraft?: string;
  /** Asked from a sector page: its applied selection, sent with each question until removed. */
  selection?: AskSelection | null;
  selectionLabel?: string;
  active?: boolean;
  layout?: 'page' | 'embedded';
  /** Page tools for the Tools menu (analysis, a full study). */
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
  const [viaVoice, setViaVoice] = useState(false);
  const last = useRef<{ text: string; requestId: string; mode: RequestMode } | null>(null);
  // The question being answered (shown at once on the conversation page) and the size of the
  // conversation when it was sent: it is shown until the conversation returns it.
  const [asked, setAsked] = useState<{ text: string; requestId: string; base: number; echo: boolean } | null>(null);
  const spokenFor = useRef<number | null>(null);
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
  // The conversation asks with "auto" (the server infers the kind of answer from the question:
  // internet research, a quick answer, or analysis of OSRIP's data) unless the person picks one
  // in Tools, for this visit only. Beside the workspace's analysis it starts from data analysis.
  const [chatMode, setChatMode] = useState<RequestMode>(layout === 'embedded' ? 'ask' : 'auto');
  const effectiveMode: RequestMode = chatMode;
  // The internet modes always search the web; the data modes only with the switch on.
  const webResearch = webAvailable && (webOn || isInternetMode(effectiveMode));
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
    const askAsGuest = () => guestAsk.mutate(
      {
        content: text, language: chatLanguage, request_id: requestId, conversation_id: guestId, data_mode: mode,
        web_research: webResearch, mode: askMode, persona: persona.code, cross_check: checked, selection: scoped,
      },
      { onSuccess: (result) => setGuestId(result.conversation_id) },
    );
    // A guest's first question waits for the guest session (its cookie), which a page opened a
    // moment ago may still be requesting; it is then sent, never refused as expired.
    if (guestStatus.data) askAsGuest();
    else void guestStatus.refetch().finally(askAsGuest);
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
  // A question that could not be sent goes back into the box (unless the person has typed
  // something new), so nothing is lost; Retry sends it again.
  const [seenError, setSeenError] = useState<unknown>(null);
  if (error && error !== seenError) {
    setSeenError(error);
    if (!draft && asked) setDraftState(asked.text);
  }

  // A reply's study: beside the chat in the workspace; from the assistant page, it opens there.
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const preserved = usePreservedSearch();
  const openStudyHere = (id: string) => {
    ui.openStudy(id, !signedIn);
    if (pathname !== '/workspace') void navigate(preserved('/workspace'));
  };

  const suggestions = status.data?.suggestions[chatLanguage] ?? [];
  const canAsk = signedIn ? allowed : true;
  const linkable = signedIn && guestStatus.data?.authenticated === true && guestStatus.data.linkable_history && !link.isSuccess;
  const speakHandler = voice.canSpeak && !voice.muted
    ? (m: AssistantMessage) => voice.say(m, byCode(m.persona).gender)
    : null;
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
  // A study request to review and edit (Tools): it fills the box and the mode, and sends nothing.
  const brief = (
    <ResearchBriefBuilder language={chatLanguage} disabled={pending || needsAccount} maxLength={max}
      onDraft={(text, briefMode) => {
        setDraft(text);
        setChatMode(briefMode);
        setViaVoice(false);
        document.getElementById(inputId)?.focus();
      }} />
  );

  const asking = asked && !error && (pending || messages.length <= asked.base)
    ? { text: asked.text, requestId: asked.requestId, echo: asked.echo } : null;
  const embedded = layout === 'embedded';
  return (
    <ChatView layout={layout} chat={{
      language: chatLanguage,
      setLanguage: (l) => { pickedLanguage.current = true; setChatLanguage(l); },
      dataMode: (signedIn ? conversation.data?.data_mode : guestConversation.data?.data_mode) ?? mode,
      messages, pending, asking, guest: !signedIn, error, send, retry,
      draft, type: (text) => { setDraft(text); setViaVoice(false); }, max, inputId, viaVoice,
      canAsk, needsAccount, signedIn, allowance, signInPrompt: <SignInPrompt />,
      voice, speak: speakHandler,
      web: { available: webAvailable, on: webOn, set: (on) => { setWebOn(on); writeStore('local', WEB_KEY, on ? null : '0'); } },
      mode: { value: chatMode, set: setChatMode },
      crossCheck: { available: crossCheckAvailable, on: crossCheckOn, set: setCrossCheckOn },
      conversations: signedIn && allowed ? {
        list: conversations.data ?? [], activeId, removing: remove.isPending, loading: conversations.isPending,
        select: (id) => { setActiveId(id); setAsked(null); },
        remove: (id) => remove.mutate(id, { onSuccess: () => { if (id === activeId) setActiveId(null); } }),
      } : null,
      guestConversationId: signedIn ? null : guestId,
      newConversation: () => { if (signedIn) setActiveId(null); else setGuestId(null); setAsked(null); },
      linkPrompt: linkUi,
      memory: { guestExpires: guestData?.expires_at ?? null, guestConversationId: signedIn ? null : guestId,
        onGuestDeleted: () => setGuestId(null), onAllDeleted: () => setActiveId(null) },
      selection: { value: scope, label: selectionLabel, clear: () => setScope(null) },
      // In the workspace a reply's study shows beside the chat; elsewhere it opens there.
      brief, suggestions, tools,
      openStudy: embedded ? (id) => ui.openStudy(id, !signedIn) : openStudyHere,
      activeStudyId: embedded ? ui.activeStudy?.id ?? null : null,
    }} />
  );
}
