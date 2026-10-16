/**
 * Voice adapters (booklet 3.34), separate from the answer service.
 *
 * Both use the browser's built-in Web Speech API; OSRIP's server never receives audio
 * and nothing is recorded or stored by OSRIP. In Chrome and Edge the browser sends the
 * audio to its vendor's online speech service; the panel says so before the microphone
 * is used. Features are offered only when the browser actually provides them:
 *  - recognition: SpeechRecognition / webkitSpeechRecognition;
 *  - synthesis: speechSynthesis with an installed voice of the persona's gender for the chosen
 *    language (Al Mulhim: a man's voice; Ilham: a woman's voice; Arabic is never read with an
 *    English voice, and a persona never with a voice of the other gender).
 * The microphone opens only inside start(), which is called from a user's click.
 */

export type SpeechLanguage = 'en' | 'ar';

const LOCALE: Record<SpeechLanguage, string> = { en: 'en-GB', ar: 'ar-OM' };

interface RecognitionResultEvent {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
}

interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: RecognitionResultEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}

type RecognitionConstructor = new () => Recognition;

function recognitionConstructor(): RecognitionConstructor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function recognitionSupported(): boolean {
  return recognitionConstructor() !== null;
}

export function synthesisSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
}

/*
 * Each persona speaks only with a voice of its own gender: Al Mulhim a man's, Ilham a woman's.
 * Browsers do not report a voice's gender, so voices are recognised by the given names used by
 * Windows, Edge's online voices, macOS and Chrome. A voice not known to be of the persona's
 * gender is never used: if a browser has none for a language, nothing is read aloud and the
 * panel says why.
 */
const MALE_NAMES = new Set([
  // Arabic
  'abdullah', 'hamed', 'naayf', 'shakir', 'hamdan', 'fahed', 'moaz', 'taim', 'bassel', 'rami',
  'jamal', 'ali', 'saleh', 'omar', 'ismael', 'laith', 'hedi', 'maged', 'majed', 'tarik',
  // English
  'ryan', 'thomas', 'george', 'david', 'mark', 'guy', 'christopher', 'eric', 'roger', 'steffan',
  'andrew', 'brian', 'daniel', 'alex', 'fred', 'oliver', 'william', 'james', 'ethan', 'alfie',
  'elliot', 'noah', 'connor', 'liam', 'mitchell', 'neil', 'luke', 'ken', 'sam', 'wayne',
  'aaron', 'arthur', 'oscar', 'rishi', 'prabhat', 'tony', 'davis', 'jason', 'reed', 'ralph',
]);
const FEMALE_NAMES = new Set([
  'hoda', 'zariyah', 'aysha', 'salma', 'laila', 'amany', 'sana', 'mouna', 'iman', 'noura',
  'fatima', 'rana', 'layla', 'reem', 'amira', 'mariam', 'huda', 'hala', 'dalia', 'zira',
  'hazel', 'susan', 'sonia', 'libby', 'maisie', 'abbi', 'bella', 'hollie', 'olivia', 'aria',
  'jenny', 'michelle', 'ana', 'emma', 'ava', 'sara', 'nancy', 'amber', 'ashley', 'cora',
  'elizabeth', 'jane', 'monica', 'samantha', 'karen', 'moira', 'tessa', 'victoria', 'fiona',
  'kate', 'serena', 'martha', 'catherine', 'natasha', 'clara', 'emily', 'neerja', 'leah',
]);

export type VoiceGender = 'male' | 'female' | 'unknown';

/** Gender from the voice's name ("Microsoft Abdullah Online (Natural) - Arabic (Oman)"). */
export function voiceGender(name: string): VoiceGender {
  const lower = name.toLowerCase();
  if (/\bfemale\b/.test(lower)) return 'female';
  if (/\bmale\b/.test(lower)) return 'male'; // "Google UK English Male"
  // Unnamed voices ("Google العربية", "Google US English") stay unknown: their gender is not
  // stated, so they are never used for either persona.
  const words = lower.split(/[^a-z]+/).filter(Boolean);
  if (words.some((w) => FEMALE_NAMES.has(w))) return 'female';
  if (words.some((w) => MALE_NAMES.has(w))) return 'male';
  return 'unknown';
}

