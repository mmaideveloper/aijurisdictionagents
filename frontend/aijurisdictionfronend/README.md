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

## API Chat Integration (Task #238)

The signed-in workspace now uses the live API for case communication in all three modes (`Chat`, `Voice`, `Video`).
Voice and video are simulated by sending transcript payloads through the same chat reply endpoint.

Frontend environment variables:

- `VITE_API_BASE_URL` (default: `https://api-juris-dev.victoriousdesert-e45eec11.westeurope.azurecontainerapps.io`)
- `VITE_API_KEY` (default: `aijuris`)
- `VITE_API_COUNTRY` (default: `SK`)
- `VITE_API_LANGUAGE` (default: `en`)
- `VITE_AIJ_SPEECHTYPE` (default: `message`; use `conversation` for the existing Voice-agent transcript flow)

Speech input:

- `message` mode shows audio and microphone controls in the normal chat composer. Browser-native STT fills the visible text input first, and the reviewed text is sent through the normal chat API path.
- `conversation` mode keeps the existing Voice-agent transcript screen available for speech-first sessions.
- The browser path does not upload raw audio to the API. If browser STT is unavailable, the UI falls back to typed input. A future remote STT fallback must require explicit consent before raw audio upload.

Flow used by the workspace:

1. `POST /v1/chat/sessions` once per case.
2. `POST /v1/chat/sessions/{session_id}/reply` for each outgoing user message.
3. The API response is appended back to the active case timeline.

Console logging:

- Frontend emits process logs to browser console with `INFO`, `WARN`, and `ERROR` levels.
- API request lifecycle and failures are logged with structured JSON context.

## JurisDigta Account Login

The web app signs users in through the same API user table used by the mobile app and MCP account flows.

- Login submits `email` and `password` to `POST /v1/users/sign-in`.
- The request uses `VITE_API_BASE_URL` and `VITE_API_KEY`, matching the existing frontend API client configuration.
- The returned user profile is cached in browser `sessionStorage` for the current browser session.
- Passwords are never stored by the frontend.

## Signed-in Homepage

When authenticated, the home page switches to a 3-column workspace layout (case sidebar, active workspace, AI configuration). On smaller screens the side panels collapse for a single-column layout.

## Protected App Routes

All `/app/*` routes and `/profile` are guarded by API-backed web auth state.

- Unauthenticated users are redirected to `/`
- Authenticated users can access the full app area (`/app`, `/app/workspace`, etc.) and `/profile`
- Logging out from the profile dropdown immediately removes access to protected routes

## JurisDigta Assistant Workspace (Issue #356)

The first assistant-ui integration slice adds an authenticated route:

`/app/assistant`

Implementation notes:

- Uses `@assistant-ui/react` `0.14.23` with a local runtime adapter shape that can be replaced by the future Assistant Gateway.
- Keeps JurisDigta API/MCP as a locked mandatory capability in the UI.
- Shows Slovakia-first V1 modes for legal search, document preparation, person/company screening, car validation, and location validation.
- Does not execute arbitrary third-party MCP calls from the browser.
- Marks sensitive verification/screening flows as explicit-approval and consent/legal-basis gated before execution.
- Shows transparency metadata: AI-assisted draft, legal-review-required risk level, and required human oversight.
- All user-facing assistant strings are translated for `en`, `sk`, and `de`.

Production deployment preparation:

- The route is served by the existing `jurisdigta-web` container on local port `8090`.
- Publish `agent.jurisdigta.eu` through Cloudflare Tunnel to `http://127.0.0.1:8090`.
- Current production uses the JurisDigta account login at `/auth`; do not configure Cloudflare Access for `agent.jurisdigta.eu` unless the auth plan changes.
- Login credentials are verified by the API against the PostgreSQL-backed users table.
- Validate `https://agent.jurisdigta.eu/health` and `https://agent.jurisdigta.eu/app/assistant` after DNS/tunnel setup.

## Navbar Branding

The signed-out navigation includes the same app logo treatment used in the signed-in sidebar (`AJ` mark + app name/tagline).

