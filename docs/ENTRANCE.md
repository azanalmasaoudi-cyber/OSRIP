# Welcome and sign-in screens

Status, 3 November 2026: **implemented and locally tested** (mock and full-stack browser
suites, Chrome desktop and Pixel 7 emulation), on branch `feature/welcome-login-design`. Not
deployed.

## Source

The project owner's design, `OSRIP_Welcome_Login_Design` (an HTML prototype, four screenshots
and the four sector images). It is rebuilt natively in React, not embedded, so it shares the
application's languages, themes, focus handling, routes and tests:

- `frontend/src/components/layout/Entrance.tsx`: the welcome;
- `frontend/src/components/layout/AuthLayout.tsx` and `frontend/src/pages/SignInPage.tsx`: the
  sign-in screen;
- `frontend/src/components/layout/WelcomeChrome.tsx`: what both share (background, top bar,
  footer);
- `frontend/src/components/layout/welcome.css`: the styles.

The colours are the design's own (charcoal and peach in the dark theme, warm cream in the light
theme), scoped to these two screens and switched with the application's theme. Two light-theme
values are a shade deeper than in the design so small text keeps 4.5:1 contrast: muted text
`#5F5E5C` (design `#6B6A68`) and the button gradient `#A95833` to `#9C4D2F` (design `#B4623B`
to `#A25132`).

Text uses the application's typefaces (IBM Plex Sans and IBM Plex Sans Arabic); the large OSRIP
wordmark keeps the design's heavy Arial. The sector images are the supplied PNGs, already in
`frontend/public/images/sectors/` (byte-identical) and served as WebP
(`components/brand/SectorArtwork.tsx`).

The prototype's own footer line ("no real authentication") and its demonstration submit are
not used: the form signs in through the real API. The footer carries the application's
academic-prototype notice instead.

## The welcome

- **Top bar:** the brand ("O" sign, OSRIP, OMAN RESOURCE INTELLIGENCE), the language chip
  (switches the application to the other language) and the theme chip (light or dark).
- **Hero:**
  - "Resource intelligence platform";
  - the OSRIP wordmark (always left to right, never mirrored);
  - the platform's name in the visitor's language, with the other language below it (Arabic:
    «منصة عُمان الذكية لمعلومات الموارد», the name chosen on 8 October 2026, SPEC_CONFLICTS
    C58);
  - the lead line;
  - **Enter platform** and **Skip introduction**;
  - three notes (premium interface, Arabic and English, four research domains).
- **Panel:** the four sector images, whole, each a link to its sector page, and **Explore**
  (the Overview).
- **Right to left:** the hero at the right and the panel at the left, as in the design. Below
  790 px, one column: the text, then the panel.

## Behaviour

| Requirement | How |
|---|---|
| Once per browser session | `sessionStorage` `osrip.entrance = shown`, set as soon as it opens: a reload never shows it again in that session. A new session shows it again. If storage is blocked it is not shown, so nobody is trapped. Nothing is sent to the server. |
| Home page only | It opens on `/` only, including when the home page is reached later in the session. A direct link (a sector, the workspace, sign-in, the account) opens its page at once. |
| It waits | Nothing closes it on a timer: the visitor chooses. |
| Enter platform, Skip introduction, Escape | Close it onto the home page, keeping the data mode. Guests stay guests: nobody is sent to sign in. Focus goes to the page's main content, or back to the button that showed it again. |
| A sector card, Explore | Close it and open that sector page, or the Overview. |
| Switch | Account → Settings → *Show it when the home page opens* (`localStorage` `osrip.intro.autoplay = off`). The test configurations use the same switch. |
| Shown again | Footer *Replay opening*, Settings, and the sign-in page's *Back to introduction*. That last one navigates home with `{ welcome: true }`, used once, so a reload does not show it again. |
| Keyboard and focus | A native modal `<dialog>`: focus starts on Enter platform and stays inside it, and every control is reachable with Tab. |
| Reduced motion | No transitions and no hover lift. There is no other movement. |
| Application data not delayed | The page behind renders and loads its data while the welcome is open. |
| No sound | No audio or video elements and no audio API (tested). |

## The sign-in screen

- The design's showcase (OSRIP, "Data provides the picture. Analysis reveals the insight.", the
  four domains) and the form box ("Welcome back").
- **Required: a username and a password, nothing else.** Accounts made with an e-mail address
  type that address in the same field (the hint says so).
- **Show/Hide** reveals the password. It is named "Show password" for screen readers, so the
  Password label still finds only the field.
- Kept from before:
  - Remember me (off by default; a 14-day session on this device);
  - Forgot password and Create account;
  - "Other ways to sign in" (e-mail link, phone, Google, Microsoft: optional, never required);
  - the notices for an unconfirmed e-mail address and for Google and Microsoft returns.
- The real `POST /auth/login` is unchanged, with the same password hashing, sessions, CSRF
  protection, rate limits and server-side roles. A username alone grants nothing, and
  administration still comes only from the role checked by the API.
- *Back to introduction* shows the welcome again.

## Tests

- **`frontend/e2e/entrance.spec.ts`** (mock data, 14 tests on desktop, the phone test also on
  Pixel 7):
  - the first visit in English: names in both languages, the four images loaded, no sound, no
    timer, Enter platform enters the dashboard, and a reload does not show it again;
  - once per session;
  - the data behind loads;
  - Skip keeps the page and data mode;
  - a sector card and Explore open their pages;
  - direct links are never interrupted;
  - the footer shows it again, with focus returned;
  - focus is trapped and every control is reachable;
  - the chips change the application's language and theme (remembered);
  - the Settings switch;
  - Arabic and dark: right to left, hero at the right, OSRIP left to right;
  - reduced motion;
  - phone: one column, everything within the screen.
- **`frontend/e2e-api/welcome-sign-in.spec.ts`** (full stack):
  - only two fields to type in, Show/Hide, Remember me off;
  - a new username account signs in, and a wrong password is refused;
  - an ordinary account has no administration;
  - the administrator keeps it, and the API refuses its request to a visitor;
  - Back to introduction;
  - Arabic and dark layout;
  - phone layout.
- **`frontend/e2e-api/accounts.spec.ts`** (full stack): registration with a username and
  password, the recovery code, older e-mail accounts, and the welcome never blocking sign-in.

## History

- **Until 15 October 2026:** a code-driven 2D vector scene, an illustrated Omani man carrying
  the OSRIP sign in (`EntranceScene.tsx`, `entranceRig.ts`; git commit `24c0cca`).
- **16 October 2026:** the owner's first introduction design, with the two assistants' portraits
  and three resource images (`docs/OSRIP_Intro_Single_File.html`).
- **Later:** a three-second CSS opening, OSRIP's letters rising on a navy and emerald field
  (`opening.css`, removed now).
- **3 November 2026:** the welcome in this document.

The earlier files and their evidence images are in git history.
