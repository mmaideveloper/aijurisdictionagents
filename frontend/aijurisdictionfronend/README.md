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

## Simulated Login (Frontend-only)

The UI includes an in-memory auth state used for local development. It resets on refresh.

- Email: `admin@admin.com`
- Password: `admin123`

## Signed-in Homepage

When authenticated, the home page switches to a 3-column workspace layout (case sidebar, active workspace, AI configuration). On smaller screens the side panels collapse for a single-column layout.
The right panel now includes a collapsible **Legal tools** section (shown only for an active selected case) with placeholder actions:
- Summarize Case
- Risk Analysis
- Generate Argument
- Explain Legal Terms

Each tool click appends an AI-generated placeholder entry to the active case interaction history.

## Legal pages and footer links

Global footer links are available in all language modes (`en`, `sk`, `de`) and are visible on both public and signed-in screens.

- `/privacy`
- `/disclaimer`
- `/terms`

The disclaimer page includes AI disclosure, no-legal-advice notice, no attorney-client relationship, limitation of liability, no warranty, jurisdiction scope, user responsibility, external resources clause, right-to-modify clause, and a `Last Updated` timestamp.

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
