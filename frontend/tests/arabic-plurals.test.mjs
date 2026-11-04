import assert from 'node:assert/strict';
import { test } from 'node:test';
import i18next from 'i18next';
import { ar } from '../src/i18n/locales/ar.ts';
import { en } from '../src/i18n/locales/en.ts';

// Every plural key (English "_one"/"_other") must resolve in Arabic for every count, in Arabic's
// own form: i18next looks for the count's form (zero, one, two, few, many, other) and, without it,
// shows the English text instead.

function pluralKeys(node, path = []) {
  return Object.entries(node).flatMap(([key, value]) => {
    if (typeof value !== 'string') return pluralKeys(value, [...path, key]);
    return key.endsWith('_other') ? [[...path, key.slice(0, -'_other'.length)].join('.')] : [];
  });
}

const KEYS = pluralKeys(en);
const COUNTS = [0, 1, 2, 3, 7, 10, 11, 25, 99, 100, 101, 102, 1000];
const LATIN = /[A-Za-z]/;

async function arabic() {
  const instance = i18next.createInstance();
  // No fallback language: a missing Arabic form shows the key itself, never English.
  await instance.init({
    resources: { en: { translation: en }, ar: { translation: ar } },
    lng: 'ar',
    fallbackLng: false,
    interpolation: { escapeValue: false },
  });
  return instance;
}

test('there are plural keys to check', () => {
  assert.ok(KEYS.length >= 4, KEYS.join(', '));
});

test('every plural key resolves in Arabic for every count', async () => {
  const t = (await arabic()).t;
  for (const key of KEYS) {
    for (const count of COUNTS) {
      const text = t(key, { count });
      assert.notEqual(text, key, `${key} has no Arabic form for ${count}`);
      assert.ok(!LATIN.test(text), `${key} (${count}) is not Arabic: ${text}`);
      // The number is written, except where Arabic says it in words (none, one, two).
      if (count > 2) assert.ok(text.includes(String(count)), `${key} (${count}) lacks the number: ${text}`);
    }
  }
});

test('the forms differ where Arabic grammar does', async () => {
  const t = (await arabic()).t;
  for (const key of KEYS) {
    // Dual, plural (3–10), accusative singular (11–99) and genitive singular (100+).
    const forms = new Set([2, 3, 11, 100].map((count) => t(key, { count }).replace(String(count), '#')));
    assert.equal(forms.size, 4, `${key}: ${[...forms].join(' | ')}`);
  }
});

test('the application setup shows Arabic, not the English fallback', async () => {
  const instance = i18next.createInstance();
  await instance.init({
    resources: { en: { translation: en }, ar: { translation: ar } },
    lng: 'ar',
    fallbackLng: 'en',
    interpolation: { escapeValue: false },
  });
  for (const key of KEYS) {
    for (const count of COUNTS) {
      assert.ok(!LATIN.test(instance.t(key, { count })), `${key} (${count}) fell back to English`);
    }
  }
});
