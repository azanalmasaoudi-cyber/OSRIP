import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';

import {
  boneAngle, FOREARM, HIP_Y, makePlan, poseAt, SHIN, SHOULDER_FAR, SHOULDER_NEAR, SIGN, SIGN_TOP,
  solveJoint, STAGE, THIGH, UPPER_ARM, GRIP_FAR, GRIP_NEAR, type Pose, type Vec,
} from './entranceRig';

/**
 * The entrance scene: an illustrated (fictional) Omani man in a dishdasha, kumma and sandals
 * walks in carrying the OSRIP sign, sets it down in the centre, lets go and steps aside.
 *
 * This is a code-driven 2D vector rig, not a produced video or a 3D model: every body part
 * is a separate SVG shape posed each frame from entranceRig.ts. The OSRIP lettering is real
 * text on the sign (not generated artwork), so it is always exact. Loaded on demand, only
 * when the entrance is shown. Decorative: the dialog around it carries the text.
 *
 * mode "static" draws the final frame only (reduced motion, low-power devices, or when the
 * text has already been revealed). While playing, a frame-time watchdog switches to the
 * final frame if the device cannot keep up (under about 22 frames a second).
 */

export type SceneFallback = 'none' | 'reduced-motion' | 'low-power';

interface Props {
  mode: 'play' | 'static';
  fallback: SceneFallback;
  mirror: boolean; // right-to-left: he enters from the right
  onReveal: () => void;
}

const NARROW = '(max-width: 639px)';
const VIEW_WIDE = { left: 0, right: STAGE.width };
const VIEW_NARROW = { left: 190, right: 770 }; // 580 x 420, the stage box's 29:21 on phones
const FADE = 48; // the stage edges fade into the background: he walks in from the wings

function subscribeNarrow(change: () => void): () => void {
  const query = window.matchMedia(NARROW);
  query.addEventListener('change', change);
  return () => query.removeEventListener('change', change);
}
const isNarrow = () => window.matchMedia(NARROW).matches;

// Colours of the artwork (fixed: the character does not change with the theme).
const C = {
  robe: '#f7f4ec', robeShade: '#e3ddcf', robeFar: '#d6cfbf', seam: '#d2cab8',
  skin: '#b07c5b', skinShade: '#94624a', hair: '#2b211b',
  kumma: '#fbfaf6', kummaBand: '#e2dbcb', green: '#1f4d3a', maroon: '#7a2e3a', gold: '#c9a96e',
  sandal: '#3b2618', tassel: '#b08d57',
  wood: '#8e5c34', woodDark: '#5e3b22', woodLight: '#c08a58', panel: '#fbf7ee', panelShade: '#ece3d0',
  ink: '#0c3326', copper: '#b86b3a',
};

type PartName =
  | 'world' | 'man' | 'man-shadow' | 'torso' | 'head' | 'skirt'
  | 'near-upper' | 'near-fore' | 'near-hand' | 'near-hand-closed' | 'near-hand-open'
  | 'far-upper' | 'far-fore' | 'far-hand'
  | 'near-thigh' | 'near-shin' | 'near-foot' | 'far-thigh' | 'far-shin' | 'far-foot'
  | 'sign' | 'sign-shadow' | 'near-grip' | 'far-grip';

type Rig = Record<PartName, SVGElement>;

function collectRig(svg: SVGSVGElement): Rig {
  const rig = {} as Rig;
  svg.querySelectorAll<SVGElement>('[data-part]').forEach((el) => { rig[el.dataset.part as PartName] = el; });
  return rig;
}

const n = (v: number) => (Math.round(v * 100) / 100).toString();
const place = (p: Vec, angle: number) => `translate(${n(p.x)} ${n(p.y)}) rotate(${n(angle)})`;

