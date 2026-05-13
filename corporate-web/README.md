# Corporate Web

Static single-page site for AI Jurisdigta.

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

## News and articles

The homepage includes a static articles section at `#articles`. Article detail views are hash-routed
inside the same static page, for example:

- `#article-mcp-ai-assistants`
- `#article-slovak-service-integrations`
- `#article-security-gdpr-ai-act`

Maintain article metadata and Slovak article bodies in the `articles` array inside `index.html`.
The right-side context menu is rendered from the same data on the overview and detail views, so new
articles only need one data entry. The first article-body version is Slovak-only by design; DE/EN
visitors see a translated UI note until reviewed translations are added.

Article content must not add third-party trackers, remote embeds, or claims of live MCP production
availability before the backend endpoint is actually shipped.

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

The deployment workflow replaces these footer values from the latest repository sources during deploy:

- API: `api/aijuristiction-api/pyproject.toml`
- System core: `src/aijurisdictionagents/__init__.py`

The page also includes a legal section with a structured disclaimer and `Last Updated` timestamp.

## Contact form

The contact form posts to the first-party API endpoint, which sends an email to `info@jurisdigta.eu` from the backend through the configured SMTP server. It does not open the user's local email client.

Local preview uses `http://127.0.0.1:8080/v1/contact` while the source page still contains the build placeholder. Deployed builds replace `__CONTACT_API_URL__` from the selected GitHub Environment's `CORPORATE_WEB_API_BASE_URL` variable, falling back to `API_BASE_URL` and then `https://api.jurisdigta.eu`.

Client-side protections include required structured fields, email validation, a hidden honeypot field, a minimum submit delay, disposable/test-domain blocking, web-link blocking, and Cloudflare Turnstile when `TURNSTILE_SITE_KEY` is injected during deploy. The topic must be at least 2 characters and the message at least 5 characters. The API repeats the critical honeypot, email, length, link, and Turnstile token checks before sending the email.

Turnstile is lazy-loaded only after a real `TURNSTILE_SITE_KEY` is injected, so local source previews never call Cloudflare with the placeholder key. If Cloudflare returns `400` for a real key on a deployed domain, add that exact hostname to the Turnstile widget's allowed domains or set the environment's `TURNSTILE_SITE_KEY` to a widget created for that domain.

## Video demo

The homepage switches the Jurisdigta avatar video per language:

- `assets/jurisdigta-sk.mp4` (SK)
- `assets/jurisdigta-ge.mp4` (DE)
- `assets/jurisdigta-en.mp4` (EN)

The video container constrains height to prevent oversized display on large screens.

## Minimal runnable example

Repo default: `python examples/minimal_demo.py`
Corporate web preview: `python -m http.server 8000` from `corporate-web`.
