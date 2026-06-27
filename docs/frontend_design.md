# Frontend Design - AIJurisdiction

This document describes the proposed frontend design located in `frontend_design`.

## Page Map
- `/` Public homepage with capability overview and CTA
- `/pricing` Subscription pricing for Free, Basic, Pro, Ultra
- `/auth` Sign-in / create account templates
- `/app` Authenticated dashboard landing
- `/app/case` Case creation and document intake
- `/app/workspace` Lawyer preparation. The web role selector currently keeps
  `AI Lawyer` active and shows `AI Judge` plus `Opposing Counsel` as disabled
  options until those legal-risk perspectives have separate product and
  compliance approval.
- `/app/advice` Multi-agent printable advice summary
- `/app/communications` Chat, voice, video modes. Browser voice capture uses
  browser-native speech recognition when available, keeps a reviewable
  transcript draft, asks after 10 seconds of silence whether to answer, submits
  on `yes`, and preserves the draft on `no` so the user can continue.
- `/app/law-validation` New law validation
- `/app/law-recommendation` Law recommendation
- `/app/profile` Profile and subscription management

## Multilingual Support
UI strings are available in English, Slovak, and German via a simple translation dictionary and language switcher.

## Corporate Web Update
The corporate site includes a pricing section for the four subscription tiers.

## Local Dev Hygiene
`frontend_design` build outputs and `node_modules` are excluded from git via `.gitignore`.

## Minimal Runnable Example (Project Default)
```bash
python examples/minimal_demo.py
```
