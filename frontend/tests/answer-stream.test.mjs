import assert from 'node:assert/strict';
import { test } from 'node:test';
import { answerReducer, EMPTY_ANSWER } from '../src/lib/answerStreamState.ts';

const apply = (events, state = EMPTY_ANSWER) =>
  events.reduce((s, raw) => answerReducer(s, { type: 'event', raw }), state);
const stage = (seq, name) => ({ seq, type: 'stage', payload: { stage: name } });
const segment = (seq, index, text) => ({ seq, type: 'answer.segment', payload: { index, text } });

test('the stages map to the phases a person sees', () => {
  assert.equal(apply([stage(1, 'web_search')]).phase, 'searching');
  assert.equal(apply([stage(1, 'reading')]).phase, 'reading');
  assert.equal(apply([stage(1, 'computing')]).phase, 'analysing');
  assert.equal(apply([stage(1, 'published_data')]).phase, 'analysing');
  assert.equal(apply([stage(1, 'planning')]).phase, 'planning');
  assert.equal(apply([stage(1, 'visuals')]).phase, 'preparing');
  assert.equal(apply([stage(1, 'image')]).phase, 'preparing');
  assert.equal(apply([stage(1, 'writing')]).phase, 'writing');
  assert.equal(apply([stage(1, 'checking')]).phase, 'checking');
});

test('segments build the text in order; a repeat after a reconnect is ignored', () => {
  const s = apply([stage(1, 'writing'), segment(2, 0, 'One. '), segment(3, 1, 'Two.'), segment(3, 1, 'Two.')]);
  assert.equal(s.text, 'One. Two.');
  assert.equal(s.segments, 2);
  assert.equal(s.phase, 'writing');
});

test('an older or out-of-order event changes nothing', () => {
  const s = apply([segment(5, 0, 'A. '), segment(4, 1, 'old'), segment(6, 2, 'skipped')]);
  assert.equal(s.text, 'A. ');
});

test('a reset starts the text again; nothing is applied after the end', () => {
  let s = apply([segment(1, 0, 'First try'), { seq: 2, type: 'answer.reset', payload: { reason: 'new_attempt' } },
    segment(3, 0, 'Second.')]);
  assert.equal(s.text, 'Second.');
  s = apply([{ seq: 4, type: 'study.completed', payload: {} }, segment(5, 1, ' Late.')], s);
  assert.equal(s.ended, true);
  assert.equal(s.text, 'Second.');
  assert.equal(s.phase, 'done');
});

test('malformed events are ignored', () => {
  const s = apply([{ seq: 1, type: 'answer.segment', payload: { index: -1, text: 'x' } }, { type: 'stage' }, null]);
  assert.deepEqual(s, EMPTY_ANSWER);
});
