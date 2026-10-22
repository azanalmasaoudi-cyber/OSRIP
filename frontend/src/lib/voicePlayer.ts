/**
 * Plays synthesised speech (MP3 from the server) and reports its loudness while it plays,
 * so the avatar can move with the actual audio. This is an amplitude-driven speaking
 * animation, not lip synchronisation: no phonemes or visemes are available.
 *
 * The audio element plays on its own; the level meter listens to a captured copy of its
 * output (captureStream), so a suspended or unavailable AudioContext can only stop the
 * animation, never the sound. Where captureStream is missing (Safari), the avatar shows
 * the speaking state without level movement.
 * Nothing autoplays: play() is only called after the user's own action (asking by voice,
 * pressing "Read aloud", "Test voice" or "Listen").
 *
 * Every playback is registered, so one "Stop audio" control can stop whatever is playing
 * anywhere on the page (a reply, a narration, a voice test). Only one thing speaks at a time:
 * starting a playback stops every other one, and any browser speech.
 */

export interface Playback {
  stop(): void;
  /** Pause where the audio element supports it; resume continues from the same point. */
  pause(): void;
  resume(): void;
  readonly paused: boolean;
}

type CapturableAudio = HTMLAudioElement & { captureStream?: () => MediaStream; mozCaptureStream?: () => MediaStream };

const active = new Set<Playback>();
const listeners = new Set<(count: number) => void>();

function changed(): void {
  for (const listener of listeners) listener(active.size);
}

/** Stops every playback started with ``playAudio`` (each reports its normal end). */
export function stopAllPlayback(): void {
  for (const p of [...active]) p.stop();
}

// Browser speech starting (lib/speech) stops every server playback too. The event name is
// repeated here so the two modules stay independent of each other.
if (typeof window !== 'undefined') window.addEventListener('osrip:exclusive-audio', () => stopAllPlayback());

/** Called with the number of playing (or paused) audio clips whenever it changes. */
export function onPlaybackChange(listener: (count: number) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function playingCount(): number {
  return active.size;
}

export function playAudio(
  blob: Blob,
  handlers: {
    onStart: () => void;
    onLevel: (level: number) => void;
    onEnd: () => void;
    onError: () => void;
    onPause?: (paused: boolean) => void;
  },
): Playback {
  stopAllPlayback(); // a new response stops the previous playback
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel();
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url) as CapturableAudio;
  let context: AudioContext | null = null;
  let frame = 0;
  let ended = false;
  let paused = false;

  const cleanup = () => {
    if (ended) return;
    ended = true;
    active.delete(playback);
    changed();
    cancelAnimationFrame(frame);
    handlers.onLevel(0);
    audio.pause();
    audio.removeAttribute('src');
    URL.revokeObjectURL(url);
    void context?.close();
  };

  const startMeter = () => {
    const capture = audio.captureStream ?? audio.mozCaptureStream;
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!capture || !Ctor || context) return;
    try {
      context = new Ctor();
      void context.resume();
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      // Not connected to the speakers: the element itself is what the user hears.
      context.createMediaStreamSource(capture.call(audio)).connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (const v of data) sum += ((v - 128) / 128) ** 2;
        handlers.onLevel(paused ? 0 : Math.min(1, Math.sqrt(sum / data.length) * 4));
        frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    } catch {
      handlers.onLevel(0); // the audio keeps playing without the level meter
    }
  };

  const playback: Playback = {
    stop: () => {
      if (ended) return;
      cleanup();
      handlers.onEnd();
    },
    pause: () => {
      if (ended || paused) return;
      audio.pause();
      paused = true;
      handlers.onLevel(0);
      handlers.onPause?.(true);
    },
    resume: () => {
      if (ended || !paused) return;
      paused = false;
      handlers.onPause?.(false);
      audio.play().catch(() => { cleanup(); handlers.onError(); });
    },
    get paused() {
      return paused;
    },
  };

  audio.addEventListener('playing', () => {
    handlers.onStart();
    startMeter();
  });
  audio.addEventListener('ended', () => { cleanup(); handlers.onEnd(); });
  audio.addEventListener('error', () => { cleanup(); handlers.onError(); });
  active.add(playback);
  changed();
  audio.play().catch(() => { cleanup(); handlers.onError(); });

  return playback;
}
