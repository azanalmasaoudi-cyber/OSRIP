/**
 * Choreography of the first-visit entrance, as pure functions of time (no DOM).
 *
 * A code-driven 2D cut-out rig: the character is drawn in profile, facing +x, with its origin
 * on the floor between the feet (SVG coordinates, so "up" is negative y). Feet are planted on
 * the floor while they bear weight (the gait is driven by distance walked, not by time, so they
 * never skate), the knees and elbows are solved with two-bone inverse kinematics, and the sign
 * is a separate object that the hands hold, lower to the floor and let go of.
 *
 * Sequence (about 4.5 s on a phone, 5.3 s on a wide screen):
 *   enter    walks in from the edge carrying the sign at his side
 *   lower    stops, bends and sets the sign down in the centre
 *   release  lets go; the sign settles with a small damped rock
 *   rise     straightens up, arms back to his sides
 *   aside    steps out from behind the sign to one side
 *   turn     turns back toward the sign
 *   present  an open-hand gesture toward it; the text is revealed
 *   settled  final frame (also the reduced-motion and low-power frame)
 */

export type Vec = { x: number; y: number };
export type Phase = 'enter' | 'lower' | 'release' | 'rise' | 'aside' | 'turn' | 'present' | 'settled';

export const STAGE = { width: 960, height: 420, floor: 396, centre: 480 } as const;

// Body (character frame).
export const HIP_Y = -168;
export const THIGH = 88;
export const SHIN = 82;
export const SHOULDER_NEAR: Vec = { x: 0, y: -236 };
export const SHOULDER_FAR: Vec = { x: 7, y: -235 };
export const UPPER_ARM = 64;
export const FOREARM = 58;

// Sign (sign frame: origin on the floor under its centre).
export const SIGN = { width: 236, height: 130, legs: 36 } as const;
export const SIGN_TOP = -(SIGN.legs + SIGN.height); // -166
const SIGN_OFFSET = 70; // sign centre ahead of the body while carried
const CARRY_LIFT = 42; // sign raised this far off the floor while carried
// Where the hands hold it (sign frame): the near hand round the rear edge, the far hand over the top.
export const GRIP_NEAR: Vec = { x: -SIGN.width / 2, y: SIGN_TOP + 62 };
export const GRIP_FAR: Vec = { x: 38, y: SIGN_TOP };

// Gait.
const STRIDE = 33; // half a step: a foot travels from +STRIDE to -STRIDE under the body
const FEET_APART = 7; // standing: feet at +/- this
const LIFT = 11;
const BOB = 3;
const SPEED = 270; // units per second while walking in

const REST_NEAR: Vec = { x: 9, y: -128 };
const REST_FAR: Vec = { x: 15, y: -130 };
const PRESENT_NEAR: Vec = { x: 64, y: -214 };

export interface Foot { x: number; lift: number; tilt: number }

export interface Pose {
  phase: Phase;
  x: number; // body, stage units (before right-to-left mirroring)
  facing: number; // 1 toward the travel direction, -1 turned back; in between while turning
  crouch: number; // hips lowered by this much
  lean: number; // degrees, forward positive
  bob: number;
  headTilt: number;
  feet: [Foot, Foot]; // near, far: x relative to the body
  hands: [Vec, Vec]; // near, far: character frame
  grip: [boolean, boolean]; // fingers visibly round the sign's edge
  openHand: boolean;
  sign: { x: number; lift: number; angle: number };
}

