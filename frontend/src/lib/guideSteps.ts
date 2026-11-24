import type { SeriesView } from '@/api/series';
import type { SectorSelection } from '@/state/sectorSelections';

/**
 * The guided analysis of a sector as a state machine kept in the address, so a reload, Back and
 * a shared link return to the same step with the same selection and objectives:
 *
 *   select -> results -> analysis -> objectives -> recommendations
 *
 * A step is reachable only when what it needs exists: results and analysis need an applied
 * selection; recommendations need at least one objective (chosen or written). An address asking
 * for a step that is not reachable shows the furthest reachable one instead. Moving back keeps
 * everything; changing the selection starts again from the results of the new selection.
 */

// No runtime imports: tested on its own with Node (tests/guide-steps.test.mjs).

/** The objectives recommendations can serve (the same five as app/services/objectives.py). */
export const OBJECTIVES = ['reduce_shortages', 'improve_efficiency', 'use_surplus', 'strengthen', 'diversify'] as const;
export type Objective = (typeof OBJECTIVES)[number];

/** The period views (as api/series VIEWS). */
const VIEWS = ['annual', 'quarterly', 'monthly'] as const satisfies readonly SeriesView[];

export const GUIDE_STEPS = ['select', 'results', 'analysis', 'objectives', 'recommendations'] as const;
export type GuideStep = (typeof GUIDE_STEPS)[number];

/** Query parameters of the guided analysis (none clash with the sector page's other ones). */
export const P = {
  step: 'step',
  indicator: 'ind',
  area: 'at',
  breakdown: 'bd',
  view: 'freq',
  from: 'from',
  to: 'to',
  goals: 'goals',
  goal: 'goal',
} as const;

export const MAX_GOAL_LENGTH = 300;

export interface GuideContext {
  applied: boolean;
  objectives: readonly Objective[];
  goal: string;
}

export function hasObjectives(ctx: Pick<GuideContext, 'objectives' | 'goal'>): boolean {
  return ctx.objectives.length > 0 || ctx.goal.trim().length > 0;
}

/** The furthest step the context allows, no further than the one asked for. */
export function reachableStep(asked: GuideStep, ctx: GuideContext): GuideStep {
  if (!ctx.applied) return 'select';
  if (asked === 'recommendations' && !hasObjectives(ctx)) return 'objectives';
  return asked;
}

export function nextStep(step: GuideStep): GuideStep {
  return GUIDE_STEPS[Math.min(GUIDE_STEPS.indexOf(step) + 1, GUIDE_STEPS.length - 1)]!;
}

export function previousStep(step: GuideStep): GuideStep {
  return GUIDE_STEPS[Math.max(GUIDE_STEPS.indexOf(step) - 1, 0)]!;
}

export function stepIndex(step: GuideStep): number {
  return GUIDE_STEPS.indexOf(step);
}

export function parseStep(raw: string | null): GuideStep {
  return GUIDE_STEPS.find((s) => s === raw) ?? 'select';
}

/** Known objective codes from the address, each once, in the fixed order. */
export function parseObjectives(raw: string | null): Objective[] {
  const wanted = new Set((raw ?? '').split(','));
  return OBJECTIVES.filter((o) => wanted.has(o));
}

export function parseGoal(raw: string | null): string {
  return (raw ?? '').slice(0, MAX_GOAL_LENGTH);
}

/** The applied selection written in the address, if a complete one is there. */
export function parseSelection(params: URLSearchParams): SectorSelection | null {
  const indicator = params.get(P.indicator);
  const view = VIEWS.find((v) => v === params.get(P.view));
  const from = params.get(P.from);
  const to = params.get(P.to);
  if (!indicator || !view || !from || !to) return null;
  return { indicator, area: params.get(P.area) ?? 'OM', breakdown: params.get(P.breakdown) ?? '', view, from, to };
}

export function writeSelection(params: URLSearchParams, s: SectorSelection | null): void {
  if (!s) {
    for (const key of [P.indicator, P.area, P.breakdown, P.view, P.from, P.to]) params.delete(key);
    return;
  }
  params.set(P.indicator, s.indicator);
  params.set(P.area, s.area);
  if (s.breakdown) params.set(P.breakdown, s.breakdown);
  else params.delete(P.breakdown);
  params.set(P.view, s.view);
  params.set(P.from, s.from);
  params.set(P.to, s.to);
}

/** The governorate a wilayat code belongs to (OM-XX-NN -> OM-XX); the code itself otherwise. */
export function governorateOf(code: string, parents?: ReadonlyMap<string, string | null>): string {
  const parent = parents?.get(code);
  if (parent && parent !== 'OM') return parent;
  const m = /^(OM-[A-Z]{2})-\d+$/.exec(code);
  return m ? m[1]! : code;
}
