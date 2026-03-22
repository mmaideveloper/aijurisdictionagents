# Corporate Web

Static single-page site for AI Jurisdiction.

## Local debugging

From repo root:

```bash
cd corporate-web
python -m http.server 8000
```

Open `http://localhost:8000` in a browser.

If port 8000 is busy:

```bash
python -m http.server 8001
```

## Language switch

The page ships with Slovak (default), German, and English translations. Use the `SK/DE/EN` toggle in the header.
The selection is stored in `localStorage` (`aj_lang`).

## Pricing sync

The pricing cards and FAQ mirror the backend subscription limits for document uploads per case:

- `Free`: 2 documents per case
- `Case`: 5 documents per case
- `Basic`: 5 documents per case
- `Premium`: 50 documents per case

## Branding assets

The site now uses `assets/branding.png` as the source sheet for:

- `assets/brand-lockup.png` (logo + wordmark)
- `assets/brand-banner.png` (hero/visual banner)
- `assets/icon-ai.png`
- `assets/icon-scale.png`
- `assets/icon-doc.png`
- `assets/icon-court.png`
- `assets/login-shield.png` (transparent login/header icon)

## Legal links

Footer now includes multilingual links for:

- Privacy Policy
- Disclaimer
- Terms of Service

Footer meta also shows:

- API version (`aijuristiction-api`)
- System core version (`aijurisdictionagents`)

The page also includes a legal section with a structured disclaimer and `Last Updated` timestamp.

## Video demo

The homepage switches the Jurisdigta avatar video per language:

- `assets/jurisdigta-sk.mp4` (SK)
- `assets/jurisdigta-ge.mp4` (DE)
- `assets/jurisdigta-en.mp4` (EN)

The video container constrains height to prevent oversized display on large screens.

## Minimal runnable example

Repo default: `python examples/minimal_demo.py`
Corporate web preview: `python -m http.server 8000` from `corporate-web`.
