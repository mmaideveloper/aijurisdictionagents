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

## Protected App Routes

All `/app/*` routes are guarded by mock auth state.

- Unauthenticated users are redirected to `/`
- Authenticated users can access the full app area (`/app`, `/app/profile`, `/app/workspace`, etc.)
- Logging out from the profile dropdown immediately removes access to protected routes

## Navbar Branding

The signed-out navigation includes the same app logo treatment used in the signed-in sidebar (`AJ` mark + app name/tagline).

- The logo is rendered on the left side of the navbar only when the user is not signed in.
- The logo links to `/` (marketing homepage).
- The navbar layout is responsive so brand, links, and actions do not overlap at mobile widths.

## Signed-in Profile Dropdown

In signed-in state, the profile icon opens a click-triggered dropdown menu in the navbar.

- Options: `My Profile`, `My Cases`, `Log Out`
- Menu closes on outside click, on option click, and on `Escape`
- Keyboard navigation is supported with `ArrowUp`, `ArrowDown`, `Home`, and `End`
- Mobile layout keeps the dropdown anchored under the trigger with viewport-safe width

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
