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
- The case list scrolls independently while the sidebar stays sticky during page scroll.