/** A point of the torso after it leans (about the hips) and lowers. */
function torsoPoint(p: Vec, lean: number, drop: number): Vec {
  const r = (lean * Math.PI) / 180;
  const dx = p.x;
  const dy = p.y - HIP_Y;
  return { x: dx * Math.cos(r) - dy * Math.sin(r), y: HIP_Y + dx * Math.sin(r) + dy * Math.cos(r) + drop };
}

function drawPose(rig: Rig, pose: Pose): void {
  // Mid-turn he narrows to a third of his width and flips there (a classic cut-out turn).
  const facing = Math.sign(pose.facing || 1) * Math.max(0.32, Math.abs(pose.facing));
  rig.man.setAttribute('transform', `translate(${n(pose.x)} ${STAGE.floor}) scale(${n(facing)} 1)`);

  const drop = pose.crouch + pose.bob;
  rig.torso.setAttribute('transform', `translate(0 ${n(drop)}) rotate(${n(pose.lean)} 0 ${HIP_Y})`);
  rig.head.setAttribute('transform', `rotate(${n(pose.headTilt)} 3 -252)`);

  // Arms: shoulders move with the torso; hands go where the choreography puts them.
  const arms: Array<[Vec, Vec, 'near' | 'far']> = [
    [torsoPoint(SHOULDER_NEAR, pose.lean, drop), pose.hands[0], 'near'],
    [torsoPoint(SHOULDER_FAR, pose.lean, drop), pose.hands[1], 'far'],
  ];
  for (const [shoulder, hand, side] of arms) {
    const { joint: elbow, end: wrist } = solveJoint(shoulder, hand, UPPER_ARM, FOREARM, false);
    const fore = boneAngle(elbow, wrist);
    rig[`${side}-upper`].setAttribute('transform', place(shoulder, boneAngle(shoulder, elbow)));
    rig[`${side}-fore`].setAttribute('transform', place(elbow, fore));
    rig[`${side}-hand`].setAttribute('transform', place(wrist, fore));
  }
  rig['near-hand-closed'].setAttribute('visibility', pose.openHand ? 'hidden' : 'visible');
  rig['near-hand-open'].setAttribute('visibility', pose.openHand ? 'visible' : 'hidden');

  // Legs under the robe: the feet are planted or swinging; knees found by IK.
  const hip = { x: 0, y: HIP_Y + drop };
  const knees: Vec[] = [];
  pose.feet.forEach((foot, i) => {
    const side = i === 0 ? 'near' : 'far';
    const ankle = { x: foot.x, y: -8 - foot.lift };
    const { joint: knee } = solveJoint(hip, ankle, THIGH, SHIN, true);
    knees.push(knee);
    rig[`${side}-thigh`].setAttribute('transform', place(hip, boneAngle(hip, knee)));
    rig[`${side}-shin`].setAttribute('transform', place(knee, boneAngle(knee, ankle)));
    rig[`${side}-foot`].setAttribute('transform', `translate(${n(foot.x)} ${n(-foot.lift)}) rotate(${n(foot.tilt)} 0 -8)`);
  });

  // The lower dishdasha follows the legs: its hem spans the feet, its front the forward knee.
  const xs = pose.feet.map((f) => f.x);
  const back = Math.min(...xs) - 19;
  const front = Math.max(...xs) + 22;
  const frontLift = pose.feet[0].x > pose.feet[1].x ? pose.feet[0].lift : pose.feet[1].lift;
  const knee = Math.max(...knees.map((k) => k.x)) + 13;
  const top = HIP_Y + drop - 10;
  rig.skirt.setAttribute('d',
    `M -27 ${n(top)} C -31 ${n(top + 50)} ${n(back + 1)} -64 ${n(back)} -9 `
    + `L ${n(front)} ${n(-9 - frontLift * 0.5)} C ${n(front + 1)} -52 ${n(knee)} ${n(top + 62)} 26 ${n(top)} Z`);
  rig['man-shadow'].setAttribute('rx', n(34 + (Math.max(...xs) - Math.min(...xs)) * 0.45));
  rig['man-shadow'].setAttribute('cx', n((back + front) / 2));

  // The sign, and its shadow: wide and faint while carried, tight and darker once standing.
  rig.sign.setAttribute('transform', `translate(${n(pose.sign.x)} ${n(STAGE.floor - pose.sign.lift)}) rotate(${n(pose.sign.angle)})`);
  const lift = Math.max(0, pose.sign.lift);
  rig['sign-shadow'].setAttribute('cx', n(pose.sign.x));
  rig['sign-shadow'].setAttribute('rx', n(SIGN.width / 2 - 4 + lift * 0.45));
  rig['sign-shadow'].setAttribute('opacity', n(Math.max(0.2, 0.6 - lift * 0.009)));
  rig['near-grip'].setAttribute('visibility', pose.grip[0] ? 'visible' : 'hidden');
  rig['far-grip'].setAttribute('visibility', pose.grip[1] ? 'visible' : 'hidden');
}

