# Accepted JurisDigta guide format

Use the registration episode at `marketing/youtube-shorts/2026-09-09-registracia/` as the first accepted reference. It defines the visual rhythm and evidence level; adapt the instructions and UI scenes to the requested functionality.

## Stable choices

- Primary language: Slovak.
- Duration: 10–15 seconds, portrait 1080 × 1920, 30 fps.
- Narrator: Microsoft `sk-SK-ViktoriaNeural`, edge-tts rate `+8%`, default pitch and volume.
- Presenter: the owner-approved woman represented by `marketing/youtube-shorts/assets/presenter-reference.png`; reusable muted source clip: `presenter-base-4s.mp4` in the same directory.
- Presenter wardrobe/background: white top, navy skirt, white background.
- Closing: cleaned shield on black with `www.jurisdigta.eu`.
- Audio: normalized around -16 LUFS, true peak at or below -1.5 dBFS, AAC 48 kHz.
- Captions: concise Slovak burned-in text plus SRT; add WebVTT to the corporate article when practical.

The reusable presenter base has no audio and no lip-sync. Create new mouth animation for every changed narration. The registration `presenter-lipsync.mp4` says only “Otvorte aplikáciu a kliknite na Registrácia” and is not a generic speaking clip.

## Suggested timing

Use roughly 3–4 seconds for the presenter opening, 6–8 seconds for one or two real UI steps, and at least 2 seconds for the black end card. Shorten copy before speeding the narrator beyond comfortable Slovak speech.

## File contract

Each episode should contain narration text and audio, speech timing and final captions, approved synthetic or empty UI sources, new lip-sync output when the presenter speaks, a deterministic render script, final MP4, poster, upload copy, `verification.json`, and a README with provenance, rights, privacy, commands, and known limitations.

The corporate article copies only the delivery MP4, poster and `.vtt` captions into `corporate-web/assets/`. Its video block uses `muted: false`, a local `poster`, and a local `captions` path. Do not embed YouTube in the article.

## Upload metadata baseline

Use a direct Slovak title ending in `#Shorts`. Describe only the demonstrated functionality, link to the relevant `https://agent.jurisdigta.eu/` route and `https://www.jurisdigta.eu`, disclose the illustrative AI presenter and synthetic voice, and add a small set of accurate hashtags. Do not promise legal representation, outcomes, speed, or pricing that the current product does not guarantee.
