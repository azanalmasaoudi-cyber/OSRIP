import { useCallback, useEffect, useRef, useState } from 'react';

import { speakSegment } from '@/api/assistant';
import type { NarrationSegment } from '@/api/studyEvents';
import { useAssistantUi } from '@/components/assistant/AssistantContext';
import { speak, stopSpeaking, voiceFor, type PersonaGender } from '@/lib/speech';
import { playAudio, type Playback } from '@/lib/voicePlayer';

/**
 * Reads a study's narration one segment at a time, in the voice of the persona who answered:
 * server speech (one request per segment) or the browser's own voice, else step-through only.
 * Because each segment is played on its own, the segment being read is known from real
 * playback events (start and end of that segment), and the rows it is about are highlighted.
 * There is no word-level timing: highlighting follows sentences, never words.
 */
export type NarrationMode = 'server' | 'browser' | 'manual';

export function useNarration({ segments, messageId, language, gender, serverSpeech }: {
  segments: readonly NarrationSegment[];
  messageId: number | null;
  language: 'en' | 'ar';
  gender: PersonaGender;
  serverSpeech: boolean;
}) {
  const { setActivity, reportError } = useAssistantUi();
  const [index, setIndex] = useState<number | null>(null); // the segment highlighted
  const [playing, setPlaying] = useState(false);
  const [failed, setFailed] = useState(false);
  const run = useRef(0); // bumped by every stop: a late callback of an old run does nothing
  const playback = useRef<Playback | null>(null);
  const aborter = useRef<AbortController | null>(null);
  const mode: NarrationMode = serverSpeech && messageId !== null ? 'server' : voiceFor(language, gender) ? 'browser' : 'manual';

  const halt = useCallback(() => {
    run.current += 1;
    aborter.current?.abort();
    aborter.current = null;
    playback.current?.stop();
    playback.current = null;
    stopSpeaking();
    setPlaying(false);
  }, []);

  useEffect(() => setActivity('speaking', playing), [playing, setActivity]);
  // A different study (or narration) stops the current one and starts unhighlighted.
  useEffect(() => () => halt(), [segments, halt]);
  const [shownFor, setShownFor] = useState(segments);
  if (shownFor !== segments) {
    // Adjusting state while rendering (React docs pattern), instead of an effect.
    setShownFor(segments);
    setIndex(null);
    setFailed(false);
  }

  const playFrom = useCallback((start: number) => {
    halt();
    if (mode === 'manual' || start >= segments.length) {
      setIndex(Math.min(start, segments.length - 1));
      return;
    }
    const mine = ++run.current;
    setPlaying(true);
    setFailed(false);
    const step = (i: number) => {
      if (run.current !== mine) return;
      const segment = segments[i];
      if (!segment) {
        setPlaying(false);
        return;
      }
      setIndex(i);
      const next = () => {
        if (run.current === mine) step(i + 1);
      };
      const fail = () => {
        if (run.current !== mine) return;
        setPlaying(false);
        setFailed(true);
        reportError();
      };
      if (mode === 'server' && messageId !== null) {
        const controller = new AbortController();
        aborter.current = controller;
        speakSegment(messageId, segment.narration_segment_id, language, controller.signal)
          .then((audio) => {
            if (run.current !== mine) return;
            playback.current = playAudio(audio, { onStart: () => undefined, onLevel: () => undefined, onEnd: next, onError: fail });
          })
          .catch(() => {
            if (!controller.signal.aborted) fail();
          });
      } else if (!speak(segment.text, language, gender, { onStart: () => undefined, onEnd: next, onError: fail })) {
        fail();
      }
    };
    step(start);
  }, [halt, mode, segments, messageId, language, gender, reportError]);

  return {
    mode,
    index,
    playing,
    failed,
    current: index === null ? null : (segments[index] ?? null),
    play: () => playFrom(index ?? 0),
    playFrom,
    stop: halt,
    select: (i: number) => {
      halt();
      setIndex(i);
    },
  };
}
