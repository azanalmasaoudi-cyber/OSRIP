# First-visit entrance (cinematic introduction)

Status, 10 October 2026: **implemented and locally tested** (mock browser suite, Edge desktop
and Pixel 7 emulation). Not deployed.

## What a first-time visitor sees

A short scene of about **5.3 s on a wide screen and 4.6 s on a phone**:

| Phase | What happens |
|---|---|
| enter | A fictional Omani man walks in from the edge of the stage. He wears a white dishdasha with the furakha (collar tassel), an embroidered kumma and leather sandals. He carries a wooden-framed OSRIP sign at his side: one hand round its rear edge, the other over the top edge. |
| lower | He slows to a stop, bends and sets the sign down in the centre of the stage. |
| release | He lets go and his hands come away from the edges. The sign rocks very slightly and settles; its shadow tightens on the floor. |
| rise, aside | He straightens up, steps out from behind the sign to one side and stops. |
| turn, present | He turns back and makes an open-hand gesture toward the sign. |

Below the sign appear:

- the names: "Oman Smart Resource Intelligence Platform" and «منصة عُمان الذكية لمعلومات الموارد»;
- the three bilingual goals:
  - Understand Oman’s resources / فهم موارد عُمان
  - Analyse reliable data / تحليل البيانات الموثوقة
  - Support informed decisions / دعم القرارات المبنية على البيانات

**Explore** (ابدأ) and **Skip** (تخطي) are available from the first moment.

In Arabic the scene is mirrored: he enters from the right and steps aside to the left. The OSRIP lettering is never mirrored.

**Arabic name.** The new prompt again wrote «منصة عُمان الذكية لذكاء الموارد». The project owner already chose «…لمعلومات الموارد» on 8 October 2026 (SPEC_CONFLICTS C58), so that name is kept. Changing it is a one-line edit in `Entrance.tsx` (`NAME.ar`).

## How it is built, and what is not available

**Assets found in the repository** (checked before choosing an approach):

- `public/images/illustrations/omani-man-dishdasha-kumma.svg`, a static head-and-shoulders portrait;
- `assets/editorial/masters/omani-professional.png`, a static illustration (1.4 MB);
- the brand mark and patterns.

None of these is a character that can move. There is **no 3D model, rig or animation clip**, no produced video, and no 3D library: three.js was not approved, and no frontend package was added.

**What was built instead: a code-driven 2D vector rig** (`entranceRig.ts` + `EntranceScene.tsx`). It is a real animation, not a static illustration:

