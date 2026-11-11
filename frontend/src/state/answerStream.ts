import { useEffect, useReducer } from 'react';

import { adapterKind } from '@/api/config';
import { studyEventsUrl, TERMINAL } from '@/api/studyEvents';
import { answerReducer, EMPTY_ANSWER, type AnswerStream } from '@/lib/answerStreamState';

export type { AnswerPhase, AnswerStream } from '@/lib/answerStreamState';

/**
 * The answer to one question as the server streams it (backend assistant/streaming.py): the
 * stage reached and the checked sentences written so far, in order. Each event is applied once
 * (by ``seq``, so a reconnect that resumes from the last event changes nothing); ``answer.reset``
 * starts the text again (an attempt was replaced). The stored reply replaces this when it
 * arrives: this is only the view while it is written.
 */

/** Follows one question's stream while it is answered. ``requestId`` null: nothing open. */
export function useAnswerStream(requestId: string | null, guest: boolean): AnswerStream & { live: boolean } {
  const [state, dispatch] = useReducer(answerReducer, EMPTY_ANSWER);
  const live = Boolean(requestId) && adapterKind === 'http' && typeof EventSource !== 'undefined';
  useEffect(() => {
    dispatch({ type: 'open' });
    if (!requestId || !live) return undefined;
    // The request row appears a moment after sending; the server waits for it before streaming.
    const source = new EventSource(studyEventsUrl(requestId, guest), { withCredentials: true });
    const onEvent = (message: MessageEvent<string>) => {
      try {
        dispatch({ type: 'event', raw: JSON.parse(message.data) });
      } catch {
        return;
      }
      if (TERMINAL.has(message.type)) source.close();
    };
    for (const t of ['stage', 'answer.segment', 'answer.reset', ...TERMINAL]) source.addEventListener(t, onEvent as EventListener);
    source.addEventListener('end', () => {
      source.close();
      dispatch({ type: 'end' });
    });
    return () => source.close();
  }, [requestId, guest, live]);
  return { ...state, live };
}
