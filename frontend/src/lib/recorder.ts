/**
 * Microphone recording for the server speech service (booklet 3.34).
 *
 * The microphone is requested only inside start(), which is called from the user's click
 * on the microphone button. Audio is captured in memory, downsampled to 16 kHz mono and
 * encoded as PCM WAV (the format the speech service's short-audio API accepts), then
 * handed to the caller once. Nothing is saved in the browser; the tracks are stopped as
 * soon as recording ends so the browser's microphone indicator goes off.
 */

const TARGET_RATE = 16000;

export type RecorderError = 'denied' | 'unsupported' | 'no_device' | 'failed';

export function recordingSupported(): boolean {
  return typeof navigator !== 'undefined'
    && typeof navigator.mediaDevices?.getUserMedia === 'function'
    && typeof window !== 'undefined'
    && ('AudioContext' in window || 'webkitAudioContext' in window);
}

export interface Recording {
  /** Stop and return the WAV; resolves null when nothing usable was recorded. */
  stop(): Promise<Blob | null>;
  /** Stop and discard everything. */
  cancel(): void;
}

function downsample(input: Float32Array, fromRate: number): Float32Array {
  if (fromRate === TARGET_RATE) return input;
  const ratio = fromRate / TARGET_RATE;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += input[j] ?? 0;
    out[i] = end > start ? sum / (end - start) : 0;
  }
  return out;
}

export function encodeWav(samples: Float32Array, rate = TARGET_RATE): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const write = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };
  write(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  write(8, 'WAVE');
  write(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i += 1) {
    const s = Math.max(-1, Math.min(1, samples[i] ?? 0));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

/**
 * Opens the microphone and records until stop(), cancel() or maxSeconds. onLevel reports
 * the input level (0-1) for a visible meter; onLimit fires when maxSeconds is reached.
 */
export async function startRecording(options: {
  maxSeconds: number;
  onLevel?: (level: number) => void;
  onLimit?: () => void;
}): Promise<Recording> {
  if (!recordingSupported()) {
    const code: RecorderError = 'unsupported';
    throw Object.assign(new Error(code), { code });
  }
  // Created synchronously, inside the user's click: an AudioContext created after the
  // permission prompt (outside the gesture) starts suspended and records silence.
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const context = new Ctor();
  const resumed = context.resume();
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    await resumed;
  } catch (error) {
    void context.close();
    const name = (error as { name?: string }).name;
    const code: RecorderError = name === 'NotAllowedError' || name === 'SecurityError' ? 'denied' : name === 'NotFoundError' ? 'no_device' : 'failed';
    throw Object.assign(new Error(code), { code });
  }
  const source = context.createMediaStreamSource(stream);
  // ScriptProcessorNode is deprecated but universally available and needs no extra module file.
  const processor = context.createScriptProcessor(4096, 1, 1);
  const chunks: Float32Array[] = [];
  let length = 0;
  let done = false;
  const maxSamples = options.maxSeconds * context.sampleRate;

  const finish = () => {
    if (done) return;
    done = true;
    processor.disconnect();
    source.disconnect();
    stream.getTracks().forEach((t) => t.stop());
    void context.close();
  };

  processor.onaudioprocess = (event) => {
    if (done) return;
    const data = new Float32Array(event.inputBuffer.getChannelData(0));
    chunks.push(data);
    length += data.length;
    if (options.onLevel) {
      let peak = 0;
      for (let i = 0; i < data.length; i += 64) peak = Math.max(peak, Math.abs(data[i] ?? 0));
      options.onLevel(Math.min(1, peak * 1.6));
    }
    if (length >= maxSamples) options.onLimit?.();
  };
  source.connect(processor);
  processor.connect(context.destination);

  return {
    stop: () => {
      const rate = context.sampleRate;
      finish();
      if (length < rate * 0.3) return Promise.resolve(null);
      const merged = new Float32Array(Math.min(length, maxSamples));
      let offset = 0;
      for (const chunk of chunks) {
        if (offset >= merged.length) break;
        merged.set(chunk.subarray(0, merged.length - offset), offset);
        offset += chunk.length;
      }
      chunks.length = 0;
      return Promise.resolve(encodeWav(downsample(merged, rate)));
    },
    cancel: () => {
      finish();
      chunks.length = 0;
    },
  };
}