export default function EntranceScene({ mode, fallback, mirror, onReveal }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const narrow = useSyncExternalStore(subscribeNarrow, isNarrow);
  const view = narrow ? VIEW_NARROW : VIEW_WIDE;
  // How the scene runs is decided once, when it first appears.
  const [start] = useState(() => ({ mode, fallback, mirror, view }));
  const reveal = useRef(onReveal);
  useEffect(() => { reveal.current = onReveal; }, [onReveal]);

  useLayoutEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;
    const rig = collectRig(svg);
    const plan = makePlan(start.view.left, start.view.right);
    const show = (t: number) => {
      const pose = poseAt(plan, t);
      drawPose(rig, pose);
      if (svg.dataset.phase !== pose.phase) svg.dataset.phase = pose.phase;
    };
    const finish = (why: SceneFallback) => {
      show(plan.total);
      svg.dataset.mode = 'static';
      svg.dataset.fallback = why;
      reveal.current();
    };
    if (start.mode === 'static') {
      finish(start.fallback);
      return undefined;
    }

    svg.dataset.mode = 'play';
    show(0);
    let frame = 0;
    let last: number | null = null;
    let t = 0;
    let frames = 0;
    let sampled = 0;
    let revealed = false;
    const tick = (now: number) => {
      if (last !== null) {
        const dt = now - last;
        frames += 1;
        // Frames 3-32 (about half a second): averaging over 45 ms (under ~22 frames a second)
        // means this device cannot play it smoothly, so show the final frame instead.
        if (frames > 2 && frames <= 32) sampled += dt;
        if (frames === 32 && sampled / 30 > 45) { finish('low-power'); return; }
        // A long gap (a background tab) pauses the scene rather than skipping through it.
        t += Math.min(dt, 50) / 1000;
      }
      last = now;
      show(Math.min(t, plan.total));
      if (!revealed && t >= plan.revealAt) { revealed = true; reveal.current(); }
      if (t < plan.total) frame = window.requestAnimationFrame(tick);
      else svg.dataset.mode = 'done';
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [start]);

  const viewBox = `${view.left} 0 ${view.right - view.left} ${STAGE.height}`;
  return (
    <svg ref={svgRef} viewBox={viewBox} preserveAspectRatio="xMidYMax meet" aria-hidden="true" focusable="false"
      className="absolute inset-0 block h-full w-full" data-testid="entrance-scene" data-phase="enter" data-mode={start.mode}
      data-fallback={start.fallback} data-mirror={start.mirror ? 'true' : 'false'}>
      <defs>
        <radialGradient id="osrip-spot" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" style={{ stopColor: 'var(--nav-accent)', stopOpacity: 0.16 }} />
          <stop offset="1" style={{ stopColor: 'var(--nav-accent)', stopOpacity: 0 }} />
        </radialGradient>
        <radialGradient id="osrip-shadow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#000" stopOpacity="0.55" />
          <stop offset="0.6" stopColor="#000" stopOpacity="0.28" />
          <stop offset="1" stopColor="#000" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="osrip-floor" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" style={{ stopColor: 'var(--nav-active)', stopOpacity: 0.9 }} />
          <stop offset="1" style={{ stopColor: 'var(--nav-active)', stopOpacity: 0 }} />
        </linearGradient>
        <linearGradient id="osrip-floor-line" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" style={{ stopColor: 'var(--nav-ring)', stopOpacity: 0 }} />
          <stop offset="0.5" style={{ stopColor: 'var(--nav-ring)', stopOpacity: 0.55 }} />
          <stop offset="1" style={{ stopColor: 'var(--nav-ring)', stopOpacity: 0 }} />
        </linearGradient>
        <linearGradient id="osrip-fade-l" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" style={{ stopColor: 'var(--nav)', stopOpacity: 1 }} />
          <stop offset="1" style={{ stopColor: 'var(--nav)', stopOpacity: 0 }} />
        </linearGradient>
        <linearGradient id="osrip-fade-r" x1="1" y1="0" x2="0" y2="0">
          <stop offset="0" style={{ stopColor: 'var(--nav)', stopOpacity: 1 }} />
          <stop offset="1" style={{ stopColor: 'var(--nav)', stopOpacity: 0 }} />
        </linearGradient>
        <linearGradient id="osrip-wood" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={C.woodLight} />
          <stop offset="0.5" stopColor={C.wood} />
          <stop offset="1" stopColor={C.woodDark} />
        </linearGradient>
        <linearGradient id="osrip-panel" x1="0" y1="0" x2="0.35" y2="1">
          <stop offset="0" stopColor={C.panel} />
          <stop offset="1" stopColor={C.panelShade} />
        </linearGradient>
        <clipPath id="osrip-stage-clip">
          <rect x={view.left} y="0" width={view.right - view.left} height={STAGE.height} />
        </clipPath>
      </defs>

      <g clipPath="url(#osrip-stage-clip)">
        <rect x="0" y={STAGE.floor} width={STAGE.width} height={STAGE.height - STAGE.floor} fill="url(#osrip-floor)" />
        <ellipse cx={STAGE.centre} cy={STAGE.floor - 120} rx="330" ry="200" fill="url(#osrip-spot)" />
        <rect x="0" y={STAGE.floor} width={STAGE.width} height="1.5" fill="url(#osrip-floor-line)" />

        <g data-part="world" transform={start.mirror ? `translate(${STAGE.width} 0) scale(-1 1)` : undefined}>
          <ellipse data-part="sign-shadow" cx={STAGE.centre} cy={STAGE.floor + 1} rx="114" ry="9" fill="url(#osrip-shadow)" />

          <g data-part="man" data-testid="entrance-man">
            <ellipse data-part="man-shadow" cx="0" cy="1" rx="40" ry="6" fill="url(#osrip-shadow)" opacity="0.8" />
            <Arm side="far" />
            <Leg side="far" />
            <Leg side="near" />
            <path data-part="skirt" fill={C.robe} stroke={C.seam} strokeWidth="1.2" />
            <g data-part="torso">
              <Torso />
              <g data-part="head"><Head /></g>
            </g>
            <Arm side="near" />
          </g>

          <g data-part="sign" data-testid="entrance-sign">
            <Sign mirror={start.mirror} />
          </g>
        </g>

        <rect x={view.left} y="0" width={FADE} height={STAGE.height} fill="url(#osrip-fade-l)" />
        <rect x={view.right - FADE} y="0" width={FADE} height={STAGE.height} fill="url(#osrip-fade-r)" />
      </g>
    </svg>
  );
}

