# Frontend Design Proposal

This folder contains a React + TypeScript design proposal for the AIJurisdiction frontend, including public marketing pages and authenticated workflow screens.

## Goals
- Public homepage with system overview
- Authenticated workspaces for case creation, multi-agent debate, advice summary, and law operations
- Subscription management and pricing views
- Multilingual UI (English, Slovak, German)

## Run Locally
```bash
cd frontend_design
npm install
npm run dev
```

## Lint & Test
```bash
npm run lint
npm run test
```

## Minimal Runnable Example (Project Default)
```bash
python examples/minimal_demo.py
```

## Structure
- `src/pages`: Individual page layouts
- `src/components`: Navigation, footer, language switcher
- `src/data`: Translation and pricing data
- `src/styles`: Theme and layout styles
