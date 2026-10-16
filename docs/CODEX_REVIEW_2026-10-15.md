# OSRIP — first source upgrade, 15 October 2026

## What changed

This is an incremental upgrade of the source archive supplied by the owner, based on
commit 24c0cca673092b9d3887c930c27a0daeed3280ff. It is not the v0 redesign branch.

1. **Dashboard launchpad:** bilingual, responsive cards link to the existing voice workspace,
   studies, scenarios and sources. Existing query/mode preservation is reused.
2. **Research brief builder:** inside the assistant composer, choose electricity, water,
   food security or trade, and a trend, drivers, scenario or web-research goal. The resulting
   Arabic/English draft requests 2022+ evidence, tables, comparable charts, Omani contextual
   factors, uncertainty and citations. It sets the existing answer mode, but does not send
   or charge a request until the user submits. Existing server permissions and guest quota
   still apply. This improves the request; it does NOT guarantee the model will supply every
   requested output. Existing validated server study tools remain authoritative.
3. **Missing portraits:** shared persona image component shows a neutral AI badge on load
   failure, including the intentionally excluded Ilham image. It recovers when the source
   changes. It does not substitute a real person's likeness or claim to generate a portrait.
4. **Direct navigation:** initial presentation opens on the home route only, so opening a
   study/dashboard/account deep link does not force the user through the intro. Replay remains.
5. **Voice identity accuracy:** an unnamed Google voice is no longer assumed to be female.
   Only recognized matching voices are selected. Unsupported combinations keep the existing
   unavailable/text fallback; this does not install Arabic voices or activate a provider.

## Verification actually performed in this review

- Dependency installation using the supplied package-lock.json: succeeded.
- `npm run build`: passed (TypeScript and Vite production build).
- `npm run lint`: passed after implementation.
- `node --experimental-strip-types --test tests/research-brief.test.mjs`: 4 tests passed,
  covering all 32 language/domain/goal combinations and voice-language/persona constraints.
- Production bundle-size warning remains; no warning was hidden.
- Browser regression tests added in `frontend/e2e/review-upgrade.spec.ts`, but NOT executed:
  Chromium downloads returned invalid/truncated archives in this environment. No claim of
  visual/browser verification is made. Run them on the owner's machine before publishing.
- Backend code, database schema and secrets were not changed. Database, provider calls,
  live audio/avatar video, signup/SMS and Visual Studio F5 were NOT tested here.
- Source archive's previous test counts are historical statements, not tests run in this review.

## Important limits

This package does not fix or include the separate v0 branch's reported useContext error;
that branch was absent from the supplied archive. React's official troubleshooting guide
lists invalid hook usage, renderer/version mismatch and duplicate React as possibilities:
https://react.dev/warnings/invalid-hook-call-warning

Browser voice metadata does not include a standardized gender property:
https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice
The existing name-based selector is a compatibility heuristic, not proof of voice identity.

Live model/search/speech credentials must be configured privately on the backend. No key is
included or requested in chat. This review did not publish, merge, contact external services
with credentials, create real study findings or generate new images/videos.

## Local verification commands (PowerShell, frontend folder)

```powershell
npm.cmd ci
npm.cmd run build
npm.cmd run lint
node --experimental-strip-types --test tests/research-brief.test.mjs
npx.cmd playwright install chromium
npx.cmd playwright test e2e/review-upgrade.spec.ts --project=desktop --workers=1
npx.cmd playwright test e2e/review-upgrade.spec.ts --project=mobile --workers=1
```

Use the existing README and `start-osrip.cmd` for the full stack. Credentials and database
must stay in the owner's original environment. Extract this source to a separate folder or
merge only the changed files after comparing local changes. Do not replace a local .env.

## Integration into the project (16 October 2026)

Branch `review/codex-upgrade-2026-10-15`, from `main` at 24c0cca. Not merged or pushed.