function Torso() {
  return (
    <>
      {/* Neck */}
      <path d="M -9 -262 L 11 -262 L 13 -240 L -9 -240 Z" fill={C.skin} />
      <path d="M -9 -250 C -2 -246 6 -246 12 -250 L 13 -240 L -9 -240 Z" fill={C.skinShade} opacity="0.5" />
      {/* Dishdasha body, chest to hips (overlaps the skirt so the two read as one garment) */}
      <path d="M -11 -247 C -19 -245 -25 -241 -27 -231 C -30 -214 -31 -190 -28 -158 L 26 -158 C 28 -190 28 -212 24 -228 C 21 -239 17 -245 12 -247 Z"
        fill={C.robe} stroke={C.seam} strokeWidth="1.2" />
      <path d="M -27 -231 C -30 -214 -31 -190 -28 -158 L -20 -158 C -23 -190 -23 -214 -20 -232 Z" fill={C.robeShade} />
      {/* Round collar */}
      <path d="M -11 -246 C -4 -241 6 -241 12 -246" fill="none" stroke={C.seam} strokeWidth="2.5" strokeLinecap="round" />
      {/* Furakha: the tassel hanging from the collar */}
      <path d="M 13 -243 C 18 -232 22 -220 25 -208" fill="none" stroke={C.tassel} strokeWidth="2.2" strokeLinecap="round" />
      <path d="M 22 -209 C 21 -203 23 -195 26 -190 C 29 -195 30 -203 28 -209 C 27 -212 23 -212 22 -209 Z" fill={C.tassel} />
    </>
  );
}

