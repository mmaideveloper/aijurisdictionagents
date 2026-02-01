# Frontend Demo App

Location: `frontend/aijurisdictionfronend`

This is a basic React + TypeScript app scaffolded with Vite. It is intended as the starting
point for the AI Jurisdiction client workspace (intake, uploads, and live agent stream).
It now includes a proof-of-concept avatar lipsync view driven by Azure Speech visemes.

## Quick start

Requires Node.js 18+.

Copy the Azure Speech settings for the avatar demo:

```bash
cp frontend/aijurisdictionfronend/.env.example frontend/aijurisdictionfronend/.env
```

```bash
cd frontend/aijurisdictionfronend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Minimal runnable example

From repo root (PowerShell):

```powershell
.\examples\frontend_demo.ps1
```

## Build

```bash
npm run build
npm run preview
```

## Layout notes

- Hero header with session status and region
- Feature cards for intake, orchestration, and outputs
- Callout panel for upcoming API integration
- Avatar lipsync demo with SVG mouth shapes driven by Azure Speech visemes

## Azure Speech settings

Set the following environment variables in `frontend/aijurisdictionfronend/.env`:

- `VITE_AZURE_SPEECH_KEY`
- `VITE_AZURE_SPEECH_REGION`
- `VITE_AZURE_SPEECH_VOICE` (optional)
