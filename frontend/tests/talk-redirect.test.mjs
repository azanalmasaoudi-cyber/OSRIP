import assert from 'node:assert/strict';
import { test } from 'node:test';
import { talkRedirectSearch } from '../src/lib/talkRedirect.ts';

test('the data mode and a question to prefill are kept', () => {
  assert.equal(talkRedirectSearch('?mode=synthetic'), '?mode=synthetic');
  assert.equal(talkRedirectSearch('?mode=verified&q=Water+in+2025'), '?mode=verified&q=Water+in+2025');
});

test('anything else is dropped, including an unknown mode and an empty question', () => {
  assert.equal(talkRedirectSearch(''), '');
  assert.equal(talkRedirectSearch('?mode=admin&persona=ilham&call=1&q=%20'), '');
  assert.equal(talkRedirectSearch('?voice=on&mode=synthetic'), '?mode=synthetic');
});

test('a long question is cut to the message limit', () => {
  const q = 'a'.repeat(1500);
  const kept = new URLSearchParams(talkRedirectSearch(`?q=${q}`)).get('q');
  assert.equal(kept.length, 1000);
});