export type PersonaGender = 'male' | 'female';

/** The best installed voice of this gender for the language (the Omani or British locale
 * first, natural voices next), or null. */
export function pickVoice(voices: readonly SpeechSynthesisVoice[], language: SpeechLanguage, gender: PersonaGender): SpeechSynthesisVoice | null {
  const prefix = language === 'ar' ? 'ar' : 'en';
  const exact = LOCALE[language].toLowerCase();
  const matching = voices.filter((v) => v.lang.toLowerCase().startsWith(prefix) && voiceGender(v.name) === gender);
  const score = (v: SpeechSynthesisVoice) =>
    (v.lang.toLowerCase() === exact ? 2 : 0) + (/natural|online|neural/i.test(v.name) ? 1 : 0);
  return matching.sort((a, b) => score(b) - score(a))[0] ?? null;
}

/** An installed voice of this gender for the language, or null (voices load asynchronously in
 * some browsers). */
export function voiceFor(language: SpeechLanguage, gender: PersonaGender): SpeechSynthesisVoice | null {
  if (!synthesisSupported()) return null;
  return pickVoice(window.speechSynthesis.getVoices(), language, gender);
}

/** True when the browser has voices for the language but none of this gender. */
export function noVoiceOfGender(language: SpeechLanguage, gender: PersonaGender): boolean {
  if (!synthesisSupported()) return false;
  const prefix = language === 'ar' ? 'ar' : 'en';
  const forLanguage = window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith(prefix));
  return forLanguage.length > 0 && pickVoice(forLanguage, language, gender) === null;
}

/** Calls back whenever the browser's voice list changes (Chrome loads it lazily). */
export function onVoicesChanged(callback: () => void): () => void {
  if (!synthesisSupported()) return () => undefined;
  window.speechSynthesis.addEventListener('voiceschanged', callback);
  return () => window.speechSynthesis.removeEventListener('voiceschanged', callback);
}

/** Recognition error codes that mean the microphone or service is not available to us. */
export const PERMISSION_ERRORS = new Set(['not-allowed', 'service-not-allowed']);

export interface Recognizer {
  start(): void;
  stop(): void;
  abort(): void;
}

export function createRecognizer(
  language: SpeechLanguage,
  handlers: { onText: (text: string, isFinal: boolean) => void; onError: (code: string) => void; onEnd: () => void },
): Recognizer | null {
  const Ctor = recognitionConstructor();
  if (!Ctor) return null;
  const recognition = new Ctor();
  recognition.lang = LOCALE[language];
  recognition.interimResults = true;
  recognition.continuous = false; // one question per press; the user reviews it before sending
  recognition.maxAlternatives = 1;
  let finalText = '';
  recognition.onresult = (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      if (!result) continue;
      if (result.isFinal) finalText += result[0].transcript;
      else interim += result[0].transcript;
    }
    handlers.onText((finalText + interim).trim(), interim === '');
  };
  recognition.onerror = (event) => handlers.onError(event.error);
  recognition.onend = () => handlers.onEnd();
  return {
    start: () => recognition.start(),
    stop: () => recognition.stop(),
    abort: () => recognition.abort(),
  };
}

/** Reads text aloud with a voice of the persona's gender; returns false (and does nothing) when
 * the browser has no such voice for the language. */
export function speak(
  text: string,
  language: SpeechLanguage,
  gender: PersonaGender,
  handlers: { onStart: () => void; onEnd: () => void; onError: (code: string) => void },
): boolean {
  const voice = voiceFor(language, gender);
  if (!voice) return false;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = voice.lang || LOCALE[language];
  utterance.voice = voice;
  utterance.onstart = handlers.onStart;
  utterance.onend = handlers.onEnd;
  utterance.onerror = (event) => {
    // 'interrupted' / 'canceled' come from our own stop button, not a failure.
    if (event.error === 'interrupted' || event.error === 'canceled') handlers.onEnd();
    else handlers.onError(event.error);
  };
  window.speechSynthesis.speak(utterance);
  return true;
}

export function stopSpeaking(): void {
  if (synthesisSupported()) window.speechSynthesis.cancel();
}
