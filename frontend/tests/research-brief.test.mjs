import assert from 'node:assert/strict';
import { test } from 'node:test';
import { BRIEF_DOMAINS, BRIEF_GOALS, BRIEF_MODE, buildResearchBrief, briefDomains } from '../src/lib/researchBrief.ts';
import { voiceGender, pickVoice } from '../src/lib/speech.ts';

for (const language of ['ar', 'en']) {
  test(`All research templates fit the message budget and include evidence constraints (${language})`, () => {
    for (const domain of BRIEF_DOMAINS) for (const goal of BRIEF_GOALS) {
      const draft = buildResearchBrief(language, domain, goal);
      assert.ok(draft.length <= 1000);
      assert.ok(draft.includes(briefDomains[language][domain]));
      assert.ok(draft.includes(language === 'ar' ? '٢٠٢٢' : '2022'));
      assert.ok(draft.includes(language === 'ar' ? 'المراجع' : 'source links'));
      assert.ok(draft.includes(language === 'ar' ? 'فلا تتنبأ' : 'do not forecast'));
    }
  });
}
test('Each goal selects an existing answer mode', () => {
  assert.deepEqual(BRIEF_MODE, { trend: 'analyze', drivers: 'analyze', scenario: 'scenario', research: 'research' });
  for (const goal of BRIEF_GOALS) assert.ok(['ask', 'analyze', 'research', 'compare', 'scenario'].includes(BRIEF_MODE[goal]));
});
test('Do not assign a gender to unidentified Google voices', () => {
  assert.equal(voiceGender('Google العربية'), 'unknown');
  assert.equal(voiceGender('Google UK English Female'), 'female');
  assert.equal(voiceGender('Google UK English Male'), 'male');
});
test('Voice selection keeps both language and persona constraints', () => {
  const voices = [
    { name: 'Microsoft Abdullah Online', lang: 'ar-OM' },
    { name: 'Microsoft Aysha Online', lang: 'ar-OM' },
    { name: 'Google UK English Male', lang: 'en-GB' },
    { name: 'Google العربية', lang: 'ar-SA' },
  ];
  assert.equal(pickVoice(voices, 'ar', 'male').name, 'Microsoft Abdullah Online');
  assert.equal(pickVoice(voices, 'ar', 'female').name, 'Microsoft Aysha Online');
  assert.equal(pickVoice(voices, 'en', 'female'), null);
  assert.equal(pickVoice([voices[2]], 'ar', 'male'), null);
});
