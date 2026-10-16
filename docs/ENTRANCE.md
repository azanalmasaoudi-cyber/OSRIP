# First-visit introduction

Status, 16 October 2026: **implemented and locally tested** (mock browser suite, Edge desktop
and Pixel 7 emulation), on branch `redesign/dark-dashboard`. Not deployed.

## Source

The project owner's own design, `docs/OSRIP_Intro_Single_File.html`: a standalone page with
the two assistants' portraits, the OSRIP sign, the name, three resource images and three
goals. It is rebuilt natively in React (`frontend/src/components/layout/Entrance.tsx`, styles
`.intro*` in `src/index.css`), not embedded, so it shares the app's languages, focus handling,
replay and tests. Its images are served from the project's own optimised assets:

- **Portraits:** the assistants' 3:4 figures, `public/images/assistant/{mulhim,ilham}-figure-600.jpg`,
  built by `tools/build_persona_portraits.py`:
  - Al Mulhim's master is the courtyard portrait from the owner's file (`omani-man-courtyard.png`);
  - Ilham's master is the same artwork as before;
  - both are recorded in `frontend/assets/editorial/sources.json`.
- **Resources:** the editorial electricity, water and trade images (AVIF/WebP/JPEG, 480–1536 px).
  They are the same artworks as in the owner's file.

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

**Explore** and **Skip** are labelled in both languages and work from the first moment. Its own
deep-teal palette is used in both themes.

**Arabic name.** The owner's file writes «منصة عُمان الذكية لذكاء الموارد». The project owner
chose «…لمعلومات الموارد» on 8 October 2026 (SPEC_CONFLICTS C58), and the whole app uses that
name, so the introduction does too. Changing it is a one-line edit in `Entrance.tsx`
(`NAME.ar`).

## Behaviour

| Requirement | How |
|---|---|
| First visit only, remembered locally | `localStorage` `osrip.entrance = seen-1`, set by Explore, Skip or Escape. Nothing is sent to the server. If storage is blocked, the entrance is not shown, so nobody is trapped. |
| Home page only | The first-visit introduction opens on `/` only. A direct link opens its page at once and leaves the introduction unseen, so a later visit to the home page still shows it. |
| Replay | Footer → *Replay introduction*, and Account → Settings → *Replay introduction*, on every page. A replay starts the animation from the beginning. |
| Explore | From the home page it opens the overview. In a replay on any other page it closes and stays there. Skip never navigates. |
| Keyboard and focus | A native modal `<dialog>`. Focus starts on Explore without scrolling, so a phone starts at the top. Escape skips. Focus returns to the element that opened it, or on a first visit to the page's main content. |
| Reduced motion | The final frame at once, with no movement (`data-mode="static"`, `data-fallback="reduced-motion"`). |
| Low power | Data saver, at most 2 CPU cores or at most 2 GB device memory: the final frame (`low-power`). |
| Missing images | A portrait that cannot load becomes the neutral "AI" badge (`PersonaImage`). A resource image keeps its caption. Everything else works. |
| No sound | No audio or video elements and no audio API (tested). |
| Application data not delayed | The page behind renders and loads its data while the introduction is open (`showModal` makes it inert, not unmounted). |
| Right to left | Texts and buttons follow the language. The stage keeps the owner's order (Al Mulhim left, Ilham right) and the OSRIP lettering is never mirrored. |

## Tests

`frontend/e2e/entrance.spec.ts`: 12 tests on desktop and 1 on Pixel 7.

1. **First visit:**
   - both portraits load, with the sign centred between them;
   - both names, three resource images and the six goal texts are shown;
   - no audio is used;
   - Explore opens the overview, and the introduction is remembered after a reload.
2. The home page's latest figures load while the introduction is open.
3. Skip at once on the home page: stays there, focuses the content, is remembered.
4. A direct link (`/trade?mode=synthetic`) opens without the introduction and leaves it unseen. The footer replay closes with Escape and returns focus.
5. Explore in a replay on `/energy/water?mode=synthetic` stays there.
6. Settings → Replay introduction plays again; focus returns to the button.
7. Arabic: right to left, Arabic first, bilingual buttons, the stage order kept, the lettering left-to-right.
8. Arabic Settings label «إعادة عرض المقدمة».
9. Reduced motion: the final frame, no animation.
10. Low-power device (2 cores): the final frame.
11. Images blocked: AI badges for the portraits, captions kept, Explore works.
12. Phone (Pixel 7): portraits, sign and Skip within the screen, starting at the top, no sideways scrolling.

## History

Until 15 October 2026 the introduction was a code-driven 2D vector scene: an illustrated Omani
man carried the OSRIP sign in and set it down (`EntranceScene.tsx`, `entranceRig.ts`). The
owner's design replaced it on 16 October. The old files are in git history (commit `24c0cca`),
and so are their evidence images in `docs/evidence/entrance/` and the measurements in
`docs/TEST_RESULTS.md`.