function Head() {
  return (
    <>
      {/* Head in profile, facing +x */}
      <path d="M -6 -252 C -20 -258 -26 -276 -24 -292 C -22 -306 -10 -314 4 -314 C 18 -314 28 -306 29 -294 L 30 -289 C 31 -286 31 -284 32 -282 L 37 -273 C 37 -271 35 -270 32 -270 L 31 -266 C 33 -265 32 -262 30 -261 C 31 -258 30 -253 25 -251 C 18 -249 10 -250 6 -252 Z"
        fill={C.skin} />
      {/* Short hair at the nape, below the cap */}
      <path d="M -25 -297 C -27 -284 -24 -270 -15 -261 L -9 -265 C -15 -276 -17 -288 -17 -298 Z" fill={C.hair} />
      {/* Ear */}
      <ellipse cx="-4" cy="-281" rx="5" ry="8" fill={C.skinShade} />
      {/* Neatly trimmed beard and moustache */}
      <path d="M 3 -284 C 1 -270 6 -258 14 -253 C 20 -249 28 -250 31 -254 C 32 -258 31 -261 29 -262 C 25 -263 22 -266 20 -270 C 14 -272 9 -277 3 -284 Z" fill={C.hair} />
      <path d="M 24 -270 C 28 -271 32 -270 33 -268 C 30 -266 26 -266 22 -267 Z" fill={C.hair} />
      {/* Eye and brow */}
      <ellipse cx="21" cy="-287" rx="2.6" ry="1.8" fill={C.hair} />
      <path d="M 15 -293 C 19 -295 24 -295 28 -293" fill="none" stroke={C.hair} strokeWidth="2.6" strokeLinecap="round" />
      {/* Kumma: the embroidered cap */}
      <path d="M -26 -297 C -26 -318 -12 -332 5 -332 C 22 -332 32 -320 31 -299 C 18 -303 -10 -303 -26 -297 Z" fill={C.kumma} />
      <path d="M -26 -297 C -10 -303 18 -303 31 -299 L 31 -295 C 18 -299 -10 -299 -26 -293 Z" fill={C.kummaBand} />
      <path d="M -23 -308 C -8 -313 16 -313 30 -309" fill="none" stroke={C.green} strokeWidth="2.2" />
      <path d="M -18 -320 C -6 -325 12 -325 26 -320" fill="none" stroke={C.maroon} strokeWidth="1.8" />
      <g fill={C.green}>
        <path d="M -16 -303 l 3 -3.5 l 3 3.5 l -3 3.5 z" /><path d="M -4 -305 l 3 -3.5 l 3 3.5 l -3 3.5 z" />
        <path d="M 8 -305 l 3 -3.5 l 3 3.5 l -3 3.5 z" /><path d="M 20 -304 l 3 -3.5 l 3 3.5 l -3 3.5 z" />
      </g>
      <g fill={C.gold}>
        <circle cx="-10" cy="-316" r="1.4" /><circle cx="2" cy="-318" r="1.4" /><circle cx="14" cy="-318" r="1.4" /><circle cx="24" cy="-315" r="1.4" />
      </g>
    </>
  );
}

