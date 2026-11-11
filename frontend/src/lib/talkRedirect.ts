/**
 * The old Talk screen is gone: /talk opens the one Al Mulhim conversation (/assistant). Only
 * parameters the conversation understands are carried over: the data mode (a known value) and a
 * question to prefill, which is never sent by itself. Anything else is dropped. Pure, so it is
 * tested on its own (tests/talk-redirect.test.mjs).
 */
export function talkRedirectSearch(search: string): string {
  const from = new URLSearchParams(search);
  const kept = new URLSearchParams();
  const mode = from.get('mode');
  if (mode === 'synthetic' || mode === 'verified') kept.set('mode', mode);
  const question = from.get('q');
  if (question && question.trim()) kept.set('q', question.slice(0, 1000));
  return kept.size ? `?${kept.toString()}` : '';
}
