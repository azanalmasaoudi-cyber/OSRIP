import assert from 'node:assert/strict';
import { test } from 'node:test';
import { normalizeUsername, usernameProblem, USERNAME_MAX } from '../src/lib/username.ts';

test('one to ten Arabic or English letters and digits, starting with a letter', () => {
  for (const ok of ['a', 'ب', 'Salim', 'سالم', 'ab3', 'Ali_2', 'n.a-m', 'abcdefghij', 'أحمدبنعلي1']) {
    assert.equal(usernameProblem(ok), null, ok);
  }
  assert.equal(USERNAME_MAX, 10);
});

test('what the page says about a refused name', () => {
  assert.equal(usernameProblem('   '), 'username_required');
  assert.equal(usernameProblem('abcdefghijk'), 'username_too_long');
  assert.equal(usernameProblem('سالمسالمسالم'), 'username_too_long');
  for (const bad of ['9lives', 'a b', 'salimسالم', 'عـلي', 'عَلي', 'a@b.om', '+96890000']) {
    assert.equal(usernameProblem(bad), 'invalid_username', bad);
  }
});

test('spaces, presentation forms and Arabic-Indic digits are normalised as the server does', () => {
  assert.equal(normalizeUsername('  Sara  '), 'Sara');
  assert.equal(normalizeUsername('سارة٢٠٢٤'), 'سارة2024');
  assert.equal(normalizeUsername('ab۳'), 'ab3');
  assert.equal(normalizeUsername('ﺃﺣﻤﺪ'), 'أحمد');
  assert.equal(usernameProblem('  Salim  '), null, 'surrounding spaces do not count');
});
