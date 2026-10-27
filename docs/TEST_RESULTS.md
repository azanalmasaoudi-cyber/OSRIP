# Test results

## 2026-10-27 (evening): WhatsApp verification, Meta Cloud API (branch `feature/whatsapp-verification`)

What changed (details in INTEGRATIONS.md, "WhatsApp verification"):
- `OSRIP_SMS_PROVIDER=whatsapp`: codes made by OSRIP (only a keyed digest stored) and delivered with a WhatsApp authentication template in Arabic or English, through the Meta WhatsApp Cloud API. Meta's error codes mapped; no retry; the number, code and token never logged.
- Test and production separated: `OSRIP_WHATSAPP_MODE=test` (default) sends only to `OSRIP_WHATSAPP_TEST_RECIPIENTS` and is labelled as a demonstration (status `sandbox`); `production` must be set explicitly and is not set anywhere.
- `scripts/whatsapp_setup.py` (configure with a hidden token prompt, create the template, check the sender and template status; none of them sends a message).
- The phone form and account page say "WhatsApp" when that is the channel, in both languages.

| Check | Result |
|---|---|
| `ruff`, backend `pytest` with database tests | Pass; **906 passed**. New: `test_whatsapp.py` (request format, test-mode recipient list, keyed digest, Meta error mapping, no retry, nothing sensitive in logs, settings), `test_whatsapp_integration.py` (registration through the API in test mode with a simulated Meta API: refused number never reaches Meta, Arabic template, wrong code counted, code works once) |
| `npm run typecheck`, `npm run lint`, `npm run build` | Pass |
| Full-stack browser tests (Edge): `phone.spec.ts`, `verification-change.spec.ts`, new `whatsapp.spec.ts` | **24 passed** |
| Browser (local preview) | An API in WhatsApp test mode with placeholder settings: the form shows the demonstration notice; a number outside the approved list is refused with an explanation and an e-mail alternative, and the server log shows no call to Meta |
| WhatsApp, live | **Not tested**: no Meta developer app yet. The demonstration needs the setup in INTEGRATIONS.md |

## 2026-10-27 (later): e-mail and phone verification (branch `feature/email-phone-verification`)

