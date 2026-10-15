# Talking-avatar providers for "Talk": comparison and selection plan

Status, 10 October 2026: **no avatar provider is selected, installed or tested.** No account
has been created with any provider and nothing has been paid for. Talk shows a labelled
**still** portrait of the chosen persona that does not move its lips. Nothing in this document
should be read as a claim that lip synchronisation works.

Since 10 October there are two personas (Al Mulhim and Ilham, `docs/assistant-personas.md`),
so a provider needs **two** avatars. Each persona's avatar id is stored in the assistant profile
(`personas[].avatar.live_avatar_id`); the worker supports the plugins `anam`, `liveavatar`,
`bithuman` and `avatario` (their documented `AvatarSession` arguments), and End call deletes the
LiveKit room so no avatar session keeps running.

## What is verified on this machine

- `livekit-agents` 1.8.5 is installed (the only package approved for real-time voice).
- Its package metadata declares optional extras (plugins) for these avatar services, among
  77 extras in total: `anam`, `avatario`, `avatartalk`, `bey` (Beyond Presence), `bithuman`,
  `did` (D-ID), `lemonslice`, `liveavatar`, `simli`, `synthesia`, `tavus`. None of them is
  installed (`GET /api/v1/assistant/voice/realtime` reports the avatar as not configured).
- The worker that would host an avatar (`backend/app/voice/agent.py`) imports and is wired to
  OSRIP's answer service; it has **not** run in a LiveKit room, because no LiveKit project,
  speech models or keys are configured.

## How an avatar would fit

In LiveKit Agents an avatar is a second participant in the call's room. The OSRIP voice
worker sends the synthesised speech to the avatar service, which returns video (and the same
audio) with the face animated. The browser then shows that video track instead of the static
portrait. Answers still come only from OSRIP's answer service; the avatar only renders them.

Integration steps once a provider is chosen (each needs separate approval):
1. Install `livekit-agents[<extra>]` (a new package: needs approval).
2. Create an account with the provider and accept its terms (the project owner's decision;
   paid plans are likely).
3. Put the provider's credentials in the server's secret settings only (never in the browser
   or in chat), and set `OSRIP_VOICE_AVATAR_PROVIDER` and `OSRIP_VOICE_AVATAR_ID`.
4. Start the provider's avatar session in `entrypoint` before `session.start` (the exact
   class and parameters come from that plugin's documentation; they differ per provider).
5. Add `livekit-client` to the frontend (not approved yet) to show the room's video track.
6. Run the acceptance test below before describing the avatar as working.

## Comparison criteria

| Criterion | Why it matters for OSRIP |
|---|---|
| Arabic speech and lip movement | Al Mulhim answers in Arabic and English; lip shapes must follow Arabic phonemes, not only English. |
| Source image and rights | The OSRIP face is an AI-generated fictional person. The provider must accept a custom image (or a stock avatar we label as such) under terms that allow this use. No real person may be imitated. |
| Disclosure | The video must stay labelled "AI-generated, not a real person" in the interface. |
| Hosting and data | Answer audio and text leave the server for the provider. Check the provider's data retention and region, and whether a self-hosted or on-device option exists. |
| Latency | Extra delay between the answer audio and the moving face; a call should stay conversational. |
| Cost and account | Per-minute or subscription pricing; whether a free evaluation exists. |
| Failure behaviour | When the avatar service fails, the call must fall back to audio with the static portrait, never stop answering. |

## Shortlist to evaluate

The descriptions below summarise how each provider presents itself publicly. **OSRIP has not
verified any of them**; each "to verify" item must be checked in the provider's current
documentation and in the acceptance test.

| Provider (extra) | Presented as | To verify before choosing |
|---|---|---|
| Tavus (`tavus`) | Hosted, real-time video replicas | Arabic lip sync; custom (fictional) image allowed; pricing; data retention |
| Simli (`simli`) | Real-time face animation API | Arabic lip sync; latency; pricing |
| bitHuman (`bithuman`) | Avatar runtime with a local (self-hosted) option | Whether local mode runs on the project's hardware; Arabic quality; licence |
| D-ID (`did`) | Talking heads from a single photo | Real-time support in this plugin version; Arabic; pricing |
| Anam (`anam`) | Real-time interactive personas | Custom face; Arabic; pricing |
| Beyond Presence (`bey`) | Hosted real-time avatars | Custom face; Arabic; pricing |
| LemonSlice (`lemonslice`) | Avatars from a single image | Real-time latency; Arabic |
| Synthesia (`synthesia`) | Video avatars | Whether real-time conversation is supported here; custom face rules |

Recommendation: evaluate **one hosted provider** (for example Tavus or Simli) and **one
self-hosted option** (bitHuman), because self-hosting keeps answer audio on the project's own
infrastructure. Choose only after the acceptance test, and record the result in
`docs/implementation-status.md` and `docs/TEST_RESULTS.md`.

## Acceptance test (to run before any claim of lip synchronisation)

1. Ten scripted answers (five Arabic, five English) of 5-20 seconds, including numbers and
   the name «المُلْهِم».
2. Record the call (with consent). Two reviewers rate lip-sync for each answer (good,
   acceptable, poor); "working" means at least 8 of 10 rated acceptable or better by both.
3. Measure the delay from the end of the question to the first moving frame (median and
   maximum over the ten answers).
4. Interrupt three answers mid-sentence: the face must stop with the audio.
5. Disconnect the avatar service during a call: answers must continue as audio with the
   static portrait, and the interface must say so.
6. Confirm that the "AI-generated, not a real person" label is visible throughout.
