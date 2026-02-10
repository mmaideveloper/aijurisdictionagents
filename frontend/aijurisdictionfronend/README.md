# AI Jurisdiction Frontend

React + TypeScript + Vite frontend workspace for AI Jurisdiction. This UI is aligned with the
`frontend_design` proposal and includes the public marketing pages plus authenticated workflow
screens.

## Runtime

- Node.js 18+
- npm 9+

## Setup

```bash
cd frontend/aijurisdictionfronend
npm install
cp .env.example .env
npm run dev
```

Open `http://localhost:5173`.

## Callback Contract

The frontend expects auth callback requests to hit:

`/auth/callback`

Required query parameters:

- `provider` (`google` or `x`)
- `id` (string user id)
- `name` (string display name)

Optional query parameters:

- `avatarUrl`

Example callback URL:

`http://localhost:5173/auth/callback?provider=google&id=123&name=Jane%20Doe`

On success, the app stores the session in `localStorage` and redirects to `/`.
On invalid payloads, the callback page shows an explicit error state.

## Lint & Test

```bash
npm run lint
npm run test
```

## Build

```bash
npm run build
npm run preview
```

## Minimal Runnable Example (Project Default)

```bash
python examples/minimal_demo.py
```