function Arm({ side }: { side: 'near' | 'far' }) {
  const sleeve = side === 'near' ? C.robe : C.robeFar;
  const skin = side === 'near' ? C.skin : C.skinShade;
  return (
    <>
      <g data-part={`${side}-upper`}>
        <rect x="-9.5" y="-7" width="19" height={UPPER_ARM + 13} rx="9.5" fill={sleeve} stroke={C.seam} strokeWidth="1.1" />
      </g>
      <g data-part={`${side}-fore`}>
        <path d={`M -8.5 -2 L -6.8 ${FOREARM} L 6.8 ${FOREARM} L 8.5 -2 Z`} fill={sleeve} stroke={C.seam} strokeWidth="1.1" />
        <circle r="8.5" fill={sleeve} />
        <path d={`M -6.8 ${FOREARM - 3} L 6.8 ${FOREARM - 3}`} stroke={C.seam} strokeWidth="1.4" />
      </g>
      <g data-part={`${side}-hand`} data-testid={`entrance-hand-${side}`}>
        <g data-part={side === 'near' ? 'near-hand-closed' : undefined}>
          <path d="M -5.6 0 C -7 6 -6.2 13 -2.2 17 C 1.4 19.6 6 16.2 6.5 10.2 C 7 4.4 5.6 0 0 -1 Z" fill={skin} />
        </g>
        {side === 'near' ? (
          <g data-part="near-hand-open" visibility="hidden">
            {/* Open palm, fingers together, turned up toward the sign */}
            <path d="M -5 -1 C -6 6 -5 16 -3 22 C -1.5 25 3 25 4 22 C 5.4 16 6 7 5 -1 Z" fill={skin} />
            <path d="M 4.6 4 C 8 6 10 9 9.4 12 C 7 12 5.4 10 4.4 8 Z" fill={skin} />
          </g>
        ) : null}
      </g>
    </>
  );
}

function Leg({ side }: { side: 'near' | 'far' }) {
  const skin = side === 'near' ? C.skin : C.skinShade;
  return (
    <>
      <g data-part={`${side}-thigh`}>
        <rect x="-12" y="-4" width="24" height={THIGH + 8} rx="12" fill={side === 'near' ? C.robe : C.robeFar} />
      </g>
      <g data-part={`${side}-shin`}>
        <rect x="-5.5" y="0" width="11" height={SHIN} rx="5.5" fill={skin} />
      </g>
      <g data-part={`${side}-foot`}>
        {/* Foot in a leather sandal (na'al) */}
        <path d="M -9 -2 C -10 -9 -6 -13 0 -13 C 8 -12 16 -7 23 -3 L 23 -2 Z" fill={skin} />
        <path d="M -11 -3.5 L 25 -3.5 C 28.5 -3.5 28.5 0 25 0 L -11 0 C -13.5 0 -13.5 -3.5 -11 -3.5 Z" fill={C.sandal} />
        <path d="M 3 -11.5 C 7 -12.5 11 -10.5 13 -8" fill="none" stroke={C.sandal} strokeWidth="3" strokeLinecap="round" />
      </g>
    </>
  );
}

/** Eight-point star of two squares, the platform's mark. */
function Star({ x, y, r }: { x: number; y: number; r: number }) {
  return (
    <g transform={`translate(${x} ${y})`} fill="none" stroke={C.copper} strokeWidth="1.6" strokeLinejoin="round">
      <rect x={-r * 0.7} y={-r * 0.7} width={r * 1.4} height={r * 1.4} />
      <rect x={-r * 0.7} y={-r * 0.7} width={r * 1.4} height={r * 1.4} transform="rotate(45)" />
    </g>
  );
}