What changed (details in INTEGRATIONS.md, "E-mail" and "SMS verification"):
- Twilio Verify adapter (`OSRIP_SMS_PROVIDER=twilio_verify`; REST API, no SDK), with Twilio's error codes mapped, no retry, the code sent in the page's language, and logs without numbers or codes. Missing setting names (never values) are shown to administrators on Service health.
- Account e-mails in Arabic and English (the reader's language first), as HTML with a plain-text part.
- Changing a confirmed e-mail address or a verified phone number: current password (or a sign-in within `OSRIP_REAUTH_MINUTES` for accounts without one), proof of the new address or number, and a notice to the confirmed address. Account page: change forms, re-sending a confirmation, and translated errors.
- A per-address limit on phone code checks; the per-address limit on code requests now follows `OSRIP_SMS_PER_CLIENT_HOUR` when it is set higher (production default unchanged at 20 per hour).

| Check | Result |
|---|---|
| `ruff`, backend `pytest` with database tests | Pass; **890 passed**. New: `test_sms_twilio.py` (Twilio requests, authentication, error mapping, timeouts, no number or code in logs), `test_mail_templates.py` (both languages, right to left, escaping, no scripts or images), `test_verification_change_integration.py` (address and number changes, re-authentication, notices, other accounts' addresses never taken, SMTP HTML part via a fake server, per-address limit) |
| `npm run typecheck`, `npm run lint`, `npm run build` | Pass |
| Full-stack browser tests (Edge): `accounts.spec.ts`, `phone.spec.ts`, new `verification-change.spec.ts` | **29 passed**: registration and confirmation, links used once, password reset, magic link, phone registration, wrong and expired codes, resend countdown, delivery failure, linking, changing an address (wrong password refused, old address told), changing a number, Arabic |
| Browser (local preview, Edge) | Account page on a phone-sized screen; change-number form in Arabic (right to left, number and password left to right) with the translated wrong-password error. A throwaway account `ui-check-…@test.invalid` was created in the local development database for this |
| Twilio Verify, live | **Not tested**: no Twilio account. Every Twilio test uses mocked HTTP, so SMS delivery must not be reported as working |
| E-mail, live | **Not tested**: no SMTP relay or e-mail service configured; messages go to the development outbox |

**Remaining:** a Twilio account, Verify service, Oman sender ID registration and the live acceptance test (`backend/scripts/sms_acceptance.py`); an SMTP relay or e-mail service with SPF, DKIM and DMARC, then a real-inbox test in both languages.

## 2026-10-27: OpenAI SDK, datasets, charts and research reports (branch `feature/openai-research-platform`)

What changed (details in AI_RESEARCH_PLATFORM.md):
- OpenAI through the official `openai` SDK (answers and web search): streaming closed when the person stops a question, strict structured outputs, quota errors reported as a balance problem and not retried, consulted search sources, reasoning effort and timeout settings. Checked against developers.openai.com on 2026-10-26.
- Datasets (CSV, Excel, JSON) analysed by the server; an AI summary whose numbers are checked; pie, scatter, grouped-column and histogram charts with a type switch; a table with search, filter, sort and pages.
- Research and dataset reports (migration 0024), exported as PDF (embedded font subset, Arabic shaping and right-to-left order, vector charts), Excel and CSV; platform reports as PDF and Excel.

| Check | Result |
|---|---|
| `ruff`, backend `pytest` with database tests | Pass; **849 passed**. New: `test_openai_sdk.py` (16), `test_datasets.py` (34), `test_datasets_integration.py` (5), `test_documents.py` (19), `test_reports_export_integration.py` (3) |
| `npm run lint`, `npm run build`; full-stack browser tests (Edge) | Pass; full run of all **181** tests: **175 passed**, 3 skipped, 3 failed (two mobile-view timeouts, and missing trace files after a second run started meanwhile and cleared the shared `test-results` folder); the 3 **passed** when rerun on their own (`quality.spec.ts:121`, `research-brief.spec.ts:37`, `interface.spec.ts:137`). New: `e2e-api/datasets.spec.ts` (sign-in required; upload, findings, pie switch, statistics, search, report, PDF and Excel downloads) |
| OpenAI, missing credentials | `python -m app.cli provider-check openai`: names `OSRIP_OPENAI_API_KEY` and `OSRIP_OPENAI_MODEL` as missing and makes no call |
| OpenAI, live | **Not tested**: no OpenAI key is configured here |
| **Real** dataset summary (DeepSeek `deepseek-flash`, Arabic) | Every number in the summary matched the computed results; no sentence removed; the 25,000 value was named as a possible data error |
| **Real** research report (local site, analyst test account) | A live DeepSeek answer about gross generation (verified; 7 sources from NCSI) became a report: question, answer with reference numbers, platform calculations C1 and C2 with their method; PDF, Excel and CSV downloads (HTTP 200, correct types) |
| PDF check | Arabic and English PDFs rendered to images with the Windows PDF renderer and checked page by page (joined letters, right-to-left lines and tables, mixed Arabic and English lines, charts, footers) |
| Browser (local preview, Edge) | Upload, findings, every chart type, Arabic and light mode, search and sort, report creation, report list |
| DeepSeek use for these checks (provider log, 2026-10-27) | 6 answering calls: 51,444 input and 1,751 output tokens |
| Secret scan (every commit on every branch) | No key or `.env` file in history; only setting names, placeholders and fake test keys |

**Remaining:** a live OpenAI test needs an API key with billing on the account; the Docker image (with the PDF font) is prepared but not built here.

## 2026-10-25 (afternoon): research that reads sources and saves verified figures (branch `feature/research-crawl-series`)

What changed (details in RESEARCH_AND_SAVING.md):
- DeepSeek Search and Fetch as the research routes (`OSRIP_RESEARCH_PROVIDER=deepseek`, `OSRIP_RESEARCH_FETCH_PROVIDER=deepseek`), checked against api-docs.deepseek.com (guides/search, api/search, api/fetch) on 2026-10-25. Official Omani hosts are read directly first (DeepSeek Fetch returned 504 for ncsi.gov.om and data.gov.om); NCSI news articles are read from NCSI's own API. Searches and documents are logged and cached (`research_search`, `research_document` with the text read), with daily paid-call limits.
- Tools `submit_observations` (signed-in users with the new `research.submit`; never guests), `research_status`, `make_table`, `make_chart` (only when the question asks for a chart). Backend validation saves a figure only when it is written in an official document read in full, maps to platform codes without ambiguity, and is neither a duplicate nor a conflict; saving goes through the import workflow, one source per document, all or nothing. Reviewers can approve pending or conflicting figures ("Approve and save"; a conflict is saved as a revision beside the published value).
- Tables (one validated table per unit, CSV download with formula-safe cells) and charts (line, bars or grouped bars from the same rows, drawn by the study chart components) in the conversation. Data-update schedules by sector (`kind: data_update`), run by the research worker with no overlap.
- Migration 0023 (search log, documents outside studies, candidate codes, validation and history, job and schedule kinds, `research.submit`).
- Found by the live runs and fixed: the evidence check read the day of a written date ("31 December"), digits in web addresses, a saved record's id and a cited publication's title ("Issue 54") as figures; long paragraphs were cut to 600 characters in excerpts, losing later figures; research answers ran out of model rounds (now 12 rounds, 6 searches and 6 pages in Research mode); and the public observations API refused every year-to-date selection once totals to two different months existed (it now shows the latest end month and offers `ytd_end_month`).

| Check | Result |
|---|---|
| `ruff`, backend `pytest` with database tests | Pass; **772 passed**. New: `test_assistant_datatable.py`, `test_zzzz_research_saving_integration.py` (save once, no duplicate on repeat, conflict kept, reviewer approval as a revision, refusals for viewers, snippets, invented values, secondary sources and mismatched periods, year-to-date selection), grounding cases from the live drafts |
| `npm run lint`, `npm run build`; full-stack browser tests (Edge) | Pass; e2e-api assistant, chat-phone, research, research-workflow, research-brief: **45 passed** |
| **Real** DeepSeek Search | HTTP 200 in 0.5 s with the documented fields; 35 searches logged today |
| **Real** DeepSeek Fetch | Works for Wikipedia (4.4 s), nama.om, omandaily.om, timesofoman.com; **504 for ncsi.gov.om and data.gov.om** (read directly instead) |
| **Real** data.gov.om raw-data API | Documented (`POST /api/1.1/data/details`, example dataset OMINF2016); **HTTP 403 for every anonymous data or metadata request**; its search returned datasets from 2016. Not used |
| **Real** three-turn test, chat endpoint | Turn 1 (research): 2 searches, 3 documents read (OPWP PDF direct, two articles via DeepSeek Fetch), answered with periods and sources; turn 2: backend table of 16 rows in three unit groups, topic kept; turn 3: three line charts (one per unit) whose values are all table values; no chart before turn 3 |
| **Real** three-turn test, website (Edge) | Same results on the page; CSV download UTF-8 with BOM; research summary in turn 1; dark theme and Arabic phone view (right to left, no sideways scrolling). One earlier run withheld turn 2's text (a figure repeated from the previous answer with a wrong citation); the table still showed. Screenshots `docs/evidence/research/` |
| **Real** research and save (analyst account, real ask path) | NCSI release "Total Electricity Generation Rises 4.5%..." (published 2026-08-31) read from NCSI's API; January–July 2026 gross generation **31,732.5 GWh saved**: observation `cf501c1d-6e2d-4a69-8572-a64343b9e789`, candidate `85467db9-...`, source = the NCSI page. A figure taken from a news site was kept **pending** (`source_not_official:secondary`) |
| Persistence | After restarting the API: the observations API returns it (`ytd_end_month=7`); a new guest conversation answered 31,732.5 GWh citing it; repeating the save created **no duplicate** (still one observation; reported as already published) |
| **Real** data update (schedule `kind: data_update`, "Run now", research worker) | Succeeded in 33 s: 6 searches, the NCSI article read, **3 figures saved** (net generation Jan–Jul 2026 30,866.7; gross and net Jan–Jul 2025 30,354.6 and 29,421.5 GWh), 1 duplicate skipped; a second run of the schedule while one was queued was refused |
| DeepSeek use today (provider log, all tests of the day) | answering 336 calls (3.34 M input, 85.5 k output tokens); search 35; fetch 3 successful and 8 failed (failed calls are not billed) |

**Remaining:** data.gov.om needs portal credentials; DeepSeek Fetch cannot reach ncsi.gov.om or data.gov.om; answers vary between runs, and the evidence check still withholds a reply that cites a figure wrongly (by design).

## 2026-10-25: DeepSeek answers live after the top-up (branch `feature/research-crawl-series`)

Every request reached DeepSeek (`deepseek-flash`) after the balance was topped up, but many answers were still lost. Each cause was traced in real DeepSeek output (the model's tool calls and draft, never the key) and fixed in OSRIP; the evidence policy was not loosened:
- **Evidence check, number reading** (`grounding.py`): a number written onto an Arabic word ("و49,132.0", and 49,132.0) was read as "132.0", and a bare "و40000" was not checked at all; an ISO date ("2026-09-27", the cited source's access date) was read as three uncited numbers; list numbers ("**1. Partial year**", "2)") were read as figures; the cited publication's own title ("Statistical Year Book 2026, Issue 54") could not be named. Now: Arabic letters before a number are allowed (Latin letters still mark codes such as CO2); a date must appear in the cited evidence; list numbers at the start of a line are not figures; numbers in the cited source's title, reference period and table locator are allowed. Invented numbers, dates and wrong citations are still withheld.
- **Comparisons across two publications** (`tools.py`): national annual generation (and water production) is published in the Statistical Year Book (2022 to 2024) and the Monthly Bulletin (2025). `compare_periods` and `growth_rate` refused whenever two series matched, even for 2023 against 2024, with "ask the user which one", and DeepSeek retried until it ran out of rounds. Now the series holding both periods is used; periods only in different series come back as `different_series` with both values and their publications recorded as evidence, and no change is calculated across publications.
- **The answer loop** (`service.py`, DeepSeek adapter): the fifth and last round offers only `final_answer`, named in `tool_choice`, and says so in words (DeepSeek also called tools it had seen earlier); a tool call whose arguments are not JSON (DeepSeek's own markup leaked into them) goes back to the model as a tool error instead of ending the answer; an unanswered question is no longer joined to the next one (an unrelated Arabic question failed because it was sent together with the unanswered follow-up); earlier replies in the history lose their evidence ids (each question numbers its evidence from E1, so an old "[E85]" names another record); the system prompt says every sentence, bullet or note with a number carries its own id.
- The server log now says why an answer was withheld (`assistant answer withheld provider=... problems=...`: the check's findings, never the answer text).

| Check | Result |
|---|---|
| `ruff`, backend `pytest` with database tests | Pass; **762 passed**. New: `test_assistant_series_choice.py` (series holding both periods, different publications reported not calculated, history turns), `test_grounding.py` (Arabic prefix, ISO dates, list numbers, the publication title, a real withheld Arabic draft), `test_assistant_conversation_integration.py` (last round answers, unanswered question kept apart, broken arguments sent back), DeepSeek named tool choice and flagged arguments. The new tests fail on the old code (checked for the evidence check) |
| **Real** `provider-check deepseek` | Key accepted; models `deepseek-flash`, `deepseek-v4-pro`; minimal chat call ok in 1.3 to 1.5 s |
| **Real** Arabic request, in the backend without HTTP ("ما آخر قيمة منشورة لإجمالي توليد الكهرباء في عُمان، ولأي فترة؟") | Before the fixes: 4 of 6 withheld (the "و49,132.0" and date cases). After: **5 of 5 answered by DeepSeek**, Arabic, 4 citations each, about 7 to 10 s, no fallback |
| **Real** chat endpoint (`live_assistant_check.py`: English question, "Compare it with the previous year.", Arabic water question; one guest) | Before the fixes: the follow-up and the Arabic question failed (`too_many_rounds`, then `invalid_arguments`, then withheld). After: **the last 3 runs, 9 of 9 answered by DeepSeek** (the last on the final code); the follow-up kept the topic and gave the like-for-like January to August comparison (platform calculation) and the two full years with their publications, without a change across them; each answer used one guest answer (5 → 2) |
| **Real** website (Edge, `/assistant`, English then Arabic interface) | Each answer checked in the API response the page received and on the page. Last two runs: **6 of 6 from DeepSeek** (`answered`, `answer_provider: deepseek`, no fallback, AI label, not the data-report label); the follow-up compared the right series; the Arabic page is RTL and the answer Arabic; header "AI answers available"; "3 of 5 free answers left" after two answers. Earlier runs during the fixes each lost the follow-up (list numbers, then a wrong old evidence id), which led to the last two fixes. Screenshots `docs/evidence/deepseek/web-*.png` |
| No key anywhere | Not in the tracked diff, untracked files or the server log; `backend/.env` is git-ignored and not tracked |

**Remaining:** DeepSeek's answers vary between runs; the follow-up takes about 15 s and up to five model calls, because DeepSeek often guesses an indicator code before listing the indicators. Two requests failed with `network` errors during testing (DeepSeek not reachable for a while; the check passed again minutes later): those questions got the labelled data report and were not charged.

## 2026-10-24 (night): DeepSeek as the website's answer service (branch `feature/research-crawl-series`)

What changed:
- DeepSeek adapter checked against api-docs.deepseek.com (2026-10-24): model `deepseek-flash` (DeepSeek-V4.1-Flash), Chat Completions with function tools, thinking switched off (in thinking mode `tool_choice: required` is refused). New: `GET /models` check of the configured model; distinct categories for every documented error (401 authentication, 402 insufficient_balance, 400/422 "model does not exist" model_unavailable, 429 rate_limited, 500/503 server_error, timeout), with only DeepSeek's error type or a fixed token kept, never its message (which can echo part of a key); an empty balance is no longer reported as OSRIP's own daily budget and lets a configured fallback provider answer; messages in English and Arabic for people and administrators.
- `python -m app.cli provider-check [NAME]`: setting names only, the models the key can use, one minimal live call; never prints the key; needs no database. `scripts/live_assistant_check.py`: project data through the assistant's own tools without a model, then the chat endpoint (English, a follow-up, Arabic) with provider, model, citations, time and the guest's remaining answers.
- `backend/.env`: the key had been pasted as the value of `OSRIP_RESEARCH_API_KEY` (the web-search key, which would have sent it to the search service); the line was renamed to `OSRIP_DEEPSEEK_API_KEY` and `OSRIP_ASSISTANT_PROVIDER=deepseek`, `OSRIP_DEEPSEEK_MODEL=deepseek-flash`, `OSRIP_DEEPSEEK_BILLING_ACKNOWLEDGED=true` added, at the owner's request, without printing the key. The file is git-ignored and not tracked.

| Check | Result |
|---|---|
| `ruff`, backend `pytest` with database tests | Pass; **749 passed**. `test_ai_providers_deepseek.py` 15 (mocked transport built from the documented shapes: errors, timeout, model list, the check never printing the key) |
| `npm run lint`, `npm run build` | Pass |
| **Real** `provider-check deepseek` | Key accepted (`GET /models` 200); models for this key: `deepseek-flash`, `deepseek-v4-pro`; configured model listed: yes. Minimal chat call: **HTTP 402 Insufficient Balance** (category insufficient_balance) in 1.7 s |
| **Real** chat endpoint (`live_assistant_check.py`, API restarted with the new settings: provider deepseek, model deepseek-flash) | Every question reached DeepSeek and got 402; each reply was the labelled data-based report "the AI service account has no balance left" (Arabic for the Arabic question), with published figures cited; follow-up "Compare it with the previous year." kept the electricity topic; **no guest answer used** (5 → 5). Server log: `provider=deepseek model=deepseek-flash code=http_402 detail=insufficient_balance category=insufficient_balance`, no key anywhere in the log |
| **Real** project data, without a model | The assistant's `latest_period` tool: gross electricity generation, Oman, 2024: 49,132 GWh (E1), from the published data |
| **Real** website (Edge, `/assistant` on the restarted API) | Greeting answered at once (approved reply, not charged); question and follow-up shown at once, answered with the labelled data report and "Try the AI answer again"; Retry: still 402, no duplicate; header "AI unavailable · data reports"; status category insufficient_balance. Screenshots `docs/evidence/deepseek/` |

**Blocked:** no AI-written answer could be produced: the DeepSeek account has no balance (402). After a top-up at platform.deepseek.com, `python -m app.cli provider-check deepseek` and `scripts/live_assistant_check.py` repeat these tests; nothing else needs to change.

## 2026-10-24 (evening): the AI Assistant page as one conversation (branch `feature/research-crawl-series`)

What changed:
- `/assistant` is one centred conversation (at most 800px): a compact header (portrait, name, the answer service's real state, the Al Mulhim / Ilham switch, New conversation, Settings), the messages in one scrolling area, and one message box (Send, microphone, Tools). Before the first message: "How can I help you? / كيف يمكنني مساعدتك؟" and up to three examples. Removed from the conversation: the profile card, the "Ready" label, the analysis form and results, help and privacy notes, voice details, the research-mode tabs and the large allowance meter. They are in the Settings drawer (language, voice, Talk, recorded welcome, voice test, conversations, memory, About, Help) and the Tools drawer (answer mode, web search, cross-check, research brief, shortage and surplus analysis, a full study).
- Answers: Markdown rendered safely as page elements (headings, lists, tables, bold, links), citation chips, "Sources (n)" in one line that opens at a cited source, Copy, Read aloud, Retry for a failed answer; the question shows at once; a progress line and Stop while answering (the server streams progress, not words: nothing imitates typing); Enter sends, Shift+Enter is a new line, one submission at a time; a question that could not be sent goes back into the box. "New messages" when reading older messages.
- No mode to choose: the page sends `mode: "auto"`; the server infers Ask, Analyze, Research, Compare or Scenario from the words (`routing.answer_mode`, English and Arabic) and stores the mode used, which the reply shows.
- Follow-ups: the model receives the last 6 messages; when the answer service fails, the data-based report reads a follow-up asking for a figure or comparison together with the latest earlier question that names a topic (small talk is left alone).
- Charts only when asked for, from at least two cited published values of one series, each bar with its evidence id and the sources named.

| Check | Result |
|---|---|
| `ruff check`, `ruff format --check` (backend) | Pass |
| Backend `pytest` with database tests | 740 passed, then 1 failure fixed (the follow-up rule first also gave small talk the earlier topic; now only figure/comparison follow-ups): the affected files 21 passed. New: `test_assistant_conversation.py` (16: mode inference in English and Arabic), `test_assistant_conversation_integration.py` (2: greeting without lookup or charge, a follow-up keeping its topic, the data report keeping it when the provider fails, not charged) |
| `tsc -b`, `npm run lint`, `npm run build`, contrast, unit tests | Pass; 8 unit tests passed |
| New `e2e-api/chat-phone.spec.ts`, desktop and Pixel 7 | 16 passed: greeting at once, no lookup, no charge, welcome hidden, `mode: auto` sent; question then "Compare it with the previous year" answered with 2001 and 2002 cited, mode shown as Compare; sources open at a cited chip; no chart until "Show a chart …" (2 bars, sources); a Markdown heading, table and list; a failed send keeps the draft and Retry sends it once (charged once); a failed answer service gives a labelled, uncharged report; progress and Stop while answering; Enter and Shift+Enter, one request for a double Enter; switching to Ilham; the message box never over the latest message; "New messages" when reading from the top |
| Updated specs (assistant page moved into drawers) | `research-brief`, `analysis-workspace`, `governed-ai`, `research`, `intro-clips`, `mulhim`, `personas`, `research-workflow` (one centred column, one scrolling area, English and Arabic, phone), `sector-voice`, `talk`, `voice-gender` (the full explanations stay in the side panel; the page has one line in Settings): 66 passed and 3 fixed after the first run, then the fixed ones passed |
| Full-stack suite, desktop and Pixel 7 | **175 passed, 3 skipped, 1 failed** (17.7 min). The failure: the orb keyboard test on the phone, interrupted by a page reload when a translation file was edited during the run (the log shows the navigation); `assistant.spec.ts` re-run on both projects: 14 passed |
| Mock suite | 41 passed, 3 skipped |
| Demonstrations | 7 of 7 passed (`playwright.demo.config.ts`; Talk is now opened from the conversation settings) |
| Live, with the real `backend/.env` (API on 8029) | Greeting: approved reply in 207–361 ms, not charged. "What is the latest electricity generation?": the configured Anthropic key is rejected, so a labelled data-based report with published figures (about 1.1–1.5 s), not charged; Retry: still a data report, no duplicate; "Compare it with the previous year.": a data-based report with the electricity figures (the topic kept). 5 of 5 free answers left at the end |

Not verified: a real AI answer (no working provider key on this machine), and streaming of answer text (not offered by the server). Screenshots: `docs/evidence/assistant-redesign/` (before and after, desktop and phone, English dark and Arabic light; the live walkthrough).

## 2026-10-24 (later): the Talk page as one centred column (branch `feature/research-crawl-series`)

What changed:
- `/talk` is one centred column (at most 900px) for both personas: name and state, a compact still portrait (180–220px tall on desktop, 120–160px on phones, 3:4, never stretched), the Al Mulhim / Ilham choice, then the conversation with the message box, Send and Speak. The separate conversation column is gone.
- Removed from the page: the fallback-mode badge, the bordered live-avatar and portrait notes, the LiveKit setup box, the voice-server requirements and the long voice paragraphs under the message box. Live avatar status (setting names only) is now in Settings › Services, and the Talk modes and missing browser voices are explained in Settings › Help; the header's help button opens Settings. When no voice can read answers, Talk shows one line with a "How to fix" link.
- Compact controls: the answer modes, web search, answer language, Mute (an icon) and volume share one row; the research brief opens from the top of the conversation. Only the message list scrolls, at every width (on phones the message box sits below it, not pinned over it: pinned, the suggestions painted through its bottom edge in Chromium).

| Check | Result |
|---|---|
| `npm run lint`, `tsc -b`, `npm run build` | Pass (the existing bundle-size warning remains) |
| New `e2e-api/talk-phone.spec.ts`, desktop (1280×720) and Pixel 7 | 8 passed: column at most 900px and centred; name → portrait → choice → conversation; portrait 180 (desktop) and 160 (phone) px tall, 3:4, `object-fit: cover`; message area 152 px (desktop 720px tall) and 230 px (phone); message box in view; one scrolling region; no sideways scroll; no technical notes; Send, Speak, Mute and modes present; no microphone request before Speak; the same layout for Ilham; Arabic right to left in the light theme; the one-line voice notice and its link; the notes in Settings |
| Full-stack suite, desktop and Pixel 7 | **157 passed, 1 skipped** (13.5 min), including the updated `talk.spec.ts` and `personas.spec.ts` |
| Mock suite | 39 passed, 3 skipped, 2 failed with missing trace files while the full-stack suite ran at the same time (both suites write `frontend/test-results/`); the 2 re-run alone with their own output folder: passed |
| Demonstrations 3–4 and 7 (Talk) | 2 passed |

Screenshots (Playwright, exact viewports): `docs/evidence/talk/` (desktop and phone; English dark, with a conversation; Arabic light).

Follow-up, short screens (found while running OSRIP from Visual Studio in a squashed browser pane: at 915×412 the conversation shrank to 34px and the message box was off screen and could not be reached). Up to 560px tall, Talk now hides the large portrait, puts the name and persona choice on one row, keeps the controls to one row (no volume slider; Mute stays), uses a one-line message box and gives the conversation at least 14rem; if that does not fit, the column scrolls. Measured in the running app: 863×360 (Pixel 7 landscape) message area 74px, Send fully in view; 1280×720 unchanged (portrait 180px, message area 152px). Two new tests in `talk-phone.spec.ts` (Pixel 7 landscape: portrait hidden, message box, Send and Speak fully in view, a reply arrives; 411×257: the message box can be scrolled to and used): `talk-phone`, `talk` and `personas` specs 18 passed, 2 skipped (the short-screen tests run on the phone project only). `npm run lint`, `npm run build`, contrast check: pass. Screenshot `talk-mobile-landscape.png`.

## 2026-10-24: period-first sectors, official statistics feeds, Gemini/DeepSeek, Omani voices, evaluation (branch `feature/research-crawl-series`)

What changed (stages 1–5):
- **Sectors, period first.** Each of the four sectors has its own draft and applied selection (indicator, area, breakdown, frequency, start and end from the published periods only). Nothing is shown before *Show results*; the chart only after *Show chart*; changing the draft hides stale results. A server summary of the applied range (latest, change, highest, lowest, total only for a complete flow). The old Overview became the Analysis workspace (`/workspace`); Overview is now a project introduction.
- **Official statistics** (migration 0022): NCSI Monthly Statistical Bulletin feed (tables 21 and 22), a separate sync worker, delta import (new / revised / unchanged), staged for approval, three moments kept apart, admin schedule and upload, logs and backoff.
- **AI providers:** Gemini free tier as the recommended setup; DeepSeek (usage-billed) only with an explicit billing acknowledgement; Retry-After up to 10 s waited once; the sector selection sent with "Request analysis" as one validated prompt rule. The scripted test model now follows that rule (one lookup of the selected indicator, area, frequency and years; only periods in the range cited).
- **Voices:** one shared volume; "Listen to a short explanation" on sector results (a few sentences from the summary, Al Mulhim `ar-OM-AbdullahNeural` / Ilham `ar-OM-AyshaNeural`), transcript, Stop, nothing automatic.
- **Evaluation:** `tools/evaluate_osrip.py` (measurements), `docs/ACADEMIC_EVALUATION.md`, the evaluation scenario as demo test 9, `docs/DEMO_SCRIPT.md` rewritten for the current flow.

Browsers: installed Edge (`PW_CHANNEL=msedge`). Scripted assistant, search and speech providers in all browser runs.

| Check | Result |
|---|---|
| `ruff check` and `ruff format --check` (backend, `tools/evaluate_osrip.py`) | Pass |
| Backend `pytest` with database tests | **724 passed** (1 min 43 s). New: `test_source_sync.py` (9), `test_zzz_source_sync_integration.py` (3), `test_ai_providers_deepseek.py` (7), `test_assistant_selection_integration.py` (3), `test_series_speech.py` (4); timeline summary and availability tests added. After the last worker change: the sync and selection tests again, 15 passed |
| `tsc -b`, `npm run lint`, `npm run build`, `npm run check:contrast` | Pass (the existing bundle-size warning remains) |
| Frontend unit tests (`node --test tests/export-results.test.mjs tests/research-brief.test.mjs`) | 8 passed |
| Mock suite (`--workers=3`) | 41 passed, 3 skipped |
| Full-stack suite, desktop and Pixel 7 (150 tests) | **149 passed, 1 skipped** (14.9 min). Then, after the scripted model's selection route was added, `interface`, `assistant`, `research-workflow`, `sector-voice` and `governed-ai` on both projects: 33 passed |
| Demonstrations (`playwright.demo.config.ts`) | **7 of 7 passed.** Test 5-6 first failed on a removed workspace control (`choose-frequency-annual`; the test now uses the frequency filter) and passed on re-run. Test 9, the evaluation scenario, passed in 2 of 2 runs. Screenshots `docs/evidence/integrated/20`–`27`, step times `scenario-timings.json` |
| Measurements (`tools/evaluate_osrip.py --check-links`, API with the real `backend/.env` on 8029, verified data) | 105 series; **1338 of 1338** checks passed; CSV equal to the table 105 of 105; 5 of 5 cited sources https and HTTP 200; timeline median 29.3 ms, 95th percentile 43.7 ms (`docs/evaluation/measurements-2026-10-23.md`) |
| Live NCSI check (23 Oct) | List HTTP 200; October 2026 workbook (2,048,496 bytes): 104 new, 22 unchanged, 6 revisions by NCSI; staged for approval, nothing published. `data.gov.om` API: HTTP 403 |
| Startup | `tools\start_osrip.py --check --with-sync-worker`: prerequisites OK. `scripts\sync_worker_dev.py --once`: connects to `localhost:55432/osrip_dev`, 0 feeds due (the feed is off), exit 0. Found: the README's first worker command (`python -m app.worker`) used the default database (`localhost:5432/osrip`, not running here) and waited without output; the README now gives the development command, and the worker logs the database it connects to (no password) |

**Not verified:**
- a live AI answer (Gemini or DeepSeek keys not set; the Anthropic key in `backend/.env` fails authentication);
- Azure speech synthesis (no Azure key; the controls were tested with a scripted tone);
- the scheduled NCSI checks over days (one manual live check only);
- the NCSI data portal API (needs access);
- recorded Canva introductions (no clip supplied yet).

## 2026-10-22: data-based fallback reports, series timelines, background studies and Firecrawl (branch `feature/research-crawl-series`)

What changed:
- **Assistant failure diagnosed.** `OSRIP_ANTHROPIC_API_KEY` in `backend/.env` is truncated (Anthropic answers 401 `authentication_error`) and `OSRIP_RESEARCH_API_KEY` holds the same value, not a Brave key (Brave answers 422). No key value was printed.
- **Graceful degradation** (migration 0021): a failing answer service gives a labelled "data-based report without AI interpretation" (`data_report`), never charged, retryable; sanitized server log with the request id; web-search failure notice with the data's last update; missing inputs and next steps when the data do not answer.
- **Chronological series** (`/series/timeline`, `.csv`), sector pages in the order key indicators → trends → detailed table → analysis → recommendations → sources.
- **Studies:** option kinds, an end-of-study conclusion, the requested recommendation columns; background studies with progress, stop, retry, cache and resume; Firecrawl v2 adapter with robots.txt, SSRF and limit checks; scheduled reports off by default.
- **Interface:** conversation on the right on wide screens; compact identity card; Settings page; navigation Overview … Settings; Help panel; transcripts; one playback at a time; optional recorded-introduction slots.

Browsers: installed Edge (`PW_CHANNEL=msedge`). Scripted assistant, research and speech providers; no Firecrawl key; no real AI, search or Azure Speech call succeeded (see "In the desktop app's browser").

| Check | Result |
|---|---|
| `ruff check` and `ruff format --check` (backend) | Pass |
| Backend `pytest` with database tests | **693 passed**. Two fixes found by the full run: a new test's assertions depended on test order (rewritten), and Alembic's logging setup disabled the app's loggers when migrations ran in the same process (`alembic/env.py` now keeps them; the launcher runs migrations in a separate process, so the server was not affected). New: `test_data_report.py` (21), `test_data_report_integration.py` (4), `test_timeline.py` (11), `test_series_integration.py` (4), `test_crawl.py` (26), `test_research_jobs_integration.py` (8), migration 0021 round trip; balance tests extended (65) |
| `tsc -b`, `npm run lint`, `npm run build` | Pass (the existing bundle-size warning remains) |
| Frontend unit tests | 8 passed (1 new: the report's conclusion and column order) |
| New full-stack spec `e2e-api/research-workflow.spec.ts` | **7 passed**: conversation right of the portrait and results at 1440 px in English and Arabic, composer in view, no long notes under the portrait; phone order identity → conversation → results; a failing answer service gives a labelled, cited data report with a retry and, without a topic, missing inputs and next steps with no figures; the sector page order, chart and table with one dataset id, chronological periods and the CSV; a background study with eight steps, conclusion and next steps; navigation order, Settings services and a schedule created switched off |
| Full-stack suite, desktop and Pixel 7 (141 tests), before the last fixes | 131 passed, 1 skipped, 9 failed. Five were tests expecting the old "unavailable" reply or the old provider list (updated); one was a real regression (the readiness panel rejected the new `firecrawl` provider, fixed); three were sideways scrolling on `/assistant` in Arabic at 1024 px (fixed: two columns only from 1280 px, mirrored chart margins). One phone keyboard test is unrelated to these changes |
| Re-runs after the fixes | Chunk of seven specs on both projects (50 tests): 48 passed, 2 timed out on battery power. The affected specs on Chromium (36 tests, including `research-workflow`, `quality`, `research-brief`, `phone`, `personas`, `upgrade`, `studies`, `workspace` and the map filter): 35 passed; the responsive matrix ran out of its own 5-minute budget, then **passed alone** (six widths, English and Arabic, seven routes including `/assistant`) |
| Mock suite (44 tests) | 40 passed, 3 skipped, 1 failed: the intro's phone test (`entrance.spec.ts:262`, sector images of unequal height while loading). It also fails with this round's only global style change removed (3 of 3 runs), so it is not caused by these changes; the intro is unchanged here |
| `openapi.json` | Regenerated: 137 paths, 158 operations |
| In the desktop app's browser, with the real `backend/.env` (separate ports 8029/5179) | The question «ما آخر قيمة لتوليد الكهرباء، وكيف تغيرت؟» called Anthropic, got 401, and returned an Arabic data-based report with 7 cited figures and two OSRIP change calculations; the server log line has the request id, model, `code=http_401 detail=authentication_error category=authentication` and no key. Settings › Services shows "AI unavailable · data reports" with the fix, and web search "brave · last call failed". The assistant page in Arabic and English at 1440 px (conversation on the right), Arabic at 1024 px and 375 px with no sideways scrolling; electricity series annual and monthly with Arabic month names and year-to-date totals apart. Screenshots: `docs/evidence/2026-10-22-research-workflow/` |

**Not verified:**
- a working AI answer, Brave search and Azure Speech with real credentials (the configured keys are wrong or missing);
- Firecrawl against the live service (no key; the adapter is tested with a mock transport built from the v2 reference);
- scheduled runs over days (the scheduler is off by default; `tick()` is tested directly);
- recorded Canva introductions (no clip supplied yet; the slots stay hidden).
- The laptop ran on battery (27%), which slowed the browser runs.

## 2026-10-20: shortage and surplus analysis, assistant workspace and voices (branch `feature/assistant-analysis-voice`)

What changed:
- **Shortage and surplus analysis** (`/api/v1/analysis/balance`, migration 0020).
- **Assistant workspace** (`/assistant`): the conversation, sector questions and "Run analysis" on one side; Summary, Tables, Charts, Sources and Recommendations tabs on the other; a status bar with Stop generating and Stop audio.
- **Voice:** per-persona voice check, Test voice, pause, resume and stop, numbers and units spoken in words, and a spoken analysis summary.
- **Exports:** formula-safe CSV exports and a readable HTML report.
- **Docs:** the Arabic technical report (`docs/TECHNICAL_REPORT_AR.md`).

Browsers: installed Edge (`PW_CHANNEL=msedge`). Scripted assistant, research and speech providers; no real AI, search or Azure Speech credentials were used.

| Check | Result |
|---|---|
| `ruff check` and `ruff format --check` (backend `app` and `tests`) | Pass |
| Backend `pytest` with database tests (`OSRIP_RUN_DB_TESTS=1`) | **613 passed**. New: `test_balance.py` (52: arithmetic, missing values never zero, classification of inequalities, priority rule, document validation, CSV formula neutralisation, report escaping, pronunciation, Azure voice-list check); `test_balance_integration.py` (10: tables, charts and exports agree, trade balance = exports − imports, electricity not determinable, allowlisted parameters, voice check, Test voice, spoken summary, not-configured message); migration 0020 round trip |
| `tsc -b`, `npm run lint`, `npm run build` | Pass (the existing bundle-size warning remains) |
| `MSBuild OSRIP.sln /t:Build` | Pass (exit 0); projects regenerated with the new files |
| `npm run check:contrast` | Pass, 0 failing pairs |
| Frontend unit tests (`node --test tests/research-brief.test.mjs tests/export-results.test.mjs`) | 7 passed (2 new: client-side CSV neutralisation, report escaping) |
| New full-stack spec `e2e-api/analysis-workspace.spec.ts` | **5 passed**: the stored result agrees with the tabs, CSV and report; electricity is not determinable and names the missing peak demand; Arabic right to left in the light theme at 360 px with no sideways scrolling; voice check, Test voice (`X-Voice: ar-OM-AyshaNeural`) and Stop audio; a sector question fills the results with the assistant's study |
| Full-stack suite, desktop and Pixel 7 (134 tests) | **129 passed**, 1 skipped, 4 failed under load: `interface.spec.ts:123` (`net::ERR_NETWORK_IO_SUSPENDED`), `quality.spec.ts:33` (network-idle timeout) and two `talk.spec.ts` microphone tests. All four, with the rest of `talk.spec.ts`, **passed when re-run alone** (8 passed) |
| Mock suite (44 tests) | **40 passed**, 3 skipped, 1 failed: the intro's phone test (`entrance.spec.ts:262`) timed out right after the full-stack run. Re-run alone three times on both projects: 6 passed. The intro's files are unchanged in this branch |
| `openapi.json` | Regenerated: 125 paths, 143 operations |
| In the desktop app's browser (`osrip-api-verify` and `osrip-frontend-verify`, dev database) | Trade analysis run: a calculated 2025 surplus of 6,103 million OMR; summary, cards, 4 charts each with unit, periods and source, 21 sources, 4 recommendation rows with the ten requested columns. Arabic RTL, light theme and a 375 px phone with no sideways scrolling. Voice: Ilham's voices listed as available, Test voice played, pause held, Stop audio stopped it. `?analysis=<id>` reopens a stored analysis. A render loop found here (`useNarration` received a new array on every render) was fixed |

**Not verified:**
- real AI, web-search and Azure Speech providers (`OSRIP_SPEECH_KEY` and `OSRIP_SPEECH_REGION` are not set in this environment);
- the laptop was on battery and entered Modern Standby during the runs, which caused the load failures above.

## 2026-10-18: the owner's introduction as the opening experience (branch `redesign/dark-dashboard`)

The introduction from `docs/OSRIP_Intro_Single_File.html` is now native React, using its own
five images (`docs/ENTRANCE.md`). It shows once per browser session, on the home page only.
Explore and Skip enter the dashboard. Replay is in the footer and Settings, and Settings has
a switch for the automatic showing.

Browsers: installed Edge (`PW_CHANNEL=msedge`).

| Check | Result |
|---|---|
| `tsc -b`, `npm run lint`, `npm run build` | Pass (the existing bundle-size warning remains) |
| `npm run check:contrast` | Pass, 0 failing pairs |
| Research-brief unit tests | 5 passed |
| `MSBuild OSRIP.sln /t:Build` | Pass (exit 0); the regenerated projects list `tools/build_intro_images.py` |
| Mock browser suite, desktop and Pixel 7 | **41 passed**, 3 skipped (device-specific). Includes 16 introduction tests (`e2e/entrance.spec.ts`) |
| Full-stack suite, desktop and Pixel 7 | **123 passed**, 1 skipped, 5 failed. The laptop was on battery and went into Modern Standby during the run (Kernel-Power 506/507): the five failures ran for 50 minutes and 10 hours across the sleep. Each re-run alone **passed** (`assistant.spec` lines 93 and 134, `geography-forecast.spec` lines 22 and 37, `workspace.spec` line 165). The new test (the introduction switched on, Skip, then a real sign-in) passed |
| `start-osrip.cmd` | Reported `OSRIP is ready: http://localhost:5173/  (API http://127.0.0.1:8010/api/v1)`, release 0.8.0, migration 0019. Through port 5173, `/`, `/overview`, `/theme-init.js`, the five `/images/intro/*.jpg` and `/api/v1/health` and `/health/ready` all returned 200 |
| The running site, in the desktop app's browser | Opened on `/`, then: all five images loaded at 600 px; the portraits use `cover` and the illustrations use `contain`, all at one height; there is no audio; focus was on Explore. Explore → `/overview`; the home page did not show it again. A direct link to `/trade` was not interrupted. In a new session, Skip → `/overview`. The footer replay opened it, and Escape closed it and returned focus |

**Found while testing (existing since the initial import, not caused by this change):**
- The local development database holds both full-year and year-to-date trade figures. With the
  frequency filter on *All*, `GET /observations?section=trade` (and electricity, on the Overview)
  returns 422 `incompatible_series`.
- The browser console warns of duplicate React keys for `TRADE_MERCH_IMPORTS` comparisons.

## 2026-10-16: dashboard redesign (branch `redesign/dark-dashboard`)

The redesign covers:
- dark and light themes, with the Light / Dark / System choice;
- the compact sidebar and the top bar with search;
- the Overview as a dashboard: resource cards, the chart beside its findings, and comparison, studies and sources;
- the compact assistant panel;
- the owner's introduction, with the matching portrait of Al Mulhim.

Browsers: installed Edge (`PW_CHANNEL=msedge`).

| Check | Result |
|---|---|
| `tsc -b` and `npm run build` | Pass (the existing bundle-size warning remains) |
| `MSBuild OSRIP.sln /t:Build` | Pass (exit 0) |
| `npm run lint` | Pass |
| `npm run check:contrast` | **84 pairs pass** (42 per theme, including the sidebar) |
| Research-brief unit tests | 5 passed |
| Mock browser suite, desktop and Pixel 7 | **38 passed**, 3 skipped (device-specific). New tests: theme choice and System following the device; search in both languages and the drafted question; the phone menu and search dialog; the four resource cards; and 12 introduction tests |
| Full-stack suite, desktop and Pixel 7 | **126 passed**, 1 skipped, 1 failed. The failure was a 12 px sideways overflow at 360 px in Arabic: the sign-in label was too wide. It was fixed (icon-only sign-in link on phones) and the responsive matrix re-run passed: 6 widths × 2 languages × 7 routes. New: a dashboard test (published values, chart beside its findings, Analyse, lower row, verified-mode empty states) and recent studies listing a session's studies |
| Screenshots | Dark, light, Arabic right-to-left and phone views, taken from the real stack (scripted test providers); not stored in the repository |

## 2026-10-16: first source upgrade (branch `review/codex-upgrade-2026-10-15`)

The research brief builder, workspace launchpad, missing-portrait fallback, home-only entrance
and the browser voice correction from the 15 October review archive. Details:
`CODEX_REVIEW_2026-10-15.md`, "Integration into the project". Browsers: installed Edge
(`PW_CHANNEL=msedge`); no Playwright Chromium is downloaded on this laptop.

| Check | Result |
|---|---|
| `npm run build` (`tsc -b`, Vite) | Pass; the existing bundle-size warning remains |
| `MSBuild OSRIP.sln /t:Build` | Pass (exit 0) |
| `npm run lint` | Pass |
| `node --experimental-strip-types --test tests/research-brief.test.mjs` | **5 passed** (32 templates, answer modes, voice gender and selection) |
| Mock browser suite, desktop and Pixel 7 | Final run: **35 passed**. Earlier: 31 passed, 2 failed (two test problems, fixed); and one run with 4 entrance timing failures while the laptop was in Modern Standby (10:25–10:28), passed on the immediate re-run |
| Full-stack suite (`playwright.api.config.ts`), desktop and Pixel 7, including the new `research-brief.spec.ts` | **122 passed**, 1 skipped, 1 failed: `quality.spec.ts:76` stalled for 10 minutes while the laptop was in Modern Standby (Windows power log); re-run alone 3 times: 3 passed |
| Brief builder against the real settings (launcher stack) | Draft and mode set, no request sent, guest allowance unchanged; on Send one request, reply "unavailable" (Anthropic `http_401`), not charged; the test conversation was then deleted |
| Launcher (`start_osrip.py --no-browser --keep-db`) | Ready; PostgreSQL started, migrations at head (0019) |
| Follow-up: missing-language voice notice | Build and lint pass. `voice-gender.spec.ts`: **7 passed** (4 existing, 3 new). `assistant`, `talk` and `personas` specs: 17 passed on desktop; `assistant` 7 passed on the phone |

## 2026-10-14: project at its new location (`C:\Users\Dell\Desktop\OSRIP`)

The project moved out of OneDrive with the Windows Desktop. Before re-testing:

- the backend environment was rebuilt with the same 95 packages;
- about 20,800 files that still carried OneDrive cloud markers were rewritten as ordinary
  files, with the same bytes and timestamps.

Details are in `WINDOWS_STARTUP.md`, under "What was verified".

| Check | Result |
|---|---|
| All 589 files named by the solution present at the new path, none empty | Pass |
| `pip freeze` of the rebuilt environment against the moved one | 0 differences; `app` imports from the new path |
| Backend `OSRIP_RUN_DB_TESTS=1 pytest` | **551 passed** (69.7 s) |
| `ruff check` (app, tests, scripts, tools) | Pass |
| `npm ls --depth=0` | All dependencies present |
| `MSBuild OSRIP.sln` Clean, Build | 0 warnings, 0 errors |
| `npm run lint` | Pass |
| Mock browser suite | **27 passed**, 2 skipped. Before the markers were removed: "No tests found" |
| Launcher with Python 3.14.7 (as Visual Studio's F5) | Ready in about 10 s; 4 routes 200; clean stop |
| Backup | `Documents\OSRIP-backups\OSRIP-project-2026-10-14.zip` (592 files, archive test passed) and `osrip_dev-database-2026-10-14.dump` (56 tables with data) |

## 2026-10-11 (evening): files made suitable for this laptop and Visual Studio

No behaviour change and no new package.

Changes:

- `tools/make_vs_projects.py` now writes `OSRIP.sln` as well, with solution folders for the
  repository files and every project set to build.
- The frontend project replaces the failing `npm run clean` step.
- New `.editorconfig` and `.vsconfig` files.
- 14 CRLF files converted to LF, and six generators now write LF.

| Check | Command | Result |
|---|---|---|
| Solution Explorer coverage | scan of project files against `OSRIP.sln` and the three projects | 587 shown. Not shown, on purpose: the project files themselves, `backend\.env` and `deploy\.env` (secrets), `docs\.vscode` (another editor's state) and `Web.config` (old copy, owner's decision pending) |
| Visual Studio build | `MSBuild OSRIP.sln /t:Clean`, `/t:Build`, `/t:Rebuild` (VS Community 18.10.3) | **Pass**: 1 s, 12 s and 15 s; 0 warnings, 0 errors. Before: Clean and Rebuild failed (`npm run clean`: missing script); Build skipped every project |
| Line endings | byte scan of 484 project text files | No mixed files. CRLF only where Windows needs it: `.cmd`, `.sln` and the projects (plus the untouched `deploy\.env`, `Web.config` and `docs\.vscode`) |
| Backend | `OSRIP_RUN_DB_TESTS=1 pytest`; `ruff check`, `ruff format --check` (app, tests, scripts, tools) | **Pass: 551 passed** (67 s); lint pass |
| Frontend | `npm run lint`; `npx playwright test` (mock); type check and build via MSBuild | **Pass**; 27 passed, 2 skipped |

## 2026-10-11 (later): integrated verification

Same machine and toolchain; no new package; no migration. The assistant, search and speech
were the scripted test providers. **No live provider was used**: the stored Anthropic and
Brave keys are still rejected, and there are no OpenAI, Gemini or Azure keys. The
demonstrations and their screenshots are in [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 551 passed**. The first run had 1 failure in a new test: it expected four history sentences, but other modules add years to the shared database. The assertion was fixed to `min(4, rows)` |
| of which: allowance rules | `test_allowance_rules_integration.py` (new) | Pass: 1. One guest session covers every rule:<br>• Greetings are free in both personas and languages.<br>• A failed answer, and its retry with the same request id: 0 used.<br>• A completed answer, then a replay, three speech requests (one narration segment, the whole reply, the segment again), Stop after completion and the reopened study: still 1.<br>• Answers 2–5 through Ilham in Arabic, the voice bridge, Research and Compare: 5.<br>• A sixth answer is refused for both personas and by voice; the greeting is still free.<br>• The database holds exactly 5 charged requests and no reservation |
| of which: live studies | `test_live_study.py` | Pass: 17 (new: in a series answer, each sentence points at its own row, with the same value and period) |
| Allowance, persona, voice and registration modules | targeted run | Pass: 102 |
| Backend lint | `ruff check`, `ruff format --check` | **Pass** |
| Frontend | `tsc -b`, `npm run lint`, `npm run build` | **Pass** |
| Contrast | `npm run check:contrast` | 0 failing pairs |
| Mock browser suite | `npx playwright test` | **Pass: 27 passed**, 2 skipped |
| Full-stack browser suite | `playwright test -c playwright.api.config.ts` (Edge, desktop and Pixel 7) | **114 passed, 3 failed, 1 skipped** (37.1 min). The failures were `phone.spec.ts:99`, `workspace.spec.ts:101` and `workspace.spec.ts:132` (desktop). Each overlapped Modern Standby, logged by Kernel-Power events 506/507: the laptop was on battery at 12 % and went idle. Each failure was a 30-second test timeout with frozen page timers (a countdown stuck at "3 s"). **Re-run alone: 3 passed** (36.8 s) |
| Visual Studio projects | `make_vs_projects.py`, `MSBuild OSRIP.sln` | **Build succeeded**, 0 warnings, 0 errors |
| Demonstration suite (new) | `playwright test -c playwright.demo.config.ts` (verified reference pack loaded) | **Pass: 6 passed**, 17 screenshots in `docs/evidence/integrated/` |
| Provider keys | free checks, outcomes only | Anthropic 401, Brave 422; OpenAI, Gemini and Azure not configured |
| Live provider failure | guest requests on the launcher-started site | Greeting free; question and Research `unavailable`, 0 used |
| Startup | `tools\start_osrip.py --check`, then a full start (ports 8020/5190) | Ready in 13 s; 6 routes answered 200; stopping ended what it started |

Defects found and fixed:

1. Verified electricity and water mix annual, year-to-date and monthly series, but the
   workspace had no frequency choice: it could only say "choose one frequency", and its
   links left the page. It now has a Frequency filter, and the notice's buttons set it in
   place.
2. Two verified series from different sources had the same React key, so one card could be
   dropped. The key now includes the source.

Environment note: the first full-stack run did not start. Its API server timed out because the
development PostgreSQL had stopped uncleanly (stale `postmaster.pid`), probably when the
session that started it ended. `devdb.py start` started it, and the suite was run again.

## 2026-10-11: analytical workspace and live studies (migration 0019)

Same machine and toolchain. No new package (charts: OSRIP's own; transitions: the installed
`motion`). `osrip_dev` upgraded 0018 → 0019 (additive: the `study_event` table) after a
`pg_dump` backup (`osrip_dev-before-0019-20261010-204350.dump`). The assistant, search and
speech were the scripted test providers; **no live speech service was used**.

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 549 passed** (532 before this increment) |
| of which: live studies | `test_live_study.py` | Pass: 16. Covers:<br>• Findings split at sentences, never inside a decimal, and a citation covers its paragraph.<br>• Observation tables: one per unit and series; missing stays missing; each row is tied to its source.<br>• Tables that break the shared rules are never sent; a warning is sent instead.<br>• Narration comes from the findings and points at the rows it cites.<br>• Withheld or cancelled studies confirm no table; study tables are sent unchanged.<br>• Completion that points at an unknown table is refused.<br>• Through the API: events contiguous and in order; the source arrives before its table; table, reply and narration state the same number.<br>• Server-sent events replay, resume after `Last-Event-ID`, then end.<br>• Study and governorate tables.<br>• Cancellation ends with `study.cancelled` and nothing after; a failed search becomes a warning.<br>• Another visitor sees nothing.<br>• Narration segments are spoken one at a time.<br>• Events are deleted with the conversation; the preview is not stored |
| Migration round trip | `test_migrations_roundtrip_integration.py` | Pass: 4. New for 0019: an unknown event type, a repeated sequence number and a non-object payload are refused; events are deleted with their conversation; down to 0018 keeps requests; up again |
| Full-stack browser suite | `playwright test -c playwright.api.config.ts` (Edge, desktop and Pixel 7) | **Pass: 117 passed** (16.4 min; 1 skipped: the phone test in the desktop project). An earlier run had 4 failures, all fixed (two listed below, plus two test assumptions: the page title and a sort button named after one series) |
| of which: workspace | `workspace.spec.ts`, `workspace-phone.spec.ts` | Pass: 6 + 1. Covers:<br>• Filters, and cards with unit, source and stale flag.<br>• Chart points = table rows; sorting changes order, never values.<br>• No geographic view without coverage; verified mode empty state.<br>• Live study: Study tab comes forward; stages; source; final table; finding = table value.<br>• Narration reads N1 and highlights its row, finding and source, with the avatar speaking; stop keeps the highlight.<br>• Failed search shown as a partial failure; source dialog by keyboard with focus return; tabs by arrow keys.<br>• Return to an earlier study (replayed); Arabic labels with unchanged values.<br>• Crafted streams: after a stop, late and superseded events are ignored and nothing becomes final; a table failing browser validation is reported, never drawn.<br>• Phone: three tabs, study brought forward, follow-up, no sideways scroll |
| Changed tests | `assistant.spec.ts`, `upgrade.spec.ts`, `zz-mixed-frequency.spec.ts` | The floating assistant is hidden on the workspace, so these open it from the Electricity page; the mixed-frequency link is checked on the workspace with the Water section chosen |
| Mock browser suite | `npx playwright test` | **Pass: 27 passed**, 2 skipped |
| Frontend | `tsc -b`, `eslint .`, `vite build` | **Pass** (React Compiler and hook-rule findings fixed first) |
| Backend lint | `ruff check`, `ruff format --check` | **Pass** |
| Visual review | full-size screenshots, `docs/evidence/workspace/*.png` | Desktop light and dark, Arabic, phone. Fixed after review: cramped data-mode control and domain tiles, wrapping narration controls, highlight bar touching the cell text, raw provider code, duplicated recommendations heading, a long badge that made phones scroll sideways |

Defects found and fixed during the runs:

1. A badge that cannot wrap ("No licensed boundary map…") made the workspace 27–79 px wider than a phone screen. It is now a wrapping note.
2. The workspace page title did not contain "Overview", the navigation's name for it. It is now "Overview: analytical workspace".

## 2026-10-10 (evening): governed AI and research service (migration 0018)

Same machine and toolchain. No new package. `osrip_dev` upgraded 0017 → 0018 (additive: the
`provider_call` table) after a `pg_dump` backup (`osrip_dev-before-0018-20261010-155306.dump`).
Every external provider ran through scripted routes or mocked HTTP: **no live OpenAI, Gemini,
Anthropic or Brave call was made** (no working key; `docs/AI_PROVIDERS.md`).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 532 passed** (500 with personas) |
| of which: providers | `test_ai_providers.py` | Pass: 21. Covers:<br>• OpenAI Responses requests: function tools only, `store: false`, its own output items replayed.<br>• Gemini Interactions requests: steps sent back exactly; function results named.<br>• Usage counting, including thought tokens.<br>• A timeout is retried once, then reported; a 401 is not retried.<br>• The daily limit and the budget stop a call before anything is sent.<br>• Citations: OpenAI `url_citation` kept with its URL; Gemini byte offsets in Arabic; Search Suggestions kept.<br>• Grounded results never reach the model.<br>• The fallback route is used only after a failure; a cross-check only when asked, with the non-independence note.<br>• A planted instruction in a provider summary stays untrusted and never reaches the review queue.<br>• Routing and data-first search; `data_status` on every item.<br>• Readiness without secrets; grounded expiry |
| of which: through the API | `test_ai_providers_integration.py` | Pass: 9. Covers:<br>• Numbers look up data before the web; recent events may search first.<br>• The answering fallback runs after two OpenAI timeouts, and both are recorded in `provider_call` without tokens or text.<br>• At the daily limit nothing is sent and the guest is not charged.<br>• Google results are shown apart and not used in the answer.<br>• A cross-check runs only on request.<br>• Conflicting sources across routes are both reported and labelled; the agreeing provider summary is not cited.<br>• An invented figure is withheld.<br>• Readiness: viewer 403; `audit.read` alone can view but not test (403); an administrator can test.<br>• Expired grounded results are purged |
| Production settings | `test_api_foundation.py` | Pass: scripted routes (`fake`, `fake-gemini`) as fallback or primary make production refuse to start |
| Migration round trip | `test_migrations_roundtrip_integration.py` | Pass: 3. New for 0018: a capability outside the list and a free-text status (a question) are refused by the database; down to 0017 removes only the log; up again |
| Full-stack browser suite | `playwright test -c playwright.api.config.ts` (Edge, desktop and Pixel 7) | **Pass: 110 passed** (18.5 min, no failures) |
| of which: governed AI | `governed-ai.spec.ts` | Pass: 4. Covers:<br>• Synthetic records labelled "Synthetic demonstration data", never approved official.<br>• Web sources labelled "Unreviewed external evidence".<br>• Numbers checked against data first; one route only.<br>• After a failed first route, the Google-style fallback is shown below the answer, with a clickable citation and the suggestions in a script-free sandboxed frame; the answer does not use it.<br>• Research-mode cross-check: off by default, labelled "not independent evidence".<br>• Provider readiness for an administrator: all four providers unavailable, missing setting names shown, no Test buttons, routing line, subscription note |
| Changed test | `upgrade.spec.ts` | Pass. With a fallback route configured, a failing search now fails on both routes; both failures are listed (the second as `fallback`), and the guest is not charged |
| Mock browser suite | `npx playwright test` | 25 passed, 2 failed, 2 skipped while the backend suite ran at the same time. The 2 failures were entrance timing tests; **re-run alone, all 11 desktop entrance tests passed**. The entrance was not changed |
| Frontend | `tsc -b`, `eslint .`, `vite build` | **Pass** (one accessibility finding on the new cross-check checkbox fixed first) |
| Backend lint | `ruff check`, `ruff format --check` (app, tests, scripts) | **Pass** |
| Evidence | `docs/evidence/ai-providers/*.png` | Provider readiness, the Google results panel (English desktop; Arabic phone header), method summary, search log and a labelled web source, captured from the full-stack run |
| Live verification | Service health → Test; `scripts/set_provider_keys.py` | **Pending**: needs real API keys and model ids for OpenAI and Gemini, and working Anthropic and Brave keys |

Defect found and fixed during the run: the new integration tests left a queued web figure
behind, so in the full suite `test_upgrade_integration.py` found no candidate of its own
(candidates are de-duplicated by source). They now delete what they queued, as other
modules do.

## 2026-10-10 (later): two personas, Al Mulhim and Ilham (migration 0017, profile v3)

Same machine and toolchain. No new package. `osrip_dev` upgraded 0016 → 0017 after a `pg_dump`
backup (`osrip_dev-before-0017-20261010-115044.dump`). Every provider ran through its scripted
test double: **no live speech, LiveKit or avatar service was used** (`docs/assistant-personas.md`).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 500 passed** (474 at Stage 8) |
| of which: personas | `test_personas.py` | Pass: 23. Profile v3 personas with Microsoft-listed voices of the matching gender; seven invalid profiles refused (Ilham with a man's voice, Al Mulhim with a woman's, an invented voice, a wrong-language voice, two defaults, duplicate codes, a default that differs from the identity fields); portraits on disk and in `sources.json` with SHA-256; Ilham's Arabic greeting and feminine introduction; the about reply lists the three domains; prompts differ only in the identity block; SSML names the persona's voice and escapes text; End call deletes only the caller's room; the live voice check refuses without a service |
| of which: through the API | `test_personas.py` (integration) | Pass: profile and voice status publish both personas; a guest switches persona inside one conversation, the allowance goes 0 → 1 → 2 and status, content, evidence, calculations and citations are identical for both personas; replies keep their persona; unknown persona 422; read-aloud uses Aysha/Sonia for Ilham and Abdullah/Ryan for Al Mulhim (`X-Voice`); a signed-in choice is saved and seen by another session; the realtime token carries the persona; another visitor cannot end someone's call |
| Migration round trips | `test_migrations_roundtrip_integration.py` | Pass: 0014–0016 and 0017 down and up; replies kept; profile v3 removed and published again |
| Full-stack browser suite | `playwright test -c playwright.api.config.ts` (Edge, desktop and Pixel 7) | **103 passed, 3 failed** in one run that took 2.5 h instead of about 11 min (the machine was heavily loaded or asleep). All three were phone-sized page-load timeouts (`quality.spec.ts` ×2, `phone.spec.ts` linking); **re-run alone, all 15 phone tests passed** |
| of which: personas and voices | `personas.spec.ts`, `voice-gender.spec.ts` | Pass: 3 + 4. Choosing Ilham changes name, portrait and introduction; facts and allowance unchanged across a switch; the choice survives a reload; a signed-in choice follows to another browser; Talk shows Ilham large, states "Fallback mode: push-to-talk, still portrait", has every control, requests the microphone only on Speak (audio only, never video), reads with `en-GB-SoniaNeural`, keeps the transcript when switching persona and releases the microphone on End call; browser fallback reads Ilham with Aysha/Sonia and says so when no woman's voice exists |
| Mock browser suite | `npx playwright test` | **Pass: 27 passed**, 2 skipped (phone-only tests in the desktop project) |
| Frontend | `tsc -b`, `eslint .` | **Pass** (one accessibility finding in the persona picker fixed first) |
| Backend lint | `ruff check`, `ruff format --check` | **Pass** |
| Live verification | `scripts/voice_acceptance.py` | **Pending**: needs Azure AI Speech; real-time and avatar need LiveKit, chosen voices and avatars, and approval of `livekit-client` |

## 2026-10-10: man's voice only, and the cinematic first-visit entrance

Same machine and toolchain as Stage 8. No new package; no migration. Details of the
entrance in `docs/ENTRANCE.md`.

| Area | Command | Result |
|---|---|---|
| Man's voice: server defaults | `pytest tests/test_voice_gender.py` | **Pass: 2 passed** (Abdullah, Omani Arabic; Ryan, British English; reported by the voice-status route) |
| Man's voice: browser fallback | `playwright test -c playwright.api.config.ts voice-gender` | **Pass: 2 passed**. With a realistic mix of Windows/Edge voices, answers are read with Microsoft Abdullah (Arabic) and Ryan (English). With only female voices installed, nothing is read aloud and the panel says why |
| Entrance | `playwright test entrance` (Edge; desktop and Pixel 7) | **Pass: 12 passed**: the full sequence frame by frame on the fake clock (carry, place in the centre, release, step aside, order and 4–6 s length), data loads behind it, immediate Skip, direct links kept, focus return, Replay from Settings and the footer, Arabic mirrored scene with unmirrored lettering, reduced motion, low-power device, scene that fails to load, phone fit |
| Mock browser suite | `npx playwright test` | **Pass: 27 passed**, 2 skipped (phone-only tests in the desktop project) |
| Full-stack: navigation and voice | `playwright test -c playwright.api.config.ts interface voice-gender --project=chromium` | **Pass: 9 passed** (navigation label now "Account and settings") |
| Frontend | `tsc -b`, `eslint .`, `vite build` | **Pass**. The scene is its own chunk: `EntranceScene-*.js` 19.00 kB (6.35 kB gzip) |
| Backend lint | `ruff check`, `ruff format --check` (app, tests, scripts) | **Pass** |
| Entrance performance | production build, Edge, CDP CPU throttling | 60 fps on desktop and with the CPU 4× or 6× slower (phone size); at 20× slower the watchdog shows the final frame; layout shift 0.0001; the first overview data card in a median 439 ms with the entrance open against 435 ms without |

Not re-run for this change: the whole backend suite (the backend change is comments and one
new test) and the whole full-stack suite (only `interface` and `voice-gender`).

## Stage 8, 2026-10-08: Al Mulhim programme (migrations 0013–0016)

Same machine (Windows 11, Python 3.13.5, Node 24, PostgreSQL 17.11, Edge). Every provider ran
through its scripted test double: **no live provider was tested** (the model and search keys
in `backend/.env` are rejected masked previews; no LiveKit project, speech key or avatar).
New backend package: `livekit-agents` 1.8.5 (approved). No new frontend package.

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database per run) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 474 passed** (365 at the start of the programme) |
| of which: identity | `test_assistant_profile.py`, `test_mulhim_identity.py` | Pass: 15 + 26 |
| of which: studies | `test_study_schema.py`, `test_studies_integration.py` | Pass: schema refuses 14 kinds of inconsistent documents and parameters outside the allowlist (injection-like strings, unknown keys, ranges); builders checked against hand-calculated values (10 % change; no change across a missing or unpublished year; CAGR 6.560 %; ranked governorates with "missing in the source" apart from "no published value"; monthly heatmap or "not available" for annual-only series; availability 100 + 300 − 20 = 380 t with 78.9 % / 26.3 % contributions; partner shares 50 / 33.3 / 16.7 % and sum of squares 0.389; scenario 121 × 1.1² = 146.41 labelled hypothetical; short series withheld from forecasting; programme gap 29 with no impact claim); CSV equals the table; reproduce identical; owner-only list and delete; CSRF for signed-in runs; assistant `run_study` stored with its message in English and Arabic |
| of which: research workflow | `test_research_workflow.py`, `test_research_progress_integration.py` | Pass: stale/undated flags; PDF page locator and document SHA-256; planted instructions in a page cannot redirect the reader (only search-result addresses, private addresses refused); method summary counts; real stages recorded for guests and users; Stop before a tool runs gives `cancelled`, not charged; other visitors and users get 404; **no leakage**: a held-out forecast does not change when its own or later values change |
| of which: migrations | `test_migrations_roundtrip_integration.py` | Pass: 0016 → 0013 → 0016 on a throwaway database; messages and requests kept (statuses mapped), tables and columns removed and recreated |
| of which: voice and guest limit | `test_voice_bridge.py`, `test_guest_channels_integration.py` | Pass: only signed `user:`/`guest:` identities; speech text without citation markers; spoken refusals; worker answers the latest utterance; one five-answer count across typed English and Arabic, research, compare and voice; greetings free after the limit; registration ignores requested roles and verified flags |
| Backend lint and format | `ruff check`, `ruff format` (app, tests) | **Pass** |
| Frontend | `tsc -b`, `eslint .`, `vite build`, `npm run check:contrast` | **Pass** (bundle-size warning pre-existing; 0 failing contrast pairs, light and dark) |
| Mock browser suite | `npx playwright test` (Edge) | **Pass: 19 passed, 2 skipped** (phone-only tests in the desktop project). Includes the entrance: both names and goals, Explore remembered, Skip/Escape, Replay with focus return, Arabic buttons, reduced motion |
| Full-stack browser suite | `npx playwright test -c playwright.api.config.ts` (Edge desktop and Pixel 7) | **Pass: 99 passed** (10.9 min). New: `studies.spec.ts` (4), `talk.spec.ts` (5); updated: `interface.spec.ts` (new navigation) |
| Talk workspace, repeated | `talk.spec.ts --repeat-each=3` | **Pass: 15 of 15** (text fallback, denied microphone, fake-microphone push-to-talk with review, Arabic transcription, failing speech service, interruption, microphone released after End call) |
| Development database | `alembic upgrade head` on `osrip_dev` after `pg_dump` backups | 0013 → 0016, nothing deleted |

Defects found and fixed in this stage are listed in `docs/TECHNICAL_REPORT.md` §6.

### Stage 8 Visual Studio run

`devenv OSRIP.sln /Run` (Visual Studio 2026 Community) started the launcher after the
preview servers were stopped. `GET /api/v1/health/ready`: ready, database ok, migration
`0016_request_progress`; `http://localhost:5173/` returned 200. Through the interface's proxy:
10 study kinds, Al Mulhim profile v2, real-time voice `configured: false` with 6 missing
settings (SDK installed). The model and web search are reported as configured because keys are
present, but those keys are rejected by the providers, so answers fall back to "unavailable".

## Increment 2026-10-05: research and decision-support assistant (migration 0012)

Same machine and toolchain as the 2026-10-02 increment. Migration 0012 (answer mode and
validated structured parts on assistant messages, `research` source class, saved research,
watchlist, alert rules and alert events). New optional extra `pdf`: **pypdf 6.19.0**
installed in the backend venv with the user's approval (pure Python, 395 kB wheel). **No live
provider was tested: there are still no keys for the language model or Brave Search**, and
no SMTP relay. Every provider ran through its scripted test double.

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database per run) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 365 passed** (30 new; the 335 existing tests pass unchanged with the stricter inline-citation check) |
| of which: credential isolation | `tests/test_settings_isolation.py` | **Pass: 1.** The suite removes `OSRIP_*` values from the shell and never reads `backend/.env` (`OSRIP_ENV_FILE=none`; the browser-test server does the same). Checked with a dummy `.env` and a dummy shell key: a normal process loaded both, the test suite neither |
| of which: PDF reading (with pypdf) | `tests/test_research_assistant_units.py` | **Pass: 2.** A generated one-page PDF gives its text with `[page 1]`, its title and its creation date (2024-05-02) as the publication date; a damaged file raises. Through `read_web_page`: the excerpt becomes `pdf_excerpt` evidence (`official`, `document_metadata`), and a reply citing 41,234 GWh from it passes the grounding check. A PDF with no extractable text returns `pdf_no_text` and adds no evidence |
| of which: research assistant units | `tests/test_research_assistant_units.py` | **Pass: 16.** Inline citations (a number needs an `[E#]` in its sentence or paragraph and must match that evidence; Arabic punctuation and digits); recommendation cards withheld for an invented "25% of fuel costs", a missing field, no citation or an unknown citation, and only allowed in Analyze/Research; drivers need one of the ten names, `evidence` needs citations, an assumption may use only the user's numbers; hypotheses cannot carry invented numbers; a conflict needs two values each written in its own source (swapped values dropped); HTML tables read as `Table:` and `cell \| cell` rows, scripts dropped; PDF without `pypdf` → `PdfUnavailable`; source classes official / international / research / secondary and their ranking; compound annual growth (booklet 4.375 %, 4-year case, order, zero start, missing ≠ zero, unit mismatch) and share of total (25 %, part > total, other year, missing) |
| of which: research assistant integration | `tests/test_zy_research_assistant_integration.py` | **Pass: 11.** Growth calculated by the backend in English and Arabic (4.375 %, shown 4.38 with its citation); an incorrect premise ("doubled") corrected first in both languages; missing verified data → "not enough published data", nothing invented; governorate comparison (published / missing in the source / no published value; national total shown and not divided; no wilayat inferred; unknown indicator 422) through the API and through Compare mode; Analyze cards with the invented saving and the uncited driver withheld and counted, none in Ask mode; conflicting official and news figures both reported with a bilingual search (`queries` in English and Arabic); unavailable services (Research without a search provider records `not_configured`; a failing search is reported; no model → labelled lookup); saved research snapshot, Markdown and HTML briefs (escaped title, `default-src 'none'`), rename, ownership 404s, guest 401, delete; source library hides unreviewed web sources from the public and shows pending counts to reviewers; watchlist alerts on publication (new data + above threshold, disabled rule silent, e-mail refused when delivery is disabled or the address unconfirmed, e-mail sent through the outbox after commit, unchanged republication silent, revised value reported as revised, mark read, other users 404) |
| Backend lint and format | `ruff check`, `ruff format --check` (app, tests, scripts) | **Pass** |
| Migration 0012 | applied to the existing `osrip_dev` (additive, no reset); up → down to 0011 → up on a throwaway database | **Pass** |
| Frontend types, lint, build, contrast | `tsc -b`, `eslint .`, `vite build`, `npm run check:contrast` | **Pass** (0 failing contrast pairs) |
| Secrets in the production bundle | search of `dist/` for provider hosts, header names and key names | **None found** |
| Mock-mode browser suite | `PW_CHANNEL=msedge playwright test` | **Pass: 15 passed**, 2 phone-only skipped by design |
| Full-stack browser suite, desktop and Pixel 7 | `PW_CHANNEL=msedge playwright test -c playwright.api.config.ts` | **Final run: 87 passed** (84 existing + 3 new in `research.spec.ts`: Analyze mode with a checked card, withheld count, a citation chip that moves focus to its evidence, save and HTML brief download; watch a series → alert bell → add, switch off and remove an alert rule; public source library, sign-in prompt for saved research, governorate comparison statuses and no sideways scroll). Earlier runs in this increment: 85 passed / 2 failed and 86 passed / 1 failed, all in the new spec (D25, D26); after the fixes the new spec passed 9 of 9 over three repeats |
| Screens (in-app browser, scripted assistant, `osrip_dev`) | Analyze answer at 375 px in English and Arabic; library and Geography in Arabic | Card, drivers (Hypothesis badge), withheld count and inline citation chips shown; Arabic labels and RTL mirroring; no horizontal overflow; 0 console errors. Geography compares the reference-pack governorates (2025 gross generation for five governorates; six "no published value"; national total and the combined Batinah/Dhahirah figure shown separately) |

Defects found and fixed during this increment:

| # | Defect | Fix |
|---|---|---|
| D22 | With web research on by default, every reply would have listed "web search not configured" when no search key exists | The `not_configured` search record is added only in Research mode, where search was explicitly requested |
| D23 | On a phone the new answer-mode selector left the message list 24 px tall (it was already only about 190 px) | Below 640 px the chat scrolls as one column with the composer pinned at the bottom; messages get their full height |
| D24 | A reply citing a documented reference-pack note would have failed validation in the browser (bilingual `title`) | Evidence `title` accepts a string or EN/AR text |
| D25 | Alert on/off switch did not move until the server answered (found by the new browser test, intermittently) | The requested state is shown inside the click handler, and the saved rule replaces the cached one when the server answers |
| D26 | Comparison view lost its container when no governorate had data | The "no data" message is inside the same labelled region |

## Increment 2026-10-02: web research, talking AI Assistant, username accounts, navy/teal identity (API release 0.8.0)

Same machine (Windows 11 Pro; Visual Studio Community 2026 18.10 and 2022 17.14 with the
Python and Node.js workloads; Python 3.13.5 venv; Node 24.21; PostgreSQL 17 portable
cluster; Microsoft Edge). Migration 0011 (usernames, required password change, research
review queue). No new dependencies. **No live provider was tested: there were no keys for
the language model, Brave Search or Azure AI Speech.** Every provider was exercised through
its scripted test double or mocked HTTP.

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database per run) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass: 335 passed** (38 new) |
| of which: web research building blocks | `tests/test_research.py` | **Pass: 31.** Blocks file/ftp schemes, loopback, `localhost`, `.local`, private, link-local and metadata (169.254.169.254), IPv6 loopback, IPv4-mapped IPv6, a host resolving to a mix of public and loopback addresses (DNS rebinding), credentials in the URL and non-default ports. Pins the connection to the checked address with the original Host/SNI. Re-checks redirects to private addresses, refuses https→http, stops redirect loops after 3, enforces size and content-type limits. Strips scripts and forms, reads dates from metadata, classifies the source by host only (lookalikes such as `gov.om.evil.com` are secondary), and grounds web numbers in the cited text. Checks WAV format and duration, and drops evidence markers before speech |
| of which: release 0.8 integration | `tests/test_upgrade_integration.py` | **Pass: 7.** Username account: idempotent, viewer only, no contact details, hash not plaintext; a second run with another password changes nothing. A temporary password allows sign-in (case-insensitive username) but every permission is empty and endpoints answer 403 `password_change_required` until it is changed; weak or wrong-current passwords are refused; the old password stops working. The 12-character policy still applies to ordinary accounts. Web answer cites the NCSI fixture as `official` with dates; the candidate is queued with every provenance field and nothing is added to `observation`. A failed search is reported and **not charged**, and the web can be switched off per question. The review queue needs `research.review` (viewer 403); accepting needs a note; a second review gets 409; CSV export. Voice: transcription by a guest with CSRF (403 without), invalid audio 422; speech only for one's own message (another guest gets 404) |
| Guest allowance (unchanged rules, re-run) | `tests/test_guest_allowance_integration.py` | **Pass: 11** (five answers across languages, sixth refused before any provider call, failures not charged, replay not charged, race for the last slot) |
| Backend lint and format | `ruff check`, `ruff format --check` (app, tests, scripts), launcher with `tools/ruff.toml` | **Pass** |
| Migration 0011 | applied to the existing `osrip_dev` (additive, no reset) and every throwaway test database | **Pass** |
| Frontend types, lint, build, contrast | `tsc -b`, `eslint .`, `vite build`, `npm run check:contrast` | **Pass**. Contrast now reads the tokens from `index.css`: 35 pairs × 2 themes, 0 failing |
| Secrets in the production bundle | search of `dist/` for provider hosts, header names and key names | **None found** |
| Mock-mode browser suite | `playwright test` | **Pass: 15 passed**, 2 phone-only skipped by design |
| Full-stack browser suite, desktop and Pixel 7 | `playwright test -c playwright.api.config.ts` | **84 passed** (80 existing + 4 new in `upgrade.spec.ts`: labelled AI Assistant face in English and Arabic; web citation labelled *Official data* with link, search-engine date and retrieval date, a failed search shown and not charged; data-manager review with required note; username account forced through the password change). Two later partial re-runs, made while the machine was heavily loaded (one took 50 minutes for 37 tests), each timed out once in the 42-page sideways-scroll test; run alone it passed in 80 s |
| Voice in a real browser | Edge with a fake microphone, scripted speech provider | The microphone is requested 0 times before **Speak** and once after. The recording uploads as `audio/wav`, the transcript fills the box and is **not sent**, and the answer is charged once. The reply audio plays: the avatar shows *processing* while it is fetched, then *speaking*. The loudness variable follows the audio (0 → 1.0 → 0.5) and the level bars scale with it; under reduced motion the bars stay still. **Stop speaking** returns to idle with level 0. A typed question plays nothing by itself |
| Screens | Edge screenshots at 1440 px (English and Arabic) and 390 px (reduced motion) | Navy/teal/ivory identity; Arabic panel mirrored (RTL); no horizontal overflow on the phone; 0 console errors |
| Launcher (VS Code task form) | `backend\.venv\Scripts\python.exe tools\start_osrip.py --no-browser` | **Pass**: found the existing data folder automatically, ready in 13 s at `http://localhost:5173/`; direct route and API proxy 200; hard kill ended only its own API and frontend |
| Pre-publication check | `python deploy\predeploy_check.py` | **25 passed, 2 warnings** (no search key, no speech key), 0 failed |

Defects found and fixed during this increment:

| # | Defect | Fix |
|---|---|---|
| D14 | Recording captured silence in Chromium: the AudioContext was created after the permission prompt, outside the click, and stayed suspended | Created synchronously in the click and resumed (`lib/recorder.ts`) |
| D15 | The voice hook's unmount cleanup depended on the whole assistant UI object, which changes with every state; each state change therefore aborted the recording, the transcription request or browser speech recognition (also true before this release for browser recognition) | Effects depend only on the stable `setActivity`/`reportError` callbacks |
| D16 | Synthesised speech could have been silent if the AudioContext was suspended, because the audio element was routed through it | The element plays by itself; the level meter listens to `captureStream()`, so only the animation can fail |
| D17 | The avatar said "Speaking" while the audio was still being fetched | *Processing* until sound plays |
| D18 | `.vscode/launch.json` contained a broken entry (`http://Prj.SPRIP.com${cwd}`) | Replaced by a working Edge debug configuration with a no-browser start task |
| D19 | From Visual Studio, VS Code or a terminal the launcher could not find the existing database, which a packaged app had created in its virtualised AppData | `devdb.py` and the launcher discover it, and the launcher logs the folder used |
| D20 | `serve_public.py serve` never migrated, and the app role would lack rights on new tables | `serve` applies forward-only migrations and re-grants row access |
| D21 | Insights grid: an open question stretched its closed neighbour | `items-start` |

## Increment 0.8.0: reference pack, Windows startup, orb and guest allowance, forecast conditions, editorial images (2026-10-01)

Windows 11 Pro, Visual Studio Community 18.10.2 (Python and Node.js workloads), Python
3.13.5 (backend venv) and 3.14.7 (launcher), Node 24.21, PostgreSQL 17 portable cluster,
Microsoft Edge for browser tests. New dependencies: `motion` 13.4.4 (frontend) and
Pillow 12.3.0 (development tool for image derivatives only). Migrations 0009 (reference
pack) and 0010 (guest allowance).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (fresh database per run) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass**: 297 passed |
| of which: guest allowance (T26–T29) | `tests/test_guest_allowance_integration.py` | **Pass**: 11 — five answers across languages; sixth refused before any provider call (provider call count unchanged); failures and withheld replies not charged; failed-then-retried request id charged once; replay of a delivered reply not charged; request id reused for another question → 422; race of two requests for the last slot → exactly one 201 and one 403; database constraint refuses over-allocation; abandoned reservation released while the completed one stays charged; CSRF and cookie required; per-session abuse limit; lookup not charged; explicit link after sign-in (another account cannot claim it); signed-in replay and daily fair use |
| of which: reference pack and forecast conditions | `tests/test_zz_reference_pack_integration.py` | **Pass**: 8 — includes forecasts withheld for the 2022–2025 annual series (≤ 4 points against a 12-point minimum) and measured vs assumption conditions |
| Backend lint and format | `ruff check`, `ruff format --check` (app, tests, tools) | **Pass** |
| Migration 0010 up, down, up | throwaway database | **Pass** |
| Frontend types, lint, build, contrast | `tsc -b`, `npm run lint`, `npm run build`, `npm run check:contrast` | **Pass** (0 failing contrast pairs) |
| Secrets in the production bundle | search of `dist/` for key and secret patterns | **None found** |
| Mock-mode browser suite | `playwright test` | **Pass**: 15 passed, 2 phone-only skipped by design |
| Full-stack browser suite, desktop and Pixel 7 (first run) | `playwright test -c playwright.api.config.ts` | 76 passed, 4 failed — D9 (focus), one test interrupted by a hot reload, and one expectation still naming `frequency=` (now `period_kind=`); the failing specs then passed (assistant 14/14 on both projects; mixed frequency 6/6 with its prerequisite spec) |
| Full-stack browser suite (second run, final code) | same | **78 passed, 2 failed.** The laptop was suspended during the run (1.5 h instead of ~14 min; the trace shows a 1.2 s browser action inside a 609 s step); both failures are the two desktop assistant tests in that window. Re-run on desktop with the machine awake: **7/7 passed**. The phone project passed every assistant test in both runs |
| Launcher, command line | `tools/start_osrip.py` | **Pass**: start from stopped services (~9 s to ready); hard kill (job object ends API and frontend, watchdog stops PostgreSQL cleanly); occupied port 8010 → API on 8011 with the frontend proxying to it; second launcher detects the first; frontend killed → rest stopped gracefully, exit 1 |
| Visual Studio solution | `MSBuild OSRIP.sln` | **Pass**. Pressing F5 in the Visual Studio window was **not verified** (no access to the IDE interface; `devenv /Build` cannot load Python projects headlessly, even Visual Studio's own template) |
| Editorial images | `tools/build_editorial_images.py`, browser network log | Masters extracted unchanged (hashes match the booklet); 45 derivatives, none wider than its master; a 1366 px desktop requested 360 px (portrait) and 480 px (headers) AVIF files, a 390 px phone at 2× the 640 px portrait; no master requested |

Defects found and fixed during this increment:

| # | Defect | Fix |
|---|---|---|
| D9 | Closing the assistant panel with Escape left focus nowhere: the panel was unmounted while the native dialog was open, so the browser could not restore focus (also true of the previous header button) | The panel mounts on first open and then stays mounted; closing goes through `dialog.close()` and focus returns to the orb explicitly. Covered by `assistant.spec.ts` (orb test) |
| D10 | Series cards overflowed a 375 px screen by 4 px (grid track `min-width: auto`) | `grid-cols-[minmax(0,1fr)]` on the series grid |
| D11 | The English locale file had been re-encoded (26 lines of mojibake, e.g. "Loadingâ€¦") by a tool step, and `docs/API.md` had 7 such lines | Repaired byte-exactly; a check for mojibake patterns finds none |
| D12 | README "Start" had lost an environment variable name; SPEC_CONFLICTS had two table rows joined on one line | Fixed |
| D13 | A guest per-minute limit of 4 could stop a fast reader before the five answers | Default raised to 10 (configurable; C48) |

One failure in the first run (the five-answer test on desktop) was caused by a code change
being hot-reloaded while the test ran; it passed on re-run. `zz-mixed-frequency.spec.ts`
depends on `workflow.spec.ts` running first (a pre-existing order dependency).

Not tested, and why: live Anthropic answers (no key; the scripted provider was used);
Arabic and English speech recognition quality (browser speech service, needs people and
target browsers); microphone permission prompts in a real browser (automated browsers
have no microphone; the code requests it only from the Speak button); Visual Studio F5;
Canva exports (need the owner's approval); any public deployment (none exists).

## Increment 0.6.0: forecasts, scenarios, connected services, interface (2026-09-26)

Same environment as below (Windows 11, Python 3.13.5, Node 24.17.0, PostgreSQL 17.11,
Microsoft Edge). No new dependencies. Migration 0007 (forecast outputs, error records).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (unit and integration, fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass**: 242 passed |
| Backend lint and format | `ruff check`, `ruff format --check` | **Pass** |
| Migration 0007 up, down, up (dev database), and from empty in every test run | `alembic` | **Pass** |
| Frontend types, lint, build, contrast | `tsc -b`, `npm run lint`, `npm run build`, `npm run check:contrast` | **Pass** (0 failing contrast pairs) |
| Mock-mode browser suite | `playwright test` | **Pass**: 15 passed, 2 phone-only skipped by design |
| Full-stack browser suite, Pixel 7 and desktop | `playwright test -c playwright.api.config.ts` | **Pass**: 59 passed |
| Pre-publication check against `deploy/.env.example` | `python deploy/predeploy_check.py --env deploy/.env.example` | Repository checks **pass**. Configuration checks **fail as expected** on placeholders. No live check was run: there is no deployment |

Defects found and fixed during this increment:

| # | Defect | Fix |
|---|---|---|
| D6 | The interface could not read a forecast run that included the seasonal model: its prediction schema allowed only the two older model names | Schema widened; covered by `zzz-forecast-run.spec.ts` |
| D7 | A history with no variation (a perfectly regular series) produced zero-width 80/95% intervals, which claims certainty | No interval is given in that case, and the explanation says why; unit tests added |
| D8 | At 360 px, the Trade calculations overflowed the screen by 30 px (grid track `min-width: auto`) | Grid track `minmax(0, 1fr)`; covered by the responsive matrix |

### Forecast evaluation evidence

**No official series is eligible.** No verified-source data is loaded, and annual
series since January 2022 can never reach the 12-value minimum. Every target shows
"Insufficient data to forecast." in verified mode (`geography-forecast.spec.ts`). The
evidence below exercises the method on a **declared synthetic monthly series** (the
one the browser test publishes, 2022-01 to 2024-12: a seasonal pattern + 4 GWh a month
+ a fixed irregular term). It is **not Omani data and says nothing about forecast
accuracy for Oman**. Reproduce it with `evaluate()` and `forecast_future()` in
`app/domain/forecasting.py`.

Rolling-origin backtest with an expanding window. First training window: 24 months.
Held-out periods: 2024-01 to 2024-12 (12 one-step forecasts per model, each using only
earlier data).

| Model | n | MAE (GWh) | RMSE (GWh) |
|---|---|---|---|
| Last-value baseline | 12 | 184.00 | 207.88 |
| Linear trend | 12 | 376.83 | 417.55 |
| Seasonal naive | 12 | **47.33** | 58.40 |

Selected: seasonal naive, because its MAE is strictly lower than the baseline's. The
horizon is 9 months (min(12, 12, 36/4)). First estimates, with the 95% and 80% bounds:

| Period | 95% low | 80% low | Estimate | 80% high | 95% high |
|---|---|---|---|---|---|
| 2025-01 | 1809.5 | 1834.9 | 1883.0 | 1931.1 | 1956.5 |
| 2025-02 | 1760.5 | 1785.9 | 1834.0 | 1882.1 | 1907.5 |
| 2025-03 | 1903.5 | 1928.9 | 1977.0 | 2025.1 | 2050.5 |

Formula checks in `tests/test_forecasting_v2.py` (12 tests) compare the baseline,
seasonal and OLS intervals with Python's `statistics` module.

### Device and browser coverage (actual)

| Covered | Not covered |
|---|---|
| Microsoft Edge (Chromium) desktop viewport; Pixel 7 emulation (412 px, touch). Responsive matrix at 360, 390, 768, 1024, 1366 and 1920 px, in English and Arabic, on 7 routes (no sideways scrolling). All 19 routes checked at the desktop and Pixel 7 sizes. Reduced motion (`emulateMedia`). Keyboard focus and skip link | Firefox and Safari/WebKit: engines not installed, and downloading them needs your approval. Real phones and tablets. Screen readers. Right-to-left review by a qualified Arabic speaker |

## Increment 0.5.0: accounts, assistant, 2022+ statistics, landing refresh (2026-09-26)

Same environment as below. New dependency: PyJWT 2.15 with cryptography 50.0 (ID-token validation).

| Area | Command | Result |
|---|---|---|
| Backend, all tests (unit and integration, fresh database) | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass**: 219 passed |
| Backend lint and format | `ruff check`, `ruff format --check` | **Pass** |
| Migration 0006 up, down, up (dev database), and from empty in every test run | `alembic` | **Pass** |
| Frontend types, lint, build, contrast | `tsc -b`, `npm run lint`, `npm run build`, `npm run check:contrast` | **Pass** (0 errors, 0 problems, built, 54/54) |
| Mock-mode browser suite | `playwright test` | **Pass**: 15 passed, 2 phone-only skipped by design |
| Full-stack browser suite, desktop and Pixel 7 | `playwright test -c playwright.api.config.ts` | **Pass**: 50 passed |

What the new tests verify:

| Requirement | Evidence | Result |
|---|---|---|
| Registration gives ordinary (Viewer) access only; password sign-in refused until the e-mail is confirmed | `test_identity_integration.py`, `e2e-api/accounts.spec.ts` | Pass |
| Verification, recovery and magic-link tokens expire, are single-use and cannot be revived (database trigger); wrong-purpose tokens fail | same | Pass |
| No account enumeration (identical replies); per-client and per-account request limits; e-mail features labelled when delivery is off | `test_identity_integration.py` | Pass |
| Password reset revokes existing sessions | same | Pass |
| Administrators grant roles explicitly; a new account cannot grant itself one | `test_identity_integration.py`, `accounts.spec.ts` | Pass |
| Google/Microsoft callbacks: PKCE, single-use state bound to the browser, signature, issuer (including the Microsoft tenant), audience, expiry, nonce, provider-confirmed e-mail; no merge on matching e-mail; linking needs a session; an identity cannot be taken over; last sign-in method protected; unconfigured providers reported, not shown as buttons | `test_oidc_integration.py` (14, scripted provider with real RSA keys), `accounts.spec.ts` | Pass |
| Assistant: cited answers carry value, period, source URL and dataset version; an invented number is withheld and the evidence shown; missing data leads to "no evidence", never zero; ambiguity leads to a clarifying question; Arabic in, Arabic out | `test_grounding.py` (7), `test_assistant_integration.py` (16), `assistant.spec.ts` | Pass |
| Assistant numerical accuracy: 2022→2023 change computed by OSRIP (205.25 ÷ 4,100.25 = 5.00579 %), inputs shown under "How calculated" | `test_anthropic_tool_loop_and_request_contract` | Pass |
| Assistant failures: HTTP 500, timeout, malformed response, not configured → a retryable "unavailable" reply | `test_assistant_integration.py`, `assistant.spec.ts` | Pass |
| Assistant permissions and limits: sign-in needed, own conversations only (404 otherwise), deletion removes messages, per-user limits (429), length limit, tools run in a READ ONLY transaction | same | Pass |
| Statistics from January 2022: earlier verified rows rejected; governorate, year and indicator filters; latest period shown per series; "Data unavailable" | `test_import_validation.py::test_verified_statistics_start_in_january_2022`, quality and section browser tests | Pass |
| NCSI conversion: 2022+ only, no unfinished years, exact region names only (all 75 registry areas covered), no guessing | `test_ncsi.py` (sample in an assumed layout, not NCSI data) | Pass |
| Arabic layout and phone usability of the new pages and the assistant panel | `quality.spec.ts` (17 routes × 2 languages × 2 viewports), `assistant.spec.ts` on Pixel 7 | Pass |

**Not run (and why):**

- The live Anthropic API, Google and Microsoft: no keys or client IDs exist.
- A real SMTP server: none is configured.
- A real NCSI export: downloading needs a data.gov.om account.
- Screen reader, Firefox/Safari, usability study: as in the earlier audit.

The NCSI converter's column names are an assumption until checked against a real file.

Defects found and fixed in this increment:

- A dynamic translation key made type-checking take more than 5 minutes; it now takes 10 s.
- The admin role checkbox did not respond until the server answered.
- The scripted test model read merged earlier questions.
- The shared e2e account hit the assistant limit.
- Several lint findings.

---

# Release audit (2026-09-25)

Every number below was produced by a command run on the date shown, in the
environment described. Nothing is carried over from earlier records without being
re-run. **Pass** = executed and met its expectation; **Fail** = executed and did not;
**Not run** = not executed (the reason is given). An empty cell is not a pass.

Code version: working tree of 2026-09-25 (API 0.4.1). The folder is not a git
repository (git is not installed here), so no commit hash can be recorded; see
[DEPLOYMENT.md](DEPLOYMENT.md#before-a-release).

## Environment

| Item | Value |
|---|---|
| Machine | Laptop, 13th Gen Intel Core i7-1355U (12 logical CPUs), 15.7 GB RAM |
| OS | Windows 11 Pro 10.0.26200 |
| Database | PostgreSQL 17.11 (official portable binaries, `backend/scripts/devdb.py`, localhost:55432) |
| Backend | Python 3.13.5, FastAPI 0.141.1, SQLAlchemy 2.0.54, psycopg 3.3.6 (full list: `backend/requirements.lock`) |
| Frontend | Node 24.17.0, React 19, TypeScript 6.0, Vite 8 (full list: `frontend/package-lock.json`) |
| Browser for automated tests | Microsoft Edge (Chromium) via Playwright, desktop 1280 px and Pixel 7 (412 px) profiles |

## Summary

| Area | Command | Result |
|---|---|---|
| Frontend types | `npx tsc -b` | **Pass**: 0 errors |
| Frontend lint (new: ESLint 9, typescript-eslint type-checked, React Hooks, jsx-a11y) | `npm run lint` | **Pass**: 0 problems, after fixing 4 findings (below) |
| Frontend production build | `npm run build` | **Pass**. Warning: main chunk 756 kB (221 kB gzip); map library in a separate lazily loaded chunk (1.06 MB, 286 kB gzip) |
| Colour contrast, light and dark | `npm run check:contrast` | **Pass**: 54 / 54 token pairs |
| Migrations on an empty database | `alembic upgrade head` → `downgrade base` → `upgrade head` | **Pass**: after `downgrade base` 0 tables, 0 enum types, 0 functions remain; re-upgrade reaches `0005_geography_forecasts` with 75 areas |
| Backend unit + integration tests | `OSRIP_RUN_DB_TESTS=1 pytest` | **Pass**: 168 passed, 0 failed, 0 skipped (fresh database per run) |
| Backend lint and format | `ruff check app tests scripts`, `ruff format --check` | **Pass** |
| Interface, mock mode (no backend) | `npx playwright test` | **Pass**: 15 passed; 2 phone-only tests skipped on the desktop project by design |
| Full stack (browser → Vite proxy → FastAPI → PostgreSQL) | `npx playwright test -c playwright.api.config.ts` | **Pass**: 31 passed (25 desktop, 6 phone) |
| Complete journey upload → publication → report → revision | `e2e-api/journey.spec.ts` | **Pass** (part of the 31) |
| Performance workload | `python scripts/perf_workload.py` | Measured (see below). First run exposed 3 defects; results below are from the run after the fixes |
| Backup and restore | `python scripts/backup_restore_drill.py` | **Pass** |
| Deployment configuration (Docker) | — | **Not run**: Docker is not installed here |
| Screen-reader test (NVDA / VoiceOver), automated axe audit | — | **Not run** |
| Firefox and Safari | — | **Not run**: Chromium (Edge) only |
| Usability study with participants | — | **Not run**: needs college clearance (booklet 3.15, 4.6) |

## Checks requested for this audit

| Check | Evidence | Result |
|---|---|---|
| Backend calculation tests (booklet Table 4.2, T01–T03, T09) | `tests/test_calculations.py` (23), `tests/test_analysis_integration.py` (16) | Pass |
| Import validation (Appendix B.1) | `tests/test_import_validation.py` (35 functions, parametrised) | Pass |
| Server-side authorization (SEC01, T06), sessions, CSRF, throttling, suspension | `tests/test_auth_integration.py` (16), `e2e-api/workflow.spec.ts` "viewer is refused… directly" | Pass |
| Import rollback (T11) and duplicate publication | `test_failed_publication_rolls_back_and_keeps_previous_snapshot`, `test_repeated_publication_does_not_duplicate_observations`, `test_concurrent_publication_requests_insert_once` | Pass |
| Report consistency and data-mode preservation (FR05, T07) | `test_report_freezes_inputs_and_survives_a_later_publication`, `test_report_keeps_its_snapshot_after_a_revision_is_published`, `test_report_export_keeps_label_filters_assumptions_and_versions`, `e2e-api/journey.spec.ts` | Pass |
| English and Arabic (UX01, T08) | `e2e/shell.spec.ts` (T08 ×2), `e2e-api/workflow.spec.ts` "Arabic shows the same API values", `quality.spec.ts` (every page in both languages) | Pass |
| Mobile and desktop | `quality.spec.ts` on desktop and Pixel 7; `shell.spec.ts` @mobile tests | Pass after fixing D1 |
| Keyboard access and focus | `quality.spec.ts` (skip link, visible focus ring on navigation, keyboard-only selection moves focus to the result), `shell.spec.ts` (dialog focus trap, Escape, focus return) | Pass |
| Long Arabic labels | `quality.spec.ts`: 12 pages × 2 languages × 2 viewports, no horizontal overflow | Pass after fixing D1 |
| Units and negative numbers | `quality.spec.ts`: trade balance shows `−28,000,000 Omani rial (nominal)` in English and the same number with a leading minus, laid out left-to-right, in Arabic; generation change `2,100 gigawatt-hour` | Pass |
| Empty states | `quality.spec.ts` (no verified data, empty filter, "No data" areas), `shell.spec.ts` | Pass |
| Broken images | `quality.spec.ts`: every `<img>` on the landing page and the credits page has loaded (naturalWidth > 0) | Pass |
| Failed requests | `quality.spec.ts`: API 503 on calculations → explained error with "Try again" while observations still show; network failure on observations → error state | Pass |

## Defects found in this audit

| ID | Defect | Found by | Fix | Re-test |
|---|---|---|---|---|
| D1 | Geography page scrolled sideways by 229 px on a 412 px phone. Screen-reader-only labels (absolutely positioned) inside a horizontally scrolling table escaped their scroll container | `quality.spec.ts` (mobile) | Every `overflow-x-auto` container is now positioned (`relative`) | Pass on both viewports |
| D2 | Data Management mapping step copied server state into local state inside an effect (cascading renders) | ESLint `react-hooks/set-state-in-effect` | The step is keyed by the saved mapping; effect removed | Lint pass; `workflow.spec.ts` upload journey pass |
| D3 | `CardTitle` could render an empty heading; dialog backdrop click had no keyboard equivalent flagged | ESLint `jsx-a11y` | Heading children explicit; the backdrop handler is documented (Escape closes the dialog natively) | Lint pass |
| D4 | A section holding monthly and annual values of one indicator could not be viewed, and **report creation failed** (10 / 10 in the workload). The API correctly refused the mixed read, but the interface offered no way to choose a frequency | Performance workload | Frequency filter on every section (passed to observations, calculations, exports and reports); an explained "Choose one frequency" notice with one button per frequency (sections, overview, area details) | `test_mixed_frequencies_are_refused_with_a_reason_until_one_is_chosen`, `e2e-api/zz-mixed-frequency.spec.ts` pass; workload 0 errors |
| D5 | Change calculations were produced for every consecutive pair of periods: the electricity calculations response for 63 monthly series was 29 MB (median 1.16 s) | Performance workload | Changes cover the latest pair within the selected years, with a note; the year filters select an earlier pair | `test_changes_cover_the_latest_pair_and_an_earlier_one_by_filter` pass; response 286 kB, median 0.40 s |
| T-1 | Three end-to-end tests assumed which series is listed first; they broke once the journey test added data | Full-stack run | Tests now select series by name | Pass |

## Performance (booklet 4.7)

Workload, fully scripted in `backend/scripts/perf_workload.py`; raw record
`docs/perf/perf-2026-09-25.json`:

* Throwaway database with the booklet fixtures plus one generated **synthetic**
  import of 7,560 rows (63 wilayats × 120 months of electricity generation);
  7,572 observations, 2 published versions, 75 areas.
* API served by uvicorn over HTTP on 127.0.0.1, **one worker**, no reload; the
  client (httpx, keep-alive) and PostgreSQL run on the same laptop.
* OSRIP has no application cache. "Warm" means 5 warm-up requests per endpoint
  before measuring (database buffers warm).

Import, one run, each step timed separately:

| Step | Duration |
|---|---|
| Upload (491 kB CSV) | 42.5 ms |
| Validate 7,560 rows | 593 ms |
| Approve | 12.1 ms |
| Publish (one transaction) | 1,739 ms |

Sequential warm reads, 100 requests each:

| Endpoint | Median | p95 | Max | Errors | Response size |
|---|---|---|---|---|---|
| `GET /health` | 0.6 ms | 1.8 ms | 2.4 ms | 0 | 15 B |
| `GET /indicators` | 2.0 ms | 4.0 ms | 5.0 ms | 0 | 7.4 kB |
| `GET /observations` electricity, monthly (63 series) | 397 ms | 542 ms | 658 ms | 0 | 1.28 MB |
| `GET /observations` one wilayat | 10.0 ms | 13.3 ms | 13.5 ms | 0 | 20 kB |
| `GET /analysis/electricity` | 400 ms | 512 ms | 544 ms | 0 | 286 kB |
| `GET /analysis/food_security` | 18.6 ms | 21.1 ms | 22.3 ms | 0 | 10.6 kB |
| `GET /areas` | 7.2 ms | 9.7 ms | 11.2 ms | 0 | 32.8 kB |
| `GET /areas/coverage` | 14.1 ms | 15.6 ms | 16.4 ms | 0 | 19.5 kB |
| `GET /forecast/eligibility` (63 eligible monthly series) | 418 ms | 527 ms | 548 ms | 0 | 77.7 kB |

Concurrent mixed reads, 10 clients × 50 requests over the same endpoints: 500
requests, 0 errors, median 320 ms, **p95 4,687 ms**, max 8,040 ms, 7.4 requests/s
(67 s wall time).

Report generation (electricity, monthly), 10 reports: median 935 ms, p95 1,003 ms,
0 errors.

**What this shows and does not show.** In this environment every endpoint's p95
for a single client with warm database buffers was under 0.6 s. Under 10 concurrent
clients with one worker the p95 was 4.7 s, above the booklet's proposed two-second
target. The target is therefore **not demonstrated** in general: it held only for
single-client warm reads on this laptop. It has not been measured on server hardware,
with several workers, over a network, or with a real (non-synthetic) dataset.

The **first** run of the workload (before fixes D4 and D5) recorded: 100 % errors on
the mixed-frequency observations read, 10 / 10 report failures, a 29 MB calculations
response (median 1.16 s) and a concurrent p95 of 8.0 s with 56 errors. Those numbers
are superseded by the run above; they are kept here because they are how the defects
were found.

## Backup and restore (booklet 3.15)

`backend/scripts/backup_restore_drill.py`; raw record `docs/backup/backup-drill-20260925.json`.

| Step | Result |
|---|---|
| Source | `osrip_dev` at migration `0005_geography_forecasts`: 30 tables, 351 rows, 1 published version (the booklet fixtures) |
| Backup | `pg_dump -Fc`, 108,669 bytes, SHA-256 `06f0f2af…7b34390`, 0.36 s; stored outside the repository (`%LOCALAPPDATA%\OSRIP-dev\backups`) |
| Restore | `pg_restore --exit-on-error` into a newly created, separate database, 0.66 s |
| Fingerprint comparison (migration version, row count of every table, MD5 of every published version's observations, file checksums) | Identical |
| Known dataset version read through the application's own query service | 48,000 / 50,100 GWh, as expected |
| Integrity rules after restore | The trigger still refuses changes to published observations |
| Overall | **Pass**. The restored database was dropped afterwards |

Limits: a single-machine exercise with a small database. Point-in-time recovery,
off-site copies and a scheduled backup job were not set up or tested.
