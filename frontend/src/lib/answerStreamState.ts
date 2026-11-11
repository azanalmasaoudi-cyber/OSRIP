import { z } from 'zod';

/**
 * The state of one streamed answer, rebuilt from its events (backend assistant/streaming.py):
 * each event applied once, by ``seq``; segments in order; ``answer.reset`` starts the text
 * again; nothing after the end. Pure, so it is tested on its own (tests/answer-stream.test.mjs).
 */

export type AnswerPhase = 'starting' | 'planning' | 'searching' | 'reading' | 'analysing' | 'preparing' | 'writing' | 'checking' | 'done';

export interface AnswerStream {
  phase: AnswerPhase;
  /** The latest stage as the server names it (workflow.stage.*). */
  stage: string | null;
  text: string;
  segments: number;
  lastSeq: number;
  ended: boolean;
}

export const EMPTY_ANSWER: AnswerStream = { phase: 'starting', stage: null, text: '', segments: 0, lastSeq: 0, ended: false };

const PHASE: Record<string, AnswerPhase> = {
  received: 'starting',
  planning: 'planning',
  web_search: 'searching',
  reading: 'reading',
  // Tables, charts, diagrams and an illustration are prepared before the text is written.
  visuals: 'preparing',
  image: 'preparing',
  writing: 'writing',
  checking: 'checking',
  done: 'done',
};

const envelope = z.object({ seq: z.number().int().positive() });
const stage = envelope.extend({ type: z.literal('stage'), payload: z.object({ stage: z.string() }) });
const segment = envelope.extend({
  type: z.literal('answer.segment'), payload: z.object({ index: z.number().int().min(0), text: z.string() }),
});
const reset = envelope.extend({ type: z.literal('answer.reset') });
const terminal = envelope.extend({ type: z.enum(['study.completed', 'study.cancelled', 'study.failed']) });
const event = z.discriminatedUnion('type', [stage, segment, reset, terminal]);

export type AnswerAction = { type: 'open' } | { type: 'event'; raw: unknown } | { type: 'end' };

export function answerReducer(state: AnswerStream, action: AnswerAction): AnswerStream {
  if (action.type === 'open') return EMPTY_ANSWER;
  if (action.type === 'end') return { ...state, ended: true };
  const parsed = event.safeParse(action.raw);
  if (!parsed.success || parsed.data.seq <= state.lastSeq || state.ended) return state;
  const e = parsed.data;
  const next = { ...state, lastSeq: e.seq };
  switch (e.type) {
    case 'stage':
      // Any other step (data, calculation, tables, plan) is analysis.
      return { ...next, stage: e.payload.stage, phase: PHASE[e.payload.stage] ?? 'analysing' };
    case 'answer.segment':
      // Segments arrive in order; one out of order (never sent by the server) is not shown.
      if (e.payload.index !== state.segments) return next;
      return { ...next, phase: 'writing', text: state.text + e.payload.text, segments: state.segments + 1 };
    case 'answer.reset':
      return { ...next, text: '', segments: 0 };
    default:
      return { ...next, phase: 'done', ended: true };
  }
}
