# Voices: Al Mulhim and Ilham

OSRIP speaks with **Azure AI Speech** (server side; the key and region never reach a browser).

| Persona | Arabic voice | English voice |
|---|---|---|
| Al Mulhim (male) | `ar-OM-AbdullahNeural` | `en-GB-RyanNeural` |
| Ilham (female) | `ar-OM-AyshaNeural` | `en-GB-SoniaNeural` |

Microsoft's language-support page (updated 2026-10-22) lists both Arabic (Oman) voices:
`ar-OM-AbdullahNeural` (male) and `ar-OM-AyshaNeural` (female). The voices are set per persona
in the assistant profile; `OSRIP_SPEECH_VOICE_AR` / `_EN` apply only to a profile without personas.

## Setting it up

In `backend/.env` (never in a chat or a browser):

```
OSRIP_SPEECH_PROVIDER=azure
OSRIP_SPEECH_KEY=<key of your Azure AI Speech resource>
OSRIP_SPEECH_REGION=<its region, e.g. uaenorth>
```

Then open **Settings › Voice** (or the assistant's voice details): each persona's voices show
"listed by the service" only when the configured Azure resource's own voice list contains them
(`GET https://<region>.tts.speech.microsoft.com/cognitiveservices/voices/list`), and **Test voice**
plays a fixed sentence in the chosen persona's voice, with its transcript.

**Cost.** Microsoft's price page (checked 2026-10-24) lists a free tier (F0) of 0.5 million
neural text-to-speech characters and 5 audio hours of speech to text per month. Whether your
resource is on F0, and how much of it is left, is shown in the Azure portal; OSRIP does not and
cannot verify it. Nothing here should be read as "the voice service is free".

## What the person controls

* **Nothing plays by itself.** Speech starts only after Read aloud, Test voice or Listen.
* **Test voice** (assistant voice panel): fixed sentence, Pause/Resume, Stop, volume, transcript.
* **Read aloud** (assistant replies): Mute, Pause/Resume, Stop, volume.
* **Listen to a short explanation** (sector results): a few sentences built from the summary of
  the applied selection (latest value, change over the range, missing periods, total where it is
  valid, provisional status, publisher), not the table read row by row. Spoken numbers are
  rounded for listening (one decimal; two below 10); the table and the transcript beside the
  player keep the exact figures. Stop and volume are beside it.
* **One volume** for spoken answers, voice tests and explanations, remembered in this browser;
  the recorded welcome keeps its own volume. Starting one playback stops any other.
* **Without the server voice** the page says so, can show the words, and offers to read them with
  a browser voice **only if this browser actually has a voice for that language** (labelled as
  the browser's voice, not the persona's). OSRIP never depends on a browser having Arabic voices:
  the Edge used in testing here had English voices only.

## The recorded welcome is separate

The Canva AI Voice introductions (`frontend/public/audio/intro/`) are fixed recordings of one
welcome sentence each. They never speak answers or results; dynamic speech is always Azure.

## Verified here, and not

* Verified: the voice list check, the endpoints and the controls through the real API with the
  scripted test speech provider (a tone, not a voice; refused in production); the two personas map
  to `ar-OM-AbdullahNeural` and `ar-OM-AyshaNeural` in those requests.
* **Not verified:** real Azure synthesis. No Azure key is configured on this machine, so no
  Arabic audio from Azure was heard. After setting the key, use Test voice for both personas in
  Arabic to confirm.