- **Body parts.** Every body part is a separate SVG shape posed 60 times a second: head, torso, skirt, upper arms, forearms, hands, thighs, shins and feet.
- **Feet.** They are planted on the floor while bearing weight. The gait is driven by the distance walked, with opening and closing steps, so the feet never skate.
- **Joints.** Knees and elbows are solved with two-bone inverse kinematics.
- **Hands and sign.** The hands are attached to the sign's grip points while carrying. Fingers are drawn round the edges in front of the sign until he lets go.
- **The sign.** A separate object: wooden frame, painted panel, stand and shadow. Its lettering is real SVG text in IBM Plex Sans (the platform's font), so "OSRIP" is always exact.

**The exact missing asset for a "produced" version.** To replace the vector rig with a 3D or filmed character, the project would need one of:

1. **A rigged 3D character** (`.glb`, ideally under 1.5 MB with Draco/meshopt compression). It would need:
   - a skeleton;
   - clips `walk_carry`, `lower_place`, `release`, `step_aside`, `turn`, `present_idle`;
   - a hand bone or attachment socket for the sign;
   - the outfit modelled as dishdasha, kumma and sandals.

   It also needs approval to add `three` (and a loader) to the frontend.
2. **A produced 4–6 s video with transparency.** WebM VP9 with alpha plus HEVC with alpha (for Safari), with a poster frame. The man carries a *blank* sign, so the OSRIP lettering stays an HTML layer tracked to it; or the lettering is composited in post-production and checked frame by frame.

The scene structure would stay the same either way: phases, Skip, still-frame fallbacks, the reveal and the tests.

## Behaviour

| Requirement | How |
|---|---|
| First visit only, remembered locally | `localStorage` `osrip.entrance = seen-1`, set by Explore, Skip or Escape. Nothing is sent to the server. If storage is blocked, the entrance is not shown, so nobody is trapped. |
| Replay introduction in settings | **Account and settings** page → *Settings* → *Replay introduction*. It is there signed in or out, and in mock mode. Also in the footer. A replay starts the scene from the beginning. |
| Immediate skip | Both buttons are rendered and focusable from the first frame. Focus starts on Explore; Escape skips. |
| Direct links preserved | Explore from the home page opens the overview. From any other address (for example `/trade?mode=synthetic`) it closes and stays there. Skip never navigates. |
| Keyboard focus restored | Back to the element that opened it (for example the Settings button). On a first visit, to the page's main content. |
| Reduced motion | The scene's final frame, with all text shown at once and nothing moving (`data-fallback="reduced-motion"`). |
| Low power | Data saver, at most 2 CPU cores or at most 2 GB device memory gives the final frame from the start (`low-power`). While playing, a watchdog switches to the final frame if frames 3–32 average more than 45 ms. |
| Loading failure | The scene is a separate chunk loaded on demand. If it fails, an error boundary shows a plain OSRIP sign and reveals the text; Explore and Skip work. If it is slower than 1.2 s, the text is revealed anyway and the scene arrives as its final frame. |
| No sound | No audio or video elements; no audio API is used (tested). |
| Application data not delayed | The page behind renders and loads its data while the entrance is open (`showModal` makes it inert, not unmounted). The scene's code is not in the main bundle. |
| Background tab | Frame gaps over 50 ms are clamped, so the scene pauses rather than skipping ahead. |

## Sizes (production build, 10 October 2026)

| Item | Size |
|---|---|
| `EntranceScene-*.js` (scene + rig, loaded only when the entrance shows) | **19.00 kB** (6.35 kB gzip) |
| Images, video, 3D files | **none** (vector shapes and text only; the fonts are the app's own) |
| Shell in the main bundle (`Entrance.tsx`: dialog, text, buttons, fallbacks) | 9.9 kB of source; its minified share of the main bundle was not measured separately (the main-bundle size warning existed before) |

## Performance (measured)

Measured on 10 October 2026 with a production build (mock data) served by `vite preview` and driven by Edge (headless) on this Windows 11 machine. The method:

- frame times from `requestAnimationFrame`;
- long tasks and layout shift from `PerformanceObserver`;
- slower devices simulated with CDP CPU throttling.

| Run | Sequence | Average fps | p95 frame | Frames over 34 ms | Long tasks | Layout shift |
|---|---|---|---|---|---|---|
| Desktop 1366×768, 3 runs | 5.29–5.39 s | 58.3 / 60 / 60 | 16.8 ms | 2 (first, cold run) / 0 / 0 | 0 | 0.0001 |
| Desktop, CPU 4× slower | 5.28 s | 59.8 | 16.8 ms | 0 | 0 | 0.0001 |
| Phone 412×915, CPU 4× slower | 4.59 s | 60 | 16.8 ms | 0 | 0 | 0 |
| Phone, CPU 6× slower | 4.59 s | 59.6 | 16.8 ms | 0 | 0 | 0 |
| Phone, CPU 20× slower | watchdog → **final frame** after 1.8 s | 18.4 | 66.7 ms | (before the switch) | — | 0 |

**Data loading.** Time to the first overview data card, 5 runs each:

- entrance open: 486 / 428 / 439 / 415 / 445 ms, median **439 ms**;
- entrance already seen: 455 / 435 / 422 / 431 / 441 ms, median **435 ms**.

The difference is within run-to-run noise.

JavaScript heap with the page and scene: 8.4–9.7 MB.

## Evidence

All in `docs/evidence/entrance/`:

- **Real-time recordings** (browser screencast, about 52 fps, assembled at 25 fps; the first frames show the page loading):
  - `entrance-desktop-en.webp` (541 kB)
  - `entrance-desktop-ar.webp` (488 kB)
  - `entrance-phone-en.webp` (489 kB)

  They play in Edge or Chrome. No ffmpeg is installed, so they are animated WebP rather than MP4.
- **Frame sheets** (exact times, from the fake clock):
  - `frames-desktop-en.png`
  - `frames-desktop-ar.png`
  - `frames-phone-en.png`
- **Fallbacks and Settings:**
  - `reduced-motion-final-frame.png`
  - `scene-failed-to-load.png`
  - `settings-replay-introduction.png`

## Tests

`frontend/e2e/entrance.spec.ts`, 11 tests on desktop and 1 on Pixel 7. The scene tests run on Playwright's fake clock, so each moment is checked deterministically.

1. **The full sequence.** Phases arrive in order (enter → lower → release → rise → aside → turn → present → settled) within 4–6.2 s. While carrying, the fingers are round both edges and the near hand is on the sign. When placed, the sign is lower than while carried and centred to within 3 px. After release, the fingers are gone and the hands are off the sign. He stands clear of it. The lettering reads "OSRIP". Then the names and goals are revealed. No audio is created. Explore goes to the overview, and the entrance is remembered after a reload.
2. The overview's data card is in the page while the scene plays.
3. Immediate Skip on a direct link keeps `/trade?mode=synthetic` and focuses the content; Escape and the footer replay return focus.
4. Explore on `/energy/water?mode=synthetic` stays there.
5. Settings → Replay introduction plays again; focus returns to the button.
6. Arabic: right to left, he enters from the right and ends to the left of the centred sign; the lettering has a positive on-screen scale (not mirrored); ابدأ / تخطي; Arabic name first.
7. Arabic Settings label «إعادة عرض المقدمة».
8. Reduced motion: the final frame at once, the text visible, no fingers on the sign.
9. Low-power device (2 cores): the final frame.
10. Loading failure (the scene module blocked): a plain sign, the text revealed, Explore works.
11. Phone (Pixel 7): the sign, the man and the stage within the screen; no sideways scrolling.

## Files

- `frontend/src/components/layout/entranceRig.ts`: choreography, gait and IK. Pure functions.
- `frontend/src/components/layout/EntranceScene.tsx`: the SVG character, the sign and the frame loop. Lazily loaded.
- `frontend/src/components/layout/Entrance.tsx`: the dialog, text, buttons, fallbacks and storage.
- `frontend/src/components/layout/entranceControl.ts`: the replay context.
- `frontend/src/components/settings/SettingsSection.tsx`: Settings → Replay introduction.
- `frontend/src/components/layout/AppShell.tsx`: direct-link-safe Explore and the replay provider.
- i18n: `settings.*`, `entrance.replay` ("Replay introduction"), `nav.account` ("Account and settings" / «الحساب والإعدادات»).
