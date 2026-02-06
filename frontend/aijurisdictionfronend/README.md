# AI Jurisdiction Frontend

React + TypeScript + Vite frontend workspace for AI Jurisdiction.

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

## Auth Configuration

Configure OAuth start URLs in `.env`:

```bash
VITE_AUTH_GOOGLE_START_URL=https://your-auth-service.example.com/oauth/google/start
VITE_AUTH_X_START_URL=https://your-auth-service.example.com/oauth/x/start
```

If these values are missing, the login buttons remain disabled and the UI shows a configuration hint.

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

## Build

```bash
npm run build
npm run preview
```
