# Assistant personas: Al Mulhim and Ilham

Status, 10 October 2026: **implemented and locally tested** with the scripted model and speech
services. **Live verification is pending**: no speech, LiveKit or avatar account is configured on
this machine, so no real voice, real-time call or lip-synchronised avatar has been heard or seen.

## What the two personas are

| | Al Mulhim / المُلْهِم (default) | Ilham / إلهام |
|---|---|---|
| Image | Fictional Omani man in a white dishdasha with furakha and an embroidered kumma | Fictional Omani woman in a headscarf and an abaya with gold-embroidered sleeves |
| Arabic self-reference | Masculine («أنا المُلْهِم، مساعد OSRIP…») | Feminine («أنا إلهام، مساعدة OSRIP…») |
| Server voice (Azure AI Speech) | `ar-OM-AbdullahNeural`, `en-GB-RyanNeural` (male) | `ar-OM-AyshaNeural`, `en-GB-SoniaNeural` (female) |
| Browser fallback voice | Only voices known to be male | Only voices known to be female |
| Real-time voice (LiveKit) | Not chosen yet (profile `null`) | Not chosen yet (profile `null`) |
| Live avatar | Not chosen yet (profile `null`) | Not chosen yet (profile `null`) |

**What both personas share:**

- the approved project knowledge;
- the analytical tools;
- permissions;
- sources;
- conversation history;
- the guest allowance (five answers per guest session).

Switching persona keeps the conversation and the count, and never changes a factual result. The tests compare both personas' answers to the same question field by field.

**Configuration is not training.** A persona is a stored profile entry: name, introduction, portrait and voice identifiers. Choosing one changes only the identity paragraph at the top of the instructions sent with each question. No model is trained or fine-tuned.

**Images.** Both images come from `docs/Oman_Statistics_References_and_Images_English.docx`, chosen by the project owner on 10 October 2026. That document describes its illustrations as generated artwork of a fictional Omani professional, with no real-person identity implied.

The masters are stored unchanged: `omani-professional.png` and `omani-woman-professional.jpg`, in `frontend/assets/editorial/masters`. They are checked by SHA-256 and recorded in `frontend/assets/editorial/sources.json`.

`tools/build_persona_portraits.py` makes two crops of each, downscaled only:

- a square portrait (432 px) for the avatar;
- a 3:4 half-length figure (600 × 800) for Talk.

**Please confirm** that the woman's image is also generated artwork that the project may use: the document's caption speaks of a single "fictional Omani professional".

## Where each thing is stored

| Item | Where | Changed by |
|---|---|---|
| Name, meaning, introduction, self-description, portrait, voice ids, avatar id | Assistant profile **version 3** (`backend/app/knowledge/assistant_profile_v3.json`, table `assistant_profile`, immutable, SHA-256) | Publishing a new reviewed version: `backend\.venv\Scripts\python.exe -m app.cli assistant-profile publish FILE` |
| A signed-in person's choice | `app_user.assistant_persona` (migration 0017) | Settings on the Account and settings page, the picker in the assistant or Talk |
| A visitor's choice | This browser only (`localStorage` `osrip.assistant.persona`) | The same pickers |
| Who gave each reply | `assistant_message.persona` | Set when the reply is stored |

A voice in the profile must be in Microsoft's published list with the persona's gender (`AZURE_VOICES` in `app/services/assistant/profile.py`). A man's voice for Ilham, a woman's voice for Al Mulhim, or an unknown voice is refused when the file is loaded, so a renamed label can never stand in for a real voice id.

## Modes in Talk

