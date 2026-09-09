# Registrácia do JurisDigta — Slovak Short

Status: review draft, not uploaded. Created manually on 2026-09-09.

## Current version

The 15-second MP4 now speaks the actual registration instructions in a similar
Slovak female voice, selected after the owner authorized a different voice.
Voice: Microsoft `sk-SK-ViktoriaNeural`, rate +8%, default pitch and volume,
generated through edge-tts 7.2.8. The recording is `narration-viktoria.mp3`;
its exact input is `narration.sk.txt`. This is a standard synthetic voice, not a
clone of the original voice and not a claim that the original preset was identified.

The first scene uses `presenter-lipsync.mp4`, generated from the existing presenter
and the new audio with MuseTalk 1.5. The remaining instructions continue as voiceover
on the registration form and an illustrative email graphic. No unsynchronized
speaking presenter is shown during those scenes. No unrelated old speech is mixed in.

## Storyboard

| Time | Scene and narration |
| --- | --- |
| 0–3.67 s | Lip-synced presenter: Otvorte aplikáciu a kliknite na Registrácia. |
| 3.67–6.80 s | Actual empty form: Vyplňte telefón, e-mail a heslo. |
| 6.80–10.68 s | Email illustration: Zadajte kód z e-mailu a kliknite na Vytvoriť účet. |
| 10.68–15 s | Clean logo and website; spoken JurisDigta, then a quiet end-card hold. |

Both SRT files reflect the new speech. The first generated sentence boundary
slightly overlapped the second; it was clamped to the second sentence's start.
The visible text in `titles.ass` follows the speech timestamps, rounded to video frames.

## Rebuild

From the repository root, supply an installed FFmpeg executable:

```powershell
.\marketing\youtube-shorts\2026-09-09-registracia\render.ps1 -FfmpegPath C:\Tools\ffmpeg.exe
```

The saved media make the final render local and repeatable without credentials,
Python or remote generation. The script uses Arial, Segoe UI Symbol, libass and
libx264. It exports H.264/yuv420p at 1080 × 1920, 30 fps, with AAC 48 kHz audio,
checks full decoding and generates `poster.png`.

To regenerate the voice, install edge-tts in an isolated environment and run from
this episode directory:

```powershell
python -m edge_tts --voice sk-SK-ViktoriaNeural --rate=+8% --file narration.sk.txt --write-media narration-viktoria.mp3 --write-subtitles speech.sk.srt
```

Voice synthesis requires the Microsoft Edge online speech service. If regenerated
timing changes, regenerate lip sync and align the scene/SRT timing before export.
Docs: https://github.com/rany2/edge-tts.

## Lip-sync provenance

Tool: MuseTalk 1.5, through the community-hosted demo
https://huggingface.co/spaces/henrybit/musetalk-1-5.
Project and usage/license information: https://github.com/TMElyralab/MuseTalk.
The project states that its code and model permit commercial use; dependencies
remain governed by their respective licenses. No third-party demo/test footage was used.

Source: `corporate-web/assets/jurisdigta-sk.mp4`, SHA-256
`4960A87ADC4244479A9BD3333A66E831D6DAA8243FFB1DEE7CA49E6E41A336AD`.
It matched the owner's linked https://www.jurisdigta.eu/assets/jurisdigta-sk.mp4.
The input video was cropped to 650 × 1080 at x=600, y=0, with original audio removed.
Two 2-second clips (0–2 and 2–4 seconds) were driven by the corresponding new audio
segments, yielding 50 frames each at 25 fps. Parameters: bbox_shift=0,
extra_margin=10, parsing_mode=jaw, left_cheek_width=90, right_cheek_width=90.
The outputs were concatenated into the 4-second saved presenter master; the final
video displays only its first 3.67 seconds.

A full-length request exceeded the hosted service's per-job limit. After the two
successful short clips, further generation exceeded the remaining free quota.
The final edit therefore shows the presenter only in the successfully synchronized
opening scene. Additional instructions use narrated graphics. No paid service or
credits were purchased. Full on-camera narration would need more lip-sync capacity.

Only owner-provided public presenter excerpts and synthetic narration were sent
to that service; no account data, passwords or OTPs were uploaded. Remote cache
retention is controlled by the hosting service; local cleanup does not delete it.

## Verification

- Full final MP4 decoding passed; 15.00 seconds, 450 frames, 1080 × 1920.
- Actual audio samples: mean -17.5 dBFS, peak -1.5 dBFS, no clipping detected.
- Final scene contact sheet and opening face-frame sequence visually inspected.
  Opening mouth shapes vary with the generated animation; face/framing remain usable.
- Independent local faster-whisper base transcription recovered the application,
  registration, phone/email/password, email-code and account-creation instructions.
  It made Slovak spelling errors and rendered the brand as “Juris dicta”; this is
  supporting content evidence, not an exact transcript or pronunciation guarantee.
- Subtitle content/timing checked against the synthesis metadata. Human listening
  review of pronunciation and perceptual lip sync remains with the owner.
- `verification.json` records hashes and technical results. Temporary evidence is
  under ignored `runs/`; remove it within 30 days after review. Saved marketing
  masters and sources are tracked for reuse.

This is media verification, not application E2E acceptance. No production account
was created and no verification email was sent. The real blank Slovak form was
inspected at https://agent.jurisdigta.eu/auth after autofill was cleared. The email
scene is explicitly illustrative; its dots are not an OTP value.
Product sources: `frontend/aijurisdictionfronend/src/pages/Auth.tsx` registration
handlers/form and `src/data/translations.ts` within that frontend (`authRegister`).

## Upload copy

Title: **Ako sa zaregistrovať do JurisDigta? #Shorts**

Registrácia do JurisDigta krok za krokom: otvorte registráciu, vyplňte telefónne
číslo, e-mail a heslo, overte e-mail a vytvorte si účet.

Registrácia: https://agent.jurisdigta.eu/auth
Viac informácií: https://www.jurisdigta.eu

Ilustračná AI sprievodkyňa a syntetický hlas; skrátená ukážka postupu.
#JurisDigta #Registrácia #Shorts
