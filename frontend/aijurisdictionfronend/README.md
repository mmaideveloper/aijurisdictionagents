# Jurisdigta AI Frontend

React + TypeScript + Vite frontend workspace for Jurisdigta AI. This UI is aligned with the
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

## Minimal Runnable Branding Example

Run the frontend with the setup commands above, sign in, and open
`http://localhost:5173/app/assistant`. The sidebar/header brand and browser-tab title both read
`Jurisdigta AI právnik` (SK), `Jurisdigta AI lawyer` (EN), or `Jurisdigta AI Anwalt` (DE), according
to the selected language. Change languages and navigate away and back to `/app/assistant` to verify
that both titles update immediately and retain the persisted language.

## E2E Regression Tests

Run the browser regression suite with:

```bash
npm run test:e2e
```

The suite starts Vite locally and uses mocked JurisDigta API responses. Deployment workflows run this Playwright gate before deployment so a failed document-preview, document-download, or document-listing regression blocks release. If the default Playwright port is already in use, set `FRONTEND_E2E_PORT`, for example `FRONTEND_E2E_PORT=5190 npm run test:e2e`. Issue #503 is covered by `e2e/assistant-live-document-preview.spec.ts`, which verifies the live assistant response path and the post-refresh case-history path both show the formatted JurisDigta document preview, generated PDF action, and citation source. Issue #530 is covered by `e2e/assistant-branding.spec.ts`, which verifies the localized SK/EN/DE sidebar brand and browser title after persisted direct loads, live language changes, and client-side navigation.

The issue #530 test writes locale screenshots to
`runs/e2e/issue-530-assistant-branding-{sk,en,de}.png` using synthetic account and API data.

### Slovak