| Mode | When | What the person sees |
|---|---|---|
| **Fallback: push-to-talk, still portrait** | Speech available (server Azure, or the browser's own recognition) | Header badge "Fallback mode: push-to-talk, still portrait", the persona's half-length portrait, a note that live avatar mode is not available. Speak → check the words → send; the answer is read with the persona's voice |
| **Fallback: text only, still portrait** | No speech in this browser or on the server | Badge "Fallback mode: text only, still portrait"; type questions, read answers |
| **Live avatar** | Not available: needs everything under "Live avatar" below, plus approval of the browser package `livekit-client` (decision C60) | Never shown as active today |

**Controls in Talk:**

- the transcript;
- the answer language;
- the microphone (asked for only when Speak is pressed, audio only, never the camera);
- mute;
- Stop speaking (interrupt);
- End call (stops the microphone tracks, any speech request and any playback);
- Close;
- the persona picker.

Greetings get the approved reply, for example «السلام عليكم» → «وعليكم السلام ورحمة الله وبركاته» followed by the persona's introduction once per conversation. "What is OSRIP?" gets its purpose and the three domains:

- Energy and Essential Services (Electricity, Water);
- Food Security;
- Trade.

## Providers, accounts and settings

Keys go in `backend/.env` on the server (or the hosting platform's secret settings). They never go in chat or in the browser. `backend\.venv\Scripts\python.exe backend\scripts\set_provider_keys.py` enters keys without showing them.

### 1. Azure AI Speech: server voices (push-to-talk and read-aloud)

1. In the Azure portal, create an **AI Services / Speech** resource in a region that offers neural voices (for example UAE North).
2. Copy **Key 1** and the **region** (or the resource endpoint).
3. Settings:
   - `OSRIP_SPEECH_PROVIDER=azure`
   - `OSRIP_SPEECH_KEY`
   - `OSRIP_SPEECH_REGION` (or `OSRIP_SPEECH_ENDPOINT`)
4. Run the live check (below).

The voices are already set in the profile. Microsoft's voice list was checked on 10 October 2026: ar-OM has Abdullah (male) and Aysha (female); en-GB has Ryan (male) and Sonia (female).

### 2. LiveKit: real-time calls (optional)

1. Create a LiveKit Cloud project, or run a self-hosted server.
2. Settings:
   - `OSRIP_VOICE_REALTIME_ENABLED=true`
   - `OSRIP_LIVEKIT_URL` (`wss://…`)
   - `OSRIP_LIVEKIT_API_KEY`
   - `OSRIP_LIVEKIT_API_SECRET`
   - `OSRIP_VOICE_STT_MODEL` (a LiveKit Inference speech-to-text model id that handles Arabic and English)
3. Choose a **male** and a **female** voice for Arabic and for English. Use LiveKit Inference descriptors of the form `provider/model:voice_id`. LiveKit's documentation lists Cartesia, Fish Audio, Inworld, Rime and xAI models with Arabic.
4. Listen to each voice with the test sentences below.
5. Publish a new profile version with `personas[].voices.realtime` filled in.
6. Run the worker: `backend\.venv\Scripts\python.exe -m app.voice.agent dev`.
7. In the browser, the client package `livekit-client` is needed. It is **not installed** (not approved), so Talk stays in fallback mode until it is approved and wired in.

**Paid sessions end with the call:**

- End call (`POST /assistant/voice/realtime/end`) deletes the room on the LiveKit server, which removes the agent and any avatar worker at once.
- The agent closes the session and deletes the room when the caller leaves (`close_on_disconnect`, `delete_room_on_close`).
- A time limit applies: `OSRIP_VOICE_MAX_CALL_MINUTES`.

### 3. Live avatar: lip-synchronised video (optional, needs LiveKit)

LiveKit's avatar plugins add an avatar worker that turns the agent's speech into synchronised video. OSRIP supports the plugins whose Python `AvatarSession` takes the avatar id in a documented argument (docs.livekit.io, checked 10 October 2026):

- `anam`;
- `liveavatar`;
- `bithuman`;
- `avatario`.

**Setup:**

1. Create an account with the chosen provider and make **two** avatars from the persona portraits, respecting the provider's rules for likeness and consent. The portraits are generated images of fictional people.
2. Install the plugin. This needs approval, since it adds a package: `pip install "livekit-agents[anam]"` (or the chosen provider).
3. Put the provider's own key in `backend/.env` under the name its guide gives (for example `ANAM_API_KEY`), and set `OSRIP_VOICE_AVATAR_PROVIDER=anam`.
4. Publish a profile version with `personas[].avatar.live_avatar_id` for both personas.
5. Readiness (`GET /assistant/voice/realtime`) lists what is still missing, by name only.

See `docs/avatar-providers.md` for the comparison and the acceptance test.

## Pronunciation and accent: how to verify (pending)

`backend\.venv\Scripts\python.exe backend\scripts\voice_acceptance.py` (needs the Azure settings) runs, for each persona and language:

1. **Synthesis.** Each persona's configured voice reads sentences with Omani place names. Arabic: مسقط، نزوى، صحار، صلالة، الدقم، صور، عبري، البريمي، خصب، ظفار، مسندم، الجبل الأخضر، مصيرة. English: Muscat, Nizwa, Sohar, Salalah, Duqm, Sur, Ibri, Al Buraimi, Khasab, Dhofar, Musandam, Jebel Akhdar, Masirah. It also reads a sentence with a figure.
2. **Recognition round trip.** It transcribes the audio back and reports which names were recognised. This catches clear mispronunciations; it cannot judge accent.
3. **Listening sheet.** It saves every recording plus `results.json` and `listening-sheet.md`. A listener who knows Omani Arabic records whether each name sounds right and what the accent sounds like.

Without the Azure settings the script stops before sending anything and says that live verification is pending.

**Claims:**

- The Arabic voices are Microsoft's **Arabic (Oman) locale** voices. That is a locale, not a tested accent.
- OSRIP does not claim an Omani accent until the listening sheet says so.
- The browser fallback voices depend on the visitor's device and are not verified.

## Verification status

| Item | Implemented | Locally tested | Live |
|---|---|---|---|
| Two personas in profile v3 (names, introductions, portraits, voice ids) | Yes | `test_personas.py` (validation refuses wrong-gender or unknown voices) | — |
| Choice saved (account) or kept (browser) | Yes | `test_personas.py`, `personas.spec.ts` (another browser gets the saved choice) | — |
| Same conversation, allowance and facts across personas | Yes | `test_personas.py` (field-by-field), `personas.spec.ts` | — |
| Greeting «السلام عليكم» → «وعليكم السلام ورحمة الله وبركاته»; purpose and three domains | Yes | `test_personas.py`, `test_mulhim_identity.py`, `personas.spec.ts` | — |
| Server read-aloud uses the replying persona's voice id | Yes | `test_personas.py` (SSML names the voice; `X-Voice` header), `personas.spec.ts` | **Pending** (no Azure key) |
| Browser fallback chooses a voice of the persona's gender | Yes | `voice-gender.spec.ts` (Abdullah/Ryan for Al Mulhim, Aysha/Sonia for Ilham, a notice when none) | Device-dependent |
| Talk: chosen persona large, fallback mode stated, all controls, mic only on press, no camera, tracks released on End call | Yes | `personas.spec.ts`, `talk.spec.ts` | — |
| Real-time call with the persona's voice | Yes (token, agent, voices from profile) | `test_mulhim_identity.py` (token metadata has the persona), `test_voice_bridge.py` | **Pending** (no LiveKit project, no voices chosen, `livekit-client` not approved) |
| End call deletes the LiveKit room (paid sessions end) | Yes | `test_personas.py` (only the caller's room; others 404) | **Pending** |
| Lip-synchronised avatar | Adapter for 4 documented plugins | Unsupported provider refused (unit) | **Pending**: no provider, plugin or avatar ids |
| Arabic and English pronunciation, Omani place names | Check script | Script refuses without a live service (unit) | **Pending** |
