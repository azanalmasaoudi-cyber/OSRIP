import assert from 'node:assert/strict';
import { test } from 'node:test';

import { workspaceRedirect } from '../src/lib/workspaceRedirect.ts';

test('an old workspace link opens its sector’s Analysis tab', () => {
  assert.deepEqual(workspaceRedirect(''), { pathname: '/energy/electricity', search: '?tab=analysis' });
  assert.deepEqual(workspaceRedirect('?section=water'), { pathname: '/energy/water', search: '?tab=analysis' });
  assert.deepEqual(workspaceRedirect('?domain=trade'), { pathname: '/trade', search: '?tab=analysis' });
  assert.equal(workspaceRedirect('?domain=food_security').pathname, '/food-security');
  assert.equal(workspaceRedirect('?section=unknown&domain=energy_essential_services').pathname, '/energy/electricity');
});

test('the data mode, indicator, area and view are kept when they are well formed', () => {
  const { search } = workspaceRedirect('?mode=synthetic&section=trade&indicator=TRADE_VALUE&area=OM-MU&frequency=monthly');
  assert.equal(search, '?tab=analysis&mode=synthetic&indicator=TRADE_VALUE&area=OM-MU&view=monthly');
});

test('anything else is dropped, never passed on', () => {
  const { search } = workspaceRedirect(
    '?mode=admin&indicator=%3Cscript%3E&area=../../etc&frequency=year_to_date&from=2001&to=2002&tab=assistant&x=1',
  );
  assert.equal(search, '?tab=analysis');
});
