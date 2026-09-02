---
name: youtube-shorts-upload
description: Prepare, validate, upload, and publish a video through YouTube Studio as a Short. Use when a developer asks to upload a local video or an HTTPS-hosted video to YouTube Shorts, especially for JurisDigta marketing content. Do not use for video generation, editing, paid promotion campaigns, or YouTube API credential setup.
---

# YouTube Shorts Upload

Create a reviewable private YouTube draft first. Treat channel creation and public publication as separate external actions that require immediate user confirmation.

## Prepare the source

1. Accept one exact local path or HTTPS URL selected by the user. Do not search folders, browsing history, cloud drives, or account storage for a likely video.
2. For an HTTPS URL or when a stable staging copy is useful, run from the repository root:

   ```powershell
   .\skills\youtube-shorts-upload\scripts\prepare_youtube_short.ps1 -VideoUrl "https://example.test/video.mp4"
   ```

   For a local source:

   ```powershell
   .\skills\youtube-shorts-upload\scripts\prepare_youtube_short.ps1 -VideoPath "C:\absolute\path\video.mp4"
   ```

3. Use the returned absolute `StagedPath`. The helper writes only below ignored `runs/youtube-shorts-upload/`, never overwrites a different file, and reports SHA-256 plus media metadata when `ffprobe` is available.
4. Require a square or vertical video no longer than 180 seconds. When local probing is unavailable, verify that YouTube produces a `/shorts/` link after upload; otherwise stop and explain that the file was not recognized as a Short.
5. Do not delete the staged file without explicit approval. Report its location and recommend deletion after the user has verified the published video.

## Compliance gate

Before uploading, check the source and intended metadata:

- Use only media, music, logos, people, and text that the user is authorized to publish. Stop on an unresolved copyright, trademark, consent, or privacy concern.
- Never upload real customer cases, legal documents, account data, credentials, or other personal data merely to create marketing content. Prefer synthetic people, documents, and interfaces.
- For JurisDigta legal marketing, preserve the approved limitations in `docs/marketing/JURISDIGTA_CONSUMER_VIDEO_PROMPT_SK.md`: do not promise legal representation, guaranteed outcomes, or an unverified free offer. Require human review of legal claims, branding, spelling, music licensing, and the visible legal disclaimer.
- In YouTube's **AI use** field, select **Yes** whenever realistic visuals or sounds were generated or materially altered with AI. Do not infer that synthetic-looking media is real footage.
- Mark paid promotion only when the user confirms that the video includes compensated placement, sponsorship, endorsement, or another applicable commercial relationship.
- Set **Made for kids** from the actual target audience. Do not use that setting as a general safety label.

## Upload in YouTube Studio

1. Use the available browser-control skill and its file-upload procedure. Reuse the user's signed-in browser session; never inspect cookies, stored passwords, tokens, or session files.
2. Open `https://studio.youtube.com/` and verify the visible channel name or account selected by the user.
3. If YouTube requires a new channel, show the proposed channel name and handle. Ask for confirmation immediately before clicking **Create channel**.
4. Choose **Upload videos**, select the staged file through the file chooser, and wait until upload and SD processing complete.
5. Confirm that YouTube exposes a `/shorts/` video link. Record the duration and link.
6. Fill the title and description supplied by the user. If absent, propose concise metadata based only on the approved source; avoid new legal or commercial claims. The user must see the final title and visibility before publication.
7. Set audience, AI use, paid promotion, and any requested language or category. Leave unrelated advanced settings unchanged.
8. Continue through **Video elements** and **Checks**. Stop and report any copyright or policy issue instead of publishing through it.

## Publish safely

1. Keep visibility **Private** while preparing and reviewing the upload.
2. At **Visibility**, summarize the exact title, channel, audience, AI disclosure, copyright-check result, intended visibility, and Short URL.
3. Ask for an immediate explicit confirmation before selecting **Public** or **Unlisted** and activating **Publish**. A prior request to prepare or upload the video is not final publication approval.
4. After confirmation, accept only warnings that directly describe the already-approved publication, click **Publish**, and verify YouTube's **Video published** confirmation.
5. Return the public link and the final settings. If interrupted or blocked, preserve the private draft when possible and report the exact remaining step.

## Stop conditions

Stop without publishing when the target account is uncertain, authentication requires a password/OTP/CAPTCHA handoff, the file is not recognized as a Short, rights or consent are unclear, a required disclosure cannot be answered, YouTube reports a policy/copyright issue, or the user has not confirmed final visibility.