**Comparison first.** The archive matched the working tree byte for byte in 546 files. 7 files
differed, all listed in `CODEX_CHANGE_MANIFEST.json`, and 8 files were new; their SHA-256 sums
matched the manifest. The archive leaves out 37 tracked files: Ilham's two portraits and the
evidence screenshots. They stay as they are. The working tree was clean, and `backend\.env`,
`deploy\.env`, the database and the images were not touched. `SHARE_NOTES.md` and
`CLAUDE_NEXT_STEPS_AR.md` describe the archive (for example "Ilham's portrait is missing in
this copy", which is not true here), so they were not added.

**Changed from the archive while integrating:**

- **Texts in the language files.** The builder's and the launchpad's labels are in `en.ts` and
  `ar.ts` (`assistant.brief.*`, `workspace.launchpad.*`), so tsc checks that both languages
  are complete. The builder's controls follow the interface language. The draft is written in
  the answer language, like the suggested questions. The draft templates themselves are
  unchanged.
- **Existing components.** The builder uses `SelectField` and `Button`. After "Use this
  draft" it closes, so the message box with the draft is in view (also on phones).
- **Answer modes in one place.** `BRIEF_MODE` in `researchBrief.ts` maps trend and
  contributing factors to Analyze, scenario to Scenario and evidence to Research. It is
  unit-tested. `researchBrief.ts` has no imports, so Node and the browser tests load it
  directly.
- **Missing portraits.** The fallback is an `<img>` showing an "AI" badge, in the same box as
  the portrait it replaces. The archive's `<span>` had a 2.25 rem minimum size, which would
  have enlarged the 20 px author icon on each reply. That icon now uses the fallback too; the
  archive missed it. Its accessible name is "AI assistant" ("مساعد ذكاء اصطناعي" in Arabic).
- **Entrance tests.** Five tests in `e2e/entrance.spec.ts` expected the entrance on direct
  links. They now test the home-only behaviour, the replay on other pages and that a direct
  link leaves the entrance unseen. `docs/ENTRANCE.md` is updated.
- **Browser test of the fallback.** The archive's test imported React from Vite's dependency
  cache and failed with `createRoot is not a function`. It was replaced by tests in the real
  assistant: a missing Ilham image shows the badge at the same size and recovers when Al Mulhim
  is chosen again, and the present Ilham image loads.
- **New full-stack test.** `e2e-api/research-brief.spec.ts` runs on desktop and phone. It
  checks all 32 drafts and their modes, that nothing is sent and no guest answer is used
  before Send, and that Send then charges exactly once with the edited text. It also checks
  the Arabic layout (right to left, no sideways scrolling or clipped controls) and keyboard
  use without a focus trap.
- **Tooling.** `tools/make_vs_projects.py` also lists `frontend/tests/*.mjs`. The Visual
  Studio files were regenerated.

The test results are in `TEST_RESULTS.md` (2026-10-16). The provider findings are below.

**Services, as found on 16 October 2026.** Setting names only; no values were printed:

| Service | Configured | Live check (one minimal call) |
|---|---|---|
| Anthropic (answers, `claude-sonnet-5-5`) | yes | **fails: HTTP 401 `authentication_error`, "invalid x-api-key"**. The stored value does not have the form of an Anthropic Console API key. |
| Brave Search (web research) | yes | **fails: HTTP 422 `SUBSCRIPTION_TOKEN_INVALID`** |
| OpenAI, Gemini (fallback or cross-check) | no: `OSRIP_OPENAI_*`, `OSRIP_GEMINI_*` missing | not called |
| Azure AI Speech (server voice) | no: `OSRIP_SPEECH_KEY`, `OSRIP_SPEECH_REGION` | not called |
| LiveKit real-time voice, avatar video | no (realtime disabled, no avatar provider) | not called. Talk is push-to-talk with a still portrait. |
| Google and Microsoft sign-in | no | not called |
| Browser voices (Edge on this laptop) | Windows has only Microsoft David and Mark (US English, male) and Zira (US English, female) | English: Al Mulhim uses David and Ilham uses Zira (US, not British). **Arabic: no voice for either persona**, so nothing is read aloud, and the panel does not say why (it only hides Read aloud). Edge's online "Natural" voices did not appear in the automated browser; whether they appear in the owner's own Edge was not checked. |

So the assistant and web research are configured but not working. Questions get the labelled
"not available" reply and are not charged (checked in the real assistant). Nothing here is a
simulated success: the full-stack tests use the backend's scripted test providers, which only
run in tests.