export interface Plan {
  startX: number;
  stopX: number;
  asideX: number;
  times: Record<Phase, number>; // start time of each phase, seconds
  total: number;
  revealAt: number;
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const smooth = (v: number) => { const t = clamp01(v); return t * t * (3 - 2 * t); };
const easeInOutSine = (v: number) => -(Math.cos(Math.PI * clamp01(v)) - 1) / 2;
const easeOutCubic = (v: number) => 1 - (1 - clamp01(v)) ** 3;
const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const mixVec = (a: Vec, b: Vec, t: number): Vec => ({ x: mix(a.x, b.x, t), y: mix(a.y, b.y, t) });

/** Timings for a stage whose visible part starts at `viewLeft` (the walk starts just beyond it). */
export function makePlan(viewLeft: number, viewRight: number): Plan {
  const stopX = STAGE.centre - SIGN_OFFSET;
  // Fully out of view: the sign leads, so its far edge must start beyond the left edge too.
  const startX = viewLeft - (SIGN_OFFSET + SIGN.width / 2) - 20;
  const asideX = Math.min(STAGE.centre + SIGN.width / 2 + 64, viewRight - 58);
  const closing = STRIDE - FEET_APART;
  const decel = (2 * closing) / SPEED;
  const enter = (stopX - startX - closing) / SPEED + decel;
  const durations: Array<[Phase, number]> = [
    ['enter', enter], ['lower', 0.55], ['release', 0.3], ['rise', 0.35],
    ['aside', 1.05], ['turn', 0.26], ['present', 0.4],
  ];
  const times = {} as Record<Phase, number>;
  let t = 0;
  for (const [phase, d] of durations) { times[phase] = t; t += d; }
  times.settled = t;
  return { startX, stopX, asideX, times, total: t, revealAt: times.turn - 0.15 };
}

/** One foot in a steady walk, `p` = 0..1 through its cycle: planted for the first half. */
function steadyFoot(p: number, a: number): Foot {
  const u = p - Math.floor(p);
  if (u < 0.5) return { x: a - 4 * a * u, lift: 0, tilt: 0 };
  const q = (u - 0.5) / 0.5;
  return { x: -a + 2 * a * smooth(q), lift: LIFT * Math.sin(Math.PI * q), tilt: -14 * Math.sin(Math.PI * q) };
}

/** A foot swinging from `from` to `to` (relative to the body) while the body moves on by `travel`. */
function swingFoot(q: number, from: number, to: number, travel: number): Foot {
  const world = from + (to + travel - from) * smooth(q);
  return { x: world - travel * q, lift: LIFT * 0.8 * Math.sin(Math.PI * q), tilt: -10 * Math.sin(Math.PI * q) };
}

interface Gait { feet: [Foot, Foot]; bob: number; swing: number }

/**
 * Feet for a walk of length `distance`, at `s` units along it. `fromRest`: begins with an
 * opening step from standing; it always ends with a closing step to standing, so both feet
 * are planted together when the walk stops.
 */
function walk(s: number, distance: number, fromRest: boolean): Gait {
  let a = STRIDE;
  let open = 0;
  if (fromRest) {
    // Fit an odd number of steady steps between the opening and closing steps.
    const steps = Math.max(1, 2 * Math.round((distance / (2 * STRIDE) - 1 - 1) / 2) + 1);
    a = distance / (2 * steps + 2);
    open = a + FEET_APART;
  }
  const closing = a - FEET_APART;
  const closeStart = distance - closing;
  const cycle = 4 * a;
  if (fromRest && s < open) {
    const q = s / open;
    return {
      feet: [{ x: FEET_APART - s, lift: 0, tilt: 0 }, swingFoot(q, -FEET_APART, a, open)],
      bob: BOB * smooth(q), swing: 10 * smooth(q),
    };
  }
  if (s >= closeStart) {
    const q = clamp01((s - closeStart) / closing);
    return {
      feet: [{ x: a - (s - closeStart), lift: 0, tilt: 0 }, swingFoot(q, -a, -FEET_APART, closing)],
      bob: BOB * (1 - smooth(q)), swing: -10 * (1 - smooth(q)),
    };
  }
  const p = (s - closeStart) / cycle; // near foot lands (p = 0) just as the closing step begins
  const u = p - Math.floor(p);
  return {
    feet: [steadyFoot(p, a), steadyFoot(p + 0.5, a)],
    bob: BOB * Math.cos(4 * Math.PI * u),
    swing: -10 * Math.cos(2 * Math.PI * u),
  };
}

const STANDING: [Foot, Foot] = [{ x: FEET_APART, lift: 0, tilt: 0 }, { x: -FEET_APART, lift: 0, tilt: 0 }];

/** Where a point of the sign is, in the character frame (the character faces +x while holding it). */
function signPoint(p: Vec, bodyX: number, sign: Pose['sign']): Vec {
  return { x: sign.x + p.x - bodyX, y: p.y - sign.lift };
}

export function poseAt(plan: Plan, t: number): Pose {
  const { times } = plan;
  const centre = STAGE.centre;
  const base: Pose = {
    phase: 'enter', x: plan.stopX, facing: 1, crouch: 0, lean: 0, bob: 0, headTilt: 0,
    feet: STANDING, hands: [REST_NEAR, REST_FAR], grip: [false, false], openHand: false,
    sign: { x: centre, lift: 0, angle: 0 },
  };

  if (t < times.lower) {
    // Walking in at a steady pace, slowing to a stop over the closing step.
    const closing = STRIDE - FEET_APART;
    const total = plan.stopX - plan.startX;
    const steadyTime = (total - closing) / SPEED;
    const s = t < steadyTime
      ? SPEED * t
      : (() => {
          const tau = Math.min(t - steadyTime, (2 * closing) / SPEED);
          return total - closing + SPEED * tau - (SPEED * SPEED / (4 * closing)) * tau * tau;
        })();
    const gait = walk(Math.min(s, total), total, false);
    const x = plan.startX + Math.min(s, total);
    // A slight sway with the steps, fading out as he stops.
    const sway = 0.5 * Math.sin((s / (4 * STRIDE)) * 2 * Math.PI) * clamp01((total - s) / closing);
    const sign = { x: x + SIGN_OFFSET, lift: CARRY_LIFT - gait.bob, angle: sway };
    return {
      ...base, phase: 'enter', x, bob: gait.bob, lean: 2, feet: gait.feet, sign,
      hands: [signPoint(GRIP_NEAR, x, sign), signPoint(GRIP_FAR, x, sign)], grip: [true, true],
    };
  }

  if (t < times.release) {
    // Bends and sets the sign down: it lands softly in the centre.
    const k = (t - times.lower) / (times.release - times.lower);
    const down = easeInOutSine(k);
    const sign = { x: centre, lift: CARRY_LIFT * (1 - easeOutCubic(k)), angle: 0 };
    return {
      ...base, phase: 'lower', crouch: 26 * down, lean: 2 + 7 * down, sign,
      hands: [signPoint(GRIP_NEAR, plan.stopX, sign), signPoint(GRIP_FAR, plan.stopX, sign)], grip: [true, true],
    };
  }

  const settle = (since: number) => {
    // A small, quickly damped rock about the sign's base after it is let go.
    const tau = Math.max(0, since);
    return 1.3 * Math.exp(-tau / 0.32) * Math.sin((2 * Math.PI * tau) / 0.46);
  };
  const placed = (at: number) => ({ x: centre, lift: 0, angle: settle(at - times.release) });

  if (t < times.rise) {
    // Lets go: the hands open and come away from the edges.
    const k = easeOutCubic((t - times.release) / (times.rise - times.release));
    const sign = placed(t);
    const gripNear = signPoint(GRIP_NEAR, plan.stopX, { ...sign, angle: 0 });
    const gripFar = signPoint(GRIP_FAR, plan.stopX, { ...sign, angle: 0 });
    return {
      ...base, phase: 'release', crouch: 26, lean: 9, sign,
      hands: [{ x: gripNear.x - 10 * k, y: gripNear.y + 4 * k }, { x: gripFar.x - 4 * k, y: gripFar.y - 18 * k }],
      grip: [k < 0.35, k < 0.35],
    };
  }

  if (t < times.aside) {
    const k = easeInOutSine((t - times.rise) / (times.aside - times.rise));
    const sign = placed(t);
    const fromNear = signPoint(GRIP_NEAR, plan.stopX, { ...sign, angle: 0 });
    const fromFar = signPoint(GRIP_FAR, plan.stopX, { ...sign, angle: 0 });
    return {
      ...base, phase: 'rise', crouch: 26 * (1 - k), lean: 9 * (1 - k), sign,
      hands: [mixVec({ x: fromNear.x - 10, y: fromNear.y + 4 }, REST_NEAR, k), mixVec({ x: fromFar.x - 4, y: fromFar.y - 18 }, REST_FAR, k)],
    };
  }

  if (t < times.turn) {
    // Steps out from behind the sign, to the side.
    const k = (t - times.aside) / (times.turn - times.aside);
    const distance = plan.asideX - plan.stopX;
    const s = distance * easeInOutSine(k);
    const gait = walk(s, distance, true);
    return {
      ...base, phase: 'aside', x: plan.stopX + s, bob: gait.bob, lean: 1.5 * Math.sin(Math.PI * k), feet: gait.feet,
      sign: placed(t),
      hands: [{ x: REST_NEAR.x + gait.swing, y: REST_NEAR.y + Math.abs(gait.swing) * 0.15 }, { x: REST_FAR.x - gait.swing, y: REST_FAR.y }],
    };
  }

  if (t < times.present) {
    // Turns back toward the sign (a cut-out turn: a quick flip through a narrow profile).
    const k = (t - times.turn) / (times.present - times.turn);
    return { ...base, phase: 'turn', x: plan.asideX, facing: Math.cos(Math.PI * smooth(k)), sign: placed(t) };
  }

  const k = easeOutCubic((t - times.present) / (times.settled - times.present));
  return {
    ...base, phase: t < times.settled ? 'present' : 'settled', x: plan.asideX, facing: -1,
    headTilt: -3 * k, sign: placed(t), openHand: k > 0.25,
    hands: [mixVec(REST_NEAR, PRESENT_NEAR, k), REST_FAR],
  };
}

/** Two-bone inverse kinematics: the middle joint for a limb from `root` reaching `target`. */
export function solveJoint(root: Vec, target: Vec, l1: number, l2: number, bendForward: boolean): { joint: Vec; end: Vec } {
  let dx = target.x - root.x;
  let dy = target.y - root.y;
  let d = Math.hypot(dx, dy) || 0.001;
  const max = l1 + l2 - 0.01;
  const min = Math.abs(l1 - l2) + 0.01;
  if (d > max || d < min) {
    const c = d > max ? max : min;
    dx *= c / d; dy *= c / d; d = c;
  }
  const angle = Math.acos(Math.min(1, Math.max(-1, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d))));
  const base = Math.atan2(dy, dx);
  const a = { x: root.x + l1 * Math.cos(base + angle), y: root.y + l1 * Math.sin(base + angle) };
  const b = { x: root.x + l1 * Math.cos(base - angle), y: root.y + l1 * Math.sin(base - angle) };
  const joint = (a.x > b.x) === bendForward ? a : b;
  return { joint, end: { x: root.x + dx, y: root.y + dy } };
}

/** Rotation (degrees) that turns the +y axis toward the vector from `a` to `b`. */
export function boneAngle(a: Vec, b: Vec): number {
  return (Math.atan2(-(b.x - a.x), b.y - a.y) * 180) / Math.PI;
}