![Issue #530 Slovak assistant branding E2E result](docs/issue-530-assistant-branding-sk.png)

### English

![Issue #530 English assistant branding E2E result](docs/issue-530-assistant-branding-en.png)

### German

![Issue #530 German assistant branding E2E result](docs/issue-530-assistant-branding-de.png)

## API Chat Integration (Task #238)

The signed-in workspace now uses the live API for case communication in all three modes (`Chat`, `Voice`, `Video`).
Voice and video are simulated by sending transcript payloads through the same chat reply endpoint.

Frontend environment variables:

- `VITE_API_BASE_URL` (default: `https://api-juris-dev.victoriousdesert-e45eec11.westeurope.azurecontainerapps.io`)
- `VITE_API_KEY` (default: `aijuris`)
- `VITE_API_COUNTRY` (default: `SK`)
- `VITE_API_LANGUAGE` (default: `en`)
- `VITE_CHAT_MODEL_LABEL` (default: `Azure Foundry model`; public label shown in the assistant chat header)
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
- New users start from the `Sign up` action on `/auth`. Registration fields stay hidden until the user chooses that action.
- Registration first collects only the required account details: phone number, email, and password.
- Email OTP verification remains a second step after those details are entered. The frontend calls `POST /v1/users/sign-up/send-code`, then completes the account with `POST /v1/users/sign-up/complete`.
- The request uses `VITE_API_BASE_URL` and `VITE_API_KEY`, matching the existing frontend API client configuration.
- The returned user profile is cached in browser `sessionStorage` for the current browser session.
- Passwords are never stored by the frontend.

## Signed-in Homepage

When authenticated, the home page switches to a 3-column workspace layout (case sidebar, active workspace, AI configuration). On smaller screens the side panels collapse for a single-column layout.

## Protected App Routes

All `/app/*` routes and `/profile` are guarded by API-backed web auth state.

- Unauthenticated users are redirected to `/`
- Authenticated users can access the full app area (`/app`, `/app/workspace`, etc.) and `/profile`
- `/app/chat` is kept as a protected compatibility alias that redirects to `/app/assistant`
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
- Shows the public AI model/runtime label used for the chat. Do not put API keys, URLs, connection strings, or secret deployment values into `VITE_CHAT_MODEL_LABEL`; it is compiled into the browser bundle.
- All user-facing assistant strings are translated for `en`, `sk`, and `de`.

Production deployment preparation:

- The route is served by the existing `jurisdigta-web` container on local port `8090`.
- Publish `agent.jurisdigta.eu` through Cloudflare Tunnel to `http://127.0.0.1:8090`.
- Current production uses the JurisDigta account login at `/auth`; do not configure Cloudflare Access for `agent.jurisdigta.eu` unless the auth plan changes.
- Login credentials are verified by the API against the PostgreSQL-backed users table.
- Validate `https://agent.jurisdigta.eu/health` and `https://agent.jurisdigta.eu/app/assistant` after DNS/tunnel setup.

## Assistant Gateway Case Answer Flow

The protected `/app/assistant` route includes a gateway-backed intake panel where a
signed-in user can create a new case target or use an existing case ID, attach documents,
send a question, and render the returned answer.

Default endpoint:

```text
POST /api/assistant/cases/answer
```

Override it with:

```bash
VITE_ASSISTANT_GATEWAY_URL=https://api.example.test/api/assistant/cases/answer npm run dev
```

The request is multipart form data with `question`, `case_mode`, `case_id`, `country`,
`language`, `consents`, and zero or more `documents` file fields. The browser never calls
MCP tools directly; Assistant Gateway must perform auth, case access checks, consent/policy
validation, document persistence, tool execution, and answer logging.

If the gateway is not reachable, the UI shows a deterministic local fallback answer so the
question/upload/answer rendering path can be tested during frontend development.

## Navbar Branding

The signed-out navigation includes the same app logo treatment used in the signed-in sidebar (`AJ` mark + localized Jurisdigta AI name/tagline). The browser title uses the same localized product name on direct loads, language changes, and client-side navigation.

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
- Submitting the form creates a mock case in frontend storage and opens `/app/assistant`
- The new case appears in:
  - the signed-in homepage sidebar
  - `My Profile` under `Opened cases`
- Uploaded documents appear in `My Profile` under `My Documents`
- Mock cases/documents are stored in browser `localStorage` for local development and tests

## Case Creation Assistant Layout (Issue #369)

Creating a case now opens the canonical assistant workspace at `/app/assistant`.
The legacy `/app/chat` path remains available as a protected redirect to the same assistant
workspace so older links do not render mixed workspace styles.

The frontend layout regression is covered by:

```bash
cd api/aijuristiction-api/e2e-playwright
API_BASE_URL=http://127.0.0.1:8080 FRONTEND_BASE_URL=http://127.0.0.1:5173 npx playwright test tests/frontend-case-create-layout.spec.ts
```

The test creates a case through the UI, captures screenshot artifacts, and checks that the
assistant rail, center conversation area, and right tool panel do not overlap or create
horizontal page overflow at desktop viewports.

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
  --build-arg "VITE_CHAT_MODEL_LABEL=Azure Foundry model" \
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

Issue #398 assistant model disclosure minimal demo:

```bash
python examples/frontend_assistant_model_disclosure_issue_398_minimal_demo.py
```

Issue #401 document preview formatting minimal demo:

```bash
python examples/frontend_document_preview_issue_401_minimal_demo.py
```

Issue #401 browser regression check:

```bash
cd api/aijuristiction-api/e2e-playwright
FRONTEND_BASE_URL=http://127.0.0.1:5173 npx playwright test tests/frontend-document-preview-formatting.spec.ts
```

Issue #503 live document preview minimal demo:

```bash
python examples/frontend_live_document_preview_issue_503_minimal_demo.py
```

Issue #503 browser regression check:

```bash
cd frontend/aijurisdictionfronend
npm run test:e2e -- e2e/assistant-live-document-preview.spec.ts
```

Issue #369 case-create layout minimal demo:

```bash
python examples/frontend_case_create_layout_issue_369_minimal_demo.py
```

The demo defaults to the shared Azure dev API endpoint. Override it for local API testing with
`AIJ_API_BASE_URL=http://127.0.0.1:8080`.
