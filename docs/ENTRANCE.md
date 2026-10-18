# Opening introduction

Status, 18 October 2026: **implemented and locally tested** (mock and full-stack browser
suites, Edge desktop and Pixel 7 emulation), on branch `redesign/dark-dashboard`. Not deployed.

## Source

The project owner's own design, `docs/OSRIP_Intro_Single_File.html`: a standalone page with
the two assistants' portraits, the OSRIP sign, the name, three resource images and three
goals. It is rebuilt natively in React (`frontend/src/components/layout/Entrance.tsx`, styles
`.intro*` in `src/index.css`), not embedded, so it shares the app's languages, themes, focus
handling, replay and tests.

**Its images are the five embedded in that file:**
- They were extracted unchanged into `frontend/assets/editorial/masters/`:
  - `omani-man-courtyard.png`, Al Mulhim (also the master of his assistant portraits);
  - `omani-woman-courtyard.jpg`, Ilham (the same picture as `omani-woman-professional.jpg`,
    encoded differently);
  - `intro-electricity.jpg`, `intro-water.jpg` and `intro-trade.jpg`, on white.
- `tools/build_intro_images.py` checks them by SHA-256 and writes 600 px JPEGs to
  `frontend/public/images/intro/` (50–67 KB each), served as `/images/intro/*.jpg`.
- They are downscaled whole: no cropping, retouching or upscaling.
- They are recorded in `frontend/assets/editorial/sources.json`.
- No path points to a temporary folder, a ZIP preview or a local drive.

**Framing:**
- **Portraits:** the file's own framing: arch frames 164 × 280 px (110 × 200 on phones), the
  image covering the frame from the top centre.
- **Illustrations:** shown complete (`object-fit: contain`) at one height, 112 px (82 px on
  phones), never cropped or stretched.

## What a first-time visitor sees

1. **Arrival.** Al Mulhim slides in from the left and Ilham from the right (1.8 s). Their portraits
   are framed in arches with their names below (Arabic and English).
2. **The sign.** The OSRIP sign ("Insight for a resilient Oman") is set down between them (2.2 s).
3. **The rest appears** after about 1.4 to 2.3 s:
   - the line "Resources we understand. Decisions built on knowledge.";
   - the platform's name in both languages;
   - the three resources: Electricity and energy, Water resources, Trade and logistics;
   - the three goals:
     - Understand Oman's resources / افهم موارد عُمان;
     - Analyse reliable data / حلّل البيانات الموثوقة;
     - Support informed decisions / ادعم القرار بالمعلومة.

**Explore / استكشف** and **Skip / تخطّي** are labelled in both languages and work from the
first moment. Both enter the dashboard (the Overview). The dark theme uses the design's deep
teal. The light theme uses the same layout on warm ivory with teal ink.

**Arabic name.** The owner's file writes «منصة عُمان الذكية لذكاء الموارد». The project owner
chose «…لمعلومات الموارد» on 8 October 2026 (SPEC_CONFLICTS C58), and the whole app uses that
name, so the introduction does too. Changing it is a one-line edit in `Entrance.tsx`
(`NAME.ar`).

## Behaviour

| Requirement | How |
|---|---|
| Once per browser session | `sessionStorage` `osrip.entrance = shown`, set as soon as it opens, so a reload never shows it again in that session and there is no loop. A new browser session shows it again. Nothing is sent to the server. If storage is blocked, it is not shown, so nobody is trapped. |
| Home page only | It opens on `/` only, including when the home page is reached later in the session. A direct link (a study, the workspace, sign-in, the account) opens its page at once and is never interrupted. |
| Switch | Account → Settings → *Show it when the home page opens*. Turning it off sets `localStorage` `osrip.intro.autoplay = off` for this browser. The browser test configurations use the same switch. |
| Replay | Footer → *Replay introduction*, and Account → Settings → *Replay introduction*, on every page. A replay starts the animation from the beginning. |
| Explore and Skip | Both enter the dashboard (`/overview`, keeping the data mode). Escape only closes. |
| Keyboard and focus | A native modal `<dialog>`. Focus starts on Explore without scrolling, so a phone starts at the top; Skip is one Shift+Tab away. Escape closes and returns focus to the element that opened it (on a first visit, the page's main content). |
| Themes | Dark: the design's deep teal. Light: warm ivory with teal ink. The focus ring follows. |
| Reduced motion | The final frame at once, with no movement (`data-mode="static"`, `data-fallback="reduced-motion"`). |
| Low power | Data saver, at most 2 CPU cores or at most 2 GB device memory: the final frame (`low-power`). |
| Missing images | A portrait that cannot load becomes the neutral "AI" badge (`PersonaImage`). A resource image keeps its caption. Everything else works. |
| No sound | No audio or video elements and no audio API (tested). |
| Application data not delayed | The page behind renders and loads its data while the introduction is open (`showModal` makes it inert, not unmounted). |
| Right to left | Texts and buttons follow the language. The stage keeps the owner's order (Al Mulhim left, Ilham right) and the OSRIP lettering is never mirrored. |

## Tests

`frontend/e2e/entrance.spec.ts`: 15 tests on desktop and 1 on Pixel 7.

1. **First visit:**
   - the five `/images/intro/` images load at 600 px;
   - the portraits cover their frames from the top centre;
   - the illustrations are complete (`contain`) and all the same height;
   - the sign is centred between the portraits;
   - the names and the six goal texts are shown, and no audio is used;
   - Explore enters the dashboard, and neither the home page nor a reload shows it again in that session.
2. A new browser session shows it again; a reload in the same session does not.
3. The home page's latest figures load while it is open.
4. Skip at once enters the dashboard, keeping the data mode; going back home does not show it again.
5. Direct links:
   - sign-in and `/trade` are never interrupted;
   - reaching the home page later (the brand link) shows it once;
   - Escape only closes.
6. Footer replay: Escape returns focus; Explore from another page enters the dashboard.
7. Keyboard: focus on Explore, Shift+Tab to Skip, focus stays inside, Enter on Skip enters the dashboard.
8. Settings: replay and Skip; the switch turns the automatic showing off.
9. Arabic: right to left, «استكشف · Explore» and «تخطّي · Skip», the stage order kept, the lettering left to right.
10. Arabic Settings label «إعادة عرض المقدمة».
11. The light theme: ivory background, teal ink and button.
12. Reduced motion: the final frame, no animation; Skip still enters the dashboard.
13. Low-power device (2 cores): the final frame.
14. Images blocked: AI badges for the portraits, captions kept, Explore works.
15. Phone (Pixel 7):
    - portraits, sign and Skip within the screen, starting at the top;
    - no sideways scrolling;
    - equal illustration heights;
    - Explore enters the dashboard.

`frontend/e2e-api/accounts.spec.ts` (full stack) checks with the introduction switched on that
Skip enters the dashboard, that a real sign-in is not blocked, and that the home page does not
show it again in the session.

## History

Until 15 October 2026 the introduction was a code-driven 2D vector scene: an illustrated Omani
man carried the OSRIP sign in and set it down (`EntranceScene.tsx`, `entranceRig.ts`). The
owner's design replaced it on 16 October. The old files are in git history (commit `24c0cca`),
and so are their evidence images in `docs/evidence/entrance/` and the measurements in
`docs/TEST_RESULTS.md`.
