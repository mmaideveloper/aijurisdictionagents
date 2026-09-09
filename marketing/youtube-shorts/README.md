# JurisDigta video guides

Create a video only when the owner requests one. There is no recurring automation,
automatic promotion, or automatic YouTube upload. The owner uploads manually to
https://www.youtube.com/@mmaideveloper. Slovak is the primary language.

Each Short explains one small, currently verified functionality in 10–15 seconds,
portrait 1080 × 1920, H.264 MP4 with readable captions. Save each episode in
`YYYY-MM-DD-feature/` with its MP4, editable source, subtitles, upload copy and
verification notes. Follow repository branch/worktree rules for new episodes.

## Visual identity

- Use the same presenter shown in `assets/presenter-reference.png` for every guide.
  Reuse the owner's existing `corporate-web/assets/jurisdigta-sk.mp4` footage for
  appearance consistency. Do not infer her identity or clone her voice.
- `assets/presenter-base-4s.mp4` is the prepared four-second, muted 650 × 1080
  presenter source for future lip-sync generation. Generate new mouth movement for
  each new narration; the current episode's lip-sync is specific to its words.
- Preserve the reference's white background and navy styling; finish with the
  shield logo and `www.jurisdigta.eu` on black.
- `assets/logo-black-hires.png` is the cleaned 1254 × 1254 generated logo master
  for black end cards. It is opaque RGB, not a transparent PNG. Its clean outer
  contour avoids the detached white pixels visible in the owner's old video.
  Do not chroma-key white: silver and white are intentional parts of this logo.
- The higher-resolution logo is a generated interpretation of the original,
  with some internal design differences, and remains a review draft.
- `assets/logo-checkerboard-hires.png` preserves the first generated version at
  the owner's request. Its gray checkerboard is baked into the RGB image; it is
  not transparent. Use the black-background version for the current video.
- Use a similar Slovak female voice for new instructional narration; the owner
  explicitly allowed this instead of requiring the original Azure voice. The
  registration episode uses `sk-SK-ViktoriaNeural` through edge-tts, rate +8%.
  Every registration instruction is spoken. Its opening presenter scene is
  lip-synced with MuseTalk 1.5; subsequent narration accompanies the form and an
  email graphic. Reuse this approach for future guides, or generate additional
  lip-sync footage when capacity is available. Do not reuse unrelated old speech.
  See the episode README for synthesis provenance, source files and limitations.

## Free tools and minimal runnable example

FFmpeg is the free local renderer: https://ffmpeg.org/. No paid video API is used.
The tested Windows build is from the ffmpeg-static project's b6.1.1 release:
https://github.com/eugeneware/ffmpeg-static/releases/tag/b6.1.1.
Keep executables and downloaded dependencies under ignored `runs/`, outside Git.
Shotcut is an optional free manual editor: https://shotcut.org/.
The logo was edited with Codex's built-in imagegen tool, not a separate purchased
API service. This is not a promise that account usage has no cost.

From the repository root, supply an installed FFmpeg executable:

```powershell
.\marketing\youtube-shorts\2026-09-09-registracia\render.ps1 -FfmpegPath C:\Tools\ffmpeg.exe
```

The script renders the MP4, checks full decoding and extracts a final-frame poster.
Arial and FFmpeg's libass, H.264 and PNG support are required. No Python, application
services, model credentials or new environment variables are required for rendering.

## Review and privacy

Inspect current code and the public UI before describing a feature. Use empty forms
or clearly synthetic data. Never retain browser autofill, real customer information,
passwords or OTP values in screenshots or exports. Do not submit production forms
or create accounts solely for a marketing capture.

These are promotional explainers, not final application E2E acceptance evidence.
Do not present illustrative verification graphics as recordings of a completed
registration. Legal output claims require human review; avoid guarantees of outcomes.
The guide includes no legal advice or personal-data processing change. No consent,
retention or human-oversight safeguards in the product are altered.

Keep approved marketing masters in Git for reuse. Delete rejected draft assets via
normal review; transient render/contact-sheet evidence in ignored `runs/` can be
deleted after review, within 30 days. Check rights for any new presenter, voice,
music or third-party asset before reuse; current footage and references were supplied
by the owner for this task. Check YouTube disclosure settings when uploading content
with a realistic synthetic presenter. Upload is always the owner's action.

## Logo generation record

Tool: built-in imagegen, edit target `corporate-web/assets/login-shield.png`.
Final prompt:

> Create a faithful high resolution cleaned version of this exact existing logo on
> a perfectly solid pure BLACK #000000 background for a black video end card. No
> checkerboard. No transparency needed. Maintain exact same original face and
> circuitry paths, original scales, original silver central column and blue shield.
> Do not redesign. Precisely smooth outer contours. No detached white pixels, white
> halo or speckles outside the shield. Square image shield centered, 12% pure black
> margin around all edges. No text. Output 2048px if available.

Both generated versions are retained at the owner's request, each 1254 × 1254.
The first version requested transparent edges but returned an opaque checkerboard;
it is saved as `assets/logo-checkerboard-hires.png`. The final black-background
version is `assets/logo-black-hires.png` and is the version used by the renderer.
