import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  GUIDE_STEPS, OBJECTIVES, governorateOf, hasObjectives, MAX_GOAL_LENGTH, nextStep, parseGoal, parseObjectives, parseSelection,
  parseStep, previousStep, reachableStep, writeSelection,
} from '../src/lib/guideSteps.ts';

const none = { applied: false, objectives: [], goal: '' };
const applied = { applied: true, objectives: [], goal: '' };

test('the guided analysis has five steps in a fixed order', () => {
  assert.deepEqual(GUIDE_STEPS, ['select', 'results', 'analysis', 'objectives', 'recommendations']);
  assert.equal(nextStep('select'), 'results');
  assert.equal(nextStep('analysis'), 'objectives');
  assert.equal(nextStep('recommendations'), 'recommendations');
  assert.equal(previousStep('results'), 'select');
  assert.equal(previousStep('select'), 'select');
});

test('a step is shown only when what it needs exists', () => {
  // Nothing applied yet: every step falls back to the selection.
  for (const step of GUIDE_STEPS) assert.equal(reachableStep(step, none), 'select', step);
  // With results applied, results and analysis are reachable; recommendations need an objective.
  assert.equal(reachableStep('results', applied), 'results');
  assert.equal(reachableStep('analysis', applied), 'analysis');
  assert.equal(reachableStep('recommendations', applied), 'objectives');
  assert.equal(reachableStep('recommendations', { ...applied, objectives: ['diversify'] }), 'recommendations');
  // An objective written in the person's own words counts; blank space does not.
  assert.equal(reachableStep('recommendations', { ...applied, goal: 'fewer outages' }), 'recommendations');
  assert.equal(hasObjectives({ objectives: [], goal: '   ' }), false);
});

test('the address keeps only known steps, objectives and a bounded goal', () => {
  assert.equal(parseStep('analysis'), 'analysis');
  assert.equal(parseStep('admin'), 'select');
  assert.equal(parseStep(null), 'select');
  assert.deepEqual(parseObjectives('diversify,unknown,reduce_shortages,diversify'), ['reduce_shortages', 'diversify']);
  assert.deepEqual(parseObjectives(null), []);
  assert.equal(OBJECTIVES.length, 5);
  assert.equal(parseGoal('x'.repeat(MAX_GOAL_LENGTH + 50)).length, MAX_GOAL_LENGTH);
});

test('the applied selection survives the address unchanged, and an incomplete one is ignored', () => {
  const selection = { indicator: 'WATER_PRODUCTION', area: 'OM-MA', breakdown: '||', view: 'annual', from: '2021-01-01', to: '2025-01-01' };
  const params = new URLSearchParams('mode=synthetic&tab=analysis');
  writeSelection(params, selection);
  assert.deepEqual(parseSelection(params), selection);
  assert.equal(params.get('mode'), 'synthetic', 'other parameters are kept');
  params.delete('to');
  assert.equal(parseSelection(params), null);
  params.set('to', '2025-01-01');
  params.set('freq', 'weekly');
  assert.equal(parseSelection(params), null, 'an unknown period view is refused');
  writeSelection(params, null);
  assert.equal(params.get('ind'), null);
  assert.equal(params.get('mode'), 'synthetic');
});

test('a wilayat belongs to its canonical governorate (the registry first, then its code)', () => {
  assert.equal(governorateOf('OM-ZU-01'), 'OM-ZU');
  assert.equal(governorateOf('OM-MA'), 'OM-MA');
  assert.equal(governorateOf('OM-GRP-BATINAH'), 'OM-GRP-BATINAH', 'a reporting group is never read as a wilayat');
  assert.equal(governorateOf('OM-ZU-01', new Map([['OM-ZU-01', 'OM-ZU']])), 'OM-ZU');
});