function Sign({ mirror }: { mirror: boolean }) {
  const w = SIGN.width;
  const h = SIGN.height;
  const top = SIGN_TOP;
  return (
    <>
      {/* Stand */}
      {[-78, 78].map((x) => (
        <g key={x}>
          <rect x={x - 4} y={-SIGN.legs - 4} width="8" height={SIGN.legs + 4} fill={C.woodDark} />
          <rect x={x - 15} y="-5" width="30" height="5" rx="2" fill={C.woodDark} />
        </g>
      ))}
      {/* Board: its thickness, the wooden frame, the painted panel, the lettering */}
      <g transform={mirror ? 'scale(-1 1)' : undefined}>
        <rect x={-w / 2 + 5} y={top + 5} width={w} height={h} rx="6" fill="#2e1c10" opacity="0.55" />
        <rect data-testid="entrance-sign-board" x={-w / 2} y={top} width={w} height={h} rx="6" fill="url(#osrip-wood)" />
        <rect x={-w / 2 + 3} y={top + 2} width={w - 6} height="2" rx="1" fill={C.woodLight} opacity="0.7" />
        <rect x={-w / 2 + 10} y={top + 10} width={w - 20} height={h - 20} rx="3" fill="url(#osrip-panel)" />
        <rect x={-w / 2 + 10} y={top + 10} width={w - 20} height="5" fill="#000" opacity="0.07" />
        <text x="2.5" y={top + 78} textAnchor="middle" direction="ltr" fontFamily="'IBM Plex Sans', system-ui, sans-serif"
          fontWeight="600" fontSize="58" letterSpacing="5" fill={C.ink} data-testid="entrance-sign-text">OSRIP</text>
        <path d={`M -66 ${top + 96} H -14 M 14 ${top + 96} H 66`} stroke={C.copper} strokeWidth="2.4" strokeLinecap="round" />
        <Star x={0} y={top + 96} r={6} />
        {([[-1, 0], [1, 0], [-1, 1], [1, 1]] as const).map(([sx, sy]) => (
          <circle key={`${sx}${sy}`} cx={sx * (w / 2 - 5)} cy={sy ? top + h - 5 : top + 5} r="2.2" fill={C.woodDark} />
        ))}
      </g>
      {/* Fingers round the edges while it is held (in front of the board) */}
      <g data-part="near-grip" data-testid="entrance-grip-near">
        <path d={`M ${GRIP_NEAR.x - 3} ${GRIP_NEAR.y - 13} h 12 a 3.6 3.6 0 0 1 0 7.2 h -12 Z M ${GRIP_NEAR.x - 3} ${GRIP_NEAR.y - 4} h 13 a 3.6 3.6 0 0 1 0 7.2 h -13 Z M ${GRIP_NEAR.x - 3} ${GRIP_NEAR.y + 5} h 11 a 3.4 3.4 0 0 1 0 6.8 h -11 Z`}
          fill={C.skin} stroke={C.skinShade} strokeWidth="0.8" />
      </g>
      <g data-part="far-grip" data-testid="entrance-grip-far">
        <path d={`M ${GRIP_FAR.x - 12} ${GRIP_FAR.y - 3} v 10 a 3.4 3.4 0 0 0 6.8 0 v -10 Z M ${GRIP_FAR.x - 3.5} ${GRIP_FAR.y - 3} v 11.5 a 3.5 3.5 0 0 0 7 0 v -11.5 Z M ${GRIP_FAR.x + 5} ${GRIP_FAR.y - 3} v 10 a 3.4 3.4 0 0 0 6.8 0 v -10 Z`}
          fill={C.skinShade} stroke="#7d5139" strokeWidth="0.8" />
      </g>
    </>
  );
}
