/**
 * The Analysis Workspace now lives inside each sector page (its Analysis tab), so an old
 * /workspace link opens the sector it was about. Only parameters a sector page understands are
 * carried over, and only in a shape it accepts: the data mode, the indicator code, the area code
 * and the period view (the workspace's "frequency"). Anything else (dates, tabs, unknown values)
 * is dropped, never passed on. Pure, so it is tested on its own (tests/workspace-redirect.test.mjs).
 */

const SECTION_PATHS: Record<string, string> = {
  electricity: '/energy/electricity',
  water: '/energy/water',
  food_security: '/food-security',
  trade: '/trade',
};
const DOMAIN_FIRST: Record<string, string> = {
  energy_essential_services: 'electricity',
  food_security: 'food_security',
  trade: 'trade',
};
const VIEWS = new Set(['annual', 'quarterly', 'monthly']);
const INDICATOR = /^[A-Z][A-Z0-9_]{1,63}$/;
const AREA = /^OM(-[A-Z0-9]{1,8}){0,2}$/;

export function workspaceRedirect(search: string): { pathname: string; search: string } {
  const from = new URLSearchParams(search);
  const section = from.get('section') ?? '';
  const domain = from.get('domain') ?? '';
  const target = SECTION_PATHS[section] ?? SECTION_PATHS[DOMAIN_FIRST[domain] ?? ''] ?? SECTION_PATHS.electricity!;
  const kept = new URLSearchParams({ tab: 'analysis' });
  const mode = from.get('mode');
  if (mode === 'synthetic' || mode === 'verified') kept.set('mode', mode);
  const indicator = from.get('indicator') ?? '';
  if (INDICATOR.test(indicator)) kept.set('indicator', indicator);
  const area = from.get('area') ?? '';
  if (AREA.test(area)) kept.set('area', area);
  const frequency = from.get('frequency') ?? '';
  if (VIEWS.has(frequency)) kept.set('view', frequency);
  return { pathname: target, search: `?${kept.toString()}` };
}