- The logo is rendered on the left side of the navbar for signed-out views.
- The logo is also rendered for signed-in views on non-home routes (for example `/app` and `/profile`).
- On signed-in homepage (`/`), the navbar logo is shown when the workspace sidebar is collapsed.
- The logo links to `/` (marketing homepage).
- The navbar layout is responsive so brand, links, and actions do not overlap at mobile widths.

## Signed-in Profile Dropdown

In signed-in state, the profile icon opens a click-triggered dropdown menu in the navbar.

- Options: `My Profile`, `My Cases`, `Log Out`
- `My Profile` navigates to `/profile`
- `My Cases` currently navigates to `/` (homepage workspace)
- Menu closes on outside click, on option click, and on `Escape`
- Keyboard navigation is supported with `ArrowUp`, `ArrowDown`, `Home`, and `End`
- Mobile layout keeps the dropdown anchored under the trigger with viewport-safe width

## My Profile View

The `/profile` page displays structured user information from the current API-authenticated web session.

- First Name
- Last Name
- Email
- Role (currently optional)
- Account Created Date (currently optional)
- Includes subscription pricing controls (billing cadence + plan selector)
- Includes an opened-cases panel with quick navigation back to active matters

## Mock Case Creation Flow (Task #242)

Task `#242` is implemented as a frontend-only mock flow. It does not create or upload cases/documents through the API.

- `+ New case` opens the intake form at `/app/case`
- The intake form requires:
  - case name
  - jurisdiction
  - opposing party
- Uploading documents is optional
- Submitting the form creates a mock case in frontend storage and returns the user to `/`
- The new case appears in:
  - the signed-in homepage sidebar
  - `My Profile` under `Opened cases`
- Uploaded documents appear in `My Profile` under `My Documents`
- Mock cases/documents are stored in browser `localStorage` for local development and tests

## Language Switching (Task #243)

Task `#243` keeps the selected UI language active across routes and applies it to the current page immediately.

- The language switcher selection is stored in browser `localStorage`
- Public routes and signed-in routes reuse the same selected language
- Signed-in workspace labels and sidebar copy update immediately when the user changes language
- App-owned mock case/workspace text is re-localized for `en`, `sk`, and `de`
- User-provided content such as case titles and uploaded filenames stays unchanged
- New chat sessions pass the selected frontend language to the API session creation call

## Chat Window Visuals (Task #245)

Task `#245` refines the signed-in workspace chat presentation.

- The seeded assistant intro message is removed after the user sends the first chat message
- The chat timeline keeps system notices and live API replies intact
- The bottom `Next recommended action` card is removed from the workspace chat view

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

## Self-managed server container

The production container serves the Vite build through nginx with SPA route
fallbacks for `BrowserRouter` routes.

```bash
cd frontend/aijurisdictionfronend
docker build \
  --build-arg VITE_API_BASE_URL=https://api.jurisdigta.eu \
  -t jurisdigta-web:local .
docker run -d \
  --name jurisdigta-web \
  --restart unless-stopped \
  -p 127.0.0.1:8090:80 \
  jurisdigta-web:local
curl -fsS http://127.0.0.1:8090/health
```

## Minimal Runnable Example (Project Default)

```bash
python examples/minimal_demo.py
```

Task-specific frontend check:

```bash
python examples/frontend_navbar_task_211_minimal_demo.py
```

Task #238 API chat minimal demo:

```bash
python examples/frontend_api_chat_minimal_demo.py
```

Task #242 mock case creation minimal demo:

```bash
python examples/frontend_case_creation_task_242_minimal_demo.py
```

Task #243 language switching minimal demo:

```bash
python examples/frontend_language_switching_task_243_minimal_demo.py
```

Task #245 chat window visuals minimal demo:

```bash
python examples/frontend_chat_window_visuals_task_245_minimal_demo.py
```

Issue #356 assistant workspace minimal demo:

```bash
python examples/frontend_assistant_task_356_minimal_demo.py
```

The demo defaults to the shared Azure dev API endpoint. Override it for local API testing with
`AIJ_API_BASE_URL=http://127.0.0.1:8080`.
