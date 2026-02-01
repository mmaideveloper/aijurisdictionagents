# AI Jurisdiction Frontend (Demo)

Basic React + TypeScript scaffold for the AI Jurisdiction frontend.

## Quick start

Requires Node.js 18+.

Copy the Azure Speech settings for the avatar demo:

```bash
cp .env.example .env
```

```bash
cd frontend/aijurisdictionfronend
npm install
npm run dev
```

Then open `http://localhost:5173`.

## Avatar lipsync demo

The demo uses Azure Speech (text-to-speech + viseme events) to drive a lightweight SVG avatar.
Set the following in `.env`:

- `VITE_AZURE_SPEECH_KEY`
- `VITE_AZURE_SPEECH_REGION`
- `VITE_AZURE_SPEECH_VOICE` (optional, defaults to `en-US-JennyNeural`)

## Build

```bash
npm run build
npm run preview
```
