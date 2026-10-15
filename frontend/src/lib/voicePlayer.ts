/**
 * Plays synthesised speech (MP3 from the server) and reports its loudness while it plays,
 * so the avatar can move with the actual audio. This is an amplitude-driven speaking
 * animation, not lip synchronisation: no phonemes or visemes are available.
 *
 * The audio element plays on its own; the level meter listens to a captured copy of its
 * output (captureStream), so a suspended or unavailable AudioContext can only stop the
 * animation, never the sound. Where captureStream is missing (Safari), the avatar shows
 * the speaking state without level movement.
 * Nothing autoplays: play() is only called after the user's own action (asking by voice
 * or pressing "Read aloud").
 */

export interface Playback {
  stop(): void;
}

type CapturableAudio = HTMLAudioElement & { captureStream?: () => MediaStream; mozCaptureStream?: () => MediaStream };

export function playAudio(
  blob: Blob,
  handlers: { onStart: () => void; onLevel: (level: number) => void; onEnd: () => void; onError: () => void },
): Playback {
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url) as CapturableAudio;
  let context: AudioContext | null = null;
  let frame = 0;
  let ended = false;

  const cleanup = () => {
    if (ended) return;
    ended = true;
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
        handlers.onLevel(Math.min(1, Math.sqrt(sum / data.length) * 4));
        frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    } catch {
      handlers.onLevel(0); // the audio keeps playing without the level meter
    }
  };

  audio.addEventListener('playing', () => {
    handlers.onStart();
    startMeter();
  });
  audio.addEventListener('ended', () => { cleanup(); handlers.onEnd(); });
  audio.addEventListener('error', () => { cleanup(); handlers.onError(); });
  audio.play().catch(() => { cleanup(); handlers.onError(); });

  return {
    stop: () => {
      if (ended) return;
      cleanup();
      handlers.onEnd();
    },
  };
}
