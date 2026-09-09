---
name: jurisdigta-video-guide
description: Create a requested 10–15 second Slovak JurisDigta feature guide, reusable media sources, a matching corporate-web article, and reviewable YouTube Short metadata. Use for one manually requested JurisDigta user-guide episode; do not schedule recurring generation or promotion.
---

# JurisDigta Video Guide

Create one guide only after the owner identifies the functionality. Keep the episode, website article, verification evidence, and upload copy in the same task branch. Follow the repository worktree, environment-sync, documentation, privacy, and review rules.

## Start from the accepted format

Read [references/format.md](references/format.md), the latest accepted episode under `marketing/youtube-shorts/`, and the relevant application code before writing the script. Verify the current public or local UI with an empty form or synthetic data. Never capture customer data, credentials, passwords, or real verification codes. Do not claim that an illustrative step was completed in production.

Run the scaffold helper from the repository root when starting a new episode:

```powershell
.\skills\jurisdigta-video-guide\scripts\new_jurisdigta_video_guide.ps1 `
  -Slug "feature-name" `
  -Title "Slovak title" `
  -NarrationText "Approved Slovak narration"
```

Use `-Synthesize` only when `edge-tts` is already available. It generates the standard `sk-SK-ViktoriaNeural` voice at `+8%`; this is a standard synthetic voice, not a clone. Preserve the exact narration text and generated subtitles.

## Media rules

- Use `marketing/youtube-shorts/assets/presenter-base-4s.mp4` as the reusable, muted presenter input and `assets/presenter-reference.png` for visual review.
- Generate a new lip-sync clip for the current words with MuseTalk 1.5 or another reviewed free/local lip-sync tool. Never reuse mouth movements made for different speech. If generation is unavailable, use the presenter as a silent bookend and place narration over UI scenes.
- Use the cleaned `assets/logo-black-hires.png` on the black end card. Retain `assets/logo-checkerboard-hires.png` in the repository, but do not use its baked-in checkerboard as transparency.
- Export portrait 1080 × 1920 H.264/yuv420p with AAC audio, readable Slovak burned-in captions, and a total duration of 10–15 seconds. Keep the spoken instructions synchronized with the demonstrated step.
- Disclose the AI presenter and synthetic voice. Use only media the owner is authorized to publish. Do not add unlicensed music.

Save narration, subtitles, editable render instructions, poster, final MP4, verification metadata, and upload copy in `marketing/youtube-shorts/YYYY-MM-DD-slug/`. Decode the complete export, inspect representative frames, check audible speech, and document any manual review still required.

## Corporate article

Add the accepted MP4, poster, and optional WebVTT captions to `corporate-web/assets/`. Add one newest-first entry to the `articles` array in `corporate-web/index.html`. Localize title, summary, standfirst, and date in Slovak, German, and English; write the reviewed body in Slovak. Include a direct first-party application link, clear steps, recovery advice where relevant, and the AI-media disclosure. Set the guide video to user-initiated playback with sound enabled and preserve existing article defaults.

Add or update a focused browser regression that loads the real local media, checks dimensions, duration, audio state, captions and link, and saves desktop/mobile screenshots under ignored test output. Update `corporate-web/README.md` and the episode documentation.

## YouTube handoff

Only upload when the owner explicitly asks. Then use the repository's `youtube-shorts-upload` skill with the exact final MP4 and approved copy. Mark realistic generated or altered visuals/audio as AI-generated, use the real target audience, and leave paid promotion off unless the owner says it applies. Prepare a private draft and stop at the final visibility action for the confirmation required by that skill. Do not create recurring uploads or promotions.

## Portability

Commit this skill and its reusable assets. On another clone, install the repository skills with `python scripts/sync_codex_skills.py --force`. Do not rely on ignored tools, caches, credentials, or machine-specific absolute paths.
