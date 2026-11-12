# Claude Code — Implement the Provided OSRIP Welcome/Login Design

Repository: https://github.com/azanalmasaoudi-cyber/OSRIP

I am attaching `OSRIP_Welcome_Login_Design.zip` containing a working HTML visual prototype, two screenshots, and four original premium sector images.

## Your implementation task

1. Inspect the current React/TypeScript codebase, especially `frontend/src/components/layout/Entrance.tsx`, `frontend/src/components/layout/AppShell.tsx`, `frontend/src/pages/SignInPage.tsx`, the existing authentication API/backend and the localization/design system.
2. Recreate the attached welcome and sign-in visual design **natively in the current React app**, reusing existing components, routes, translations and CSS variables. Do not drop in the standalone demo as an iframe or replace the whole frontend.
3. Keep the premium dark charcoal + peach / light cream themes, glass panels, typography, OSRIP branding, responsive sector-image cards, subtle accessible motion, and Arabic RTL/English LTR layout.
4. Use the supplied PNG images exactly for the four OSRIP sectors. Store them under an appropriate existing public asset path; optimize delivery as needed without distorting the images or clipping their embedded Arabic/English titles.
5. Preserve the functional opening introduction lifecycle: Skip, Enter, once-per-session behavior, Replay, direct links and reduced-motion handling. Navigate to the actual dashboard or sign-in according to existing access rules; do not unnecessarily force public guests to log in.
6. Implement **username + password** as the only mandatory sign-in fields. No required email, phone, SMS, WhatsApp or social provider. Allow username/password registration for ordinary users with backend uniqueness rules; allow names without overly strict character requirements but prevent impersonation/unsafe identifiers.
7. Connect the form to the **real existing backend**. Preserve secure password hashing, session and CSRF protection, rate limits, server-side RBAC, and existing accounts through safe migrations. Do not trust a name alone as proof of identity.
8. Preserve admin Azzan securely. Username alone must never grant admin rights. Use a secure recovery mechanism (e.g. single-use recovery codes or administrator-assisted identity-verified reset) for accounts without contact methods. Never hardcode admin passwords or create a shared default password.
9. The HTML prototype intentionally never authenticates; **do not copy its mock submit behavior as production authentication**. Keep backend API error handling and actually test sign-in and recovery.
10. Run lint, typecheck, build, relevant tests, browser checks in both languages/themes and mobile layouts. Verify keyboard navigation, focus, color contrast and status messaging.
11. Work on a separate branch, commit and push tested changes, open a PR for review; never merge into main without my approval. Do not include secrets in Git.
12. Report the files changed, tests actually executed, any blocked external integrations and the PR URL.

**Do not stop at a plan. Implement the supplied visual design in the existing application.**
