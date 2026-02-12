# Frontend Demo App

Location: `frontend/aijurisdictionfronend`

This is a basic React + TypeScript app scaffolded with Vite. It is intended as the starting
point for the AI Jurisdiction client workspace (intake, uploads, and live agent stream).

## Quick start

Requires Node.js 18+.

```bash
cd frontend/aijurisdictionfronend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Simulated login (frontend-only)

The demo includes an in-memory auth state for UI development. It resets on refresh.

- Email: `admin@admin.com`
- Password: `admin123`

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
- Navbar reacts to mock auth state: sign-in link when logged out, profile menu with name + email when logged in

## Signed-in homepage

When authenticated, the home page swaps to a 3-column workspace layout: case sidebar, active workspace, and AI configuration panel. On narrow screens the side panels collapse and the center workspace takes full width.

Case sidebar behavior:
- `+ New case` creates a mock case and makes it active.
- Clicking a case loads its data into the center workspace and AI configuration panel.
- The case list scrolls independently within the full-height sidebar.
- The sidebar is now componentized and uses a branded header plus section grouping.
- Each case row stays the same background as the sidebar with a status-colored dot.
- The workspace view is full-height with internal scrolling, so the page itself does not scroll.
- On the authenticated home view, the layout is a full-height flex row: sidebar on the left, navbar + content on the right.
- The center workspace starts with a welcome state prompting the user to start a new case or continue by selecting a case in the sidebar.

## Case state model

The frontend now includes a session-scoped case store exposed via a context provider.
Each case includes:
- `id`, `title`, `description`, `status`, `createdAt`
- `interactionHistory` entries with timestamps, actors, and messages
- `selectedRole` and `selectedMode` stored per case

The active case is available globally via the `CaseProvider` context.
