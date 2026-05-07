# Corporate Website

Location: `corporate-web`

This folder contains a single-page corporate presentation site for AI Jurisdigta.
It is static HTML/CSS and can be hosted on any static web server.

## Quick preview

From repo root:

```bash
cd corporate-web
python -m http.server 8000
```

Then open `http://localhost:8000` in a browser.

## Language

- Default language: Slovak (`sk`).
- Additional languages: German (`de`), English (`en`).
- The toggle persists in `localStorage` under `aj_lang`.

## Legal links

- Footer includes links to Privacy Policy, Disclaimer, and Terms of Service.
- Legal section content is translated for `sk`, `de`, and `en`.
- Disclaimer includes a visible `Last Updated` date.

## Deployment (GitHub Actions)

Workflow: `.github/workflows/corporate_web_deploy.yml`

Environments: `dev`, `test`, `prod`, `Prod` (manual dispatch).

FTP upload is used for all environments. Configure each GitHub Environment with:

- `corporate_web_ftp` (URL/host)
- `corporate_web_ftp_username`
- `corporate_web_ftp_dir` (remote folder for this hostname, for example the subdomain's web root)
- `CORPORATE_WEB_API_BASE_URL` (API base URL for the environment, for example the dev API URL; `/v1` or `/v1/contact` suffixes are also accepted)
- `TURNSTILE_SITE_KEY` (public Cloudflare Turnstile site key for the contact form)
- secret `corporate_web_ftp_password`

Remote FTP folder: set through `corporate_web_ftp_dir` in the selected GitHub Environment.

During deploy, the workflow updates the footer version labels from the current repository sources:

- API version from `api/aijuristiction-api/pyproject.toml`
- System core version from `src/aijurisdictionagents/__init__.py`
- Contact API endpoint from `CORPORATE_WEB_API_BASE_URL`, with `API_BASE_URL` as fallback and `/v1/contact` appended
- Stylesheet cache-busting query string from API version and Git commit SHA

FTP deploy uses clean-slate mode for `corporate_web_ftp_dir`, so the selected remote folder should be dedicated to this corporate web hostname.

## Files

- `index.html` - main single-page layout
- `styles.css` - branding, layout, and motion
- `assets/aj-logo.svg` - placeholder logo
- `assets/hero-graph.svg` - hero illustration
- `README.md` - local debugging notes


## Document upload limits

- Free plan: up to 2 uploaded documents per case.
- Basic plan: up to 5 uploaded documents per case.
- Premium plan: up to 50 uploaded documents per case.
- Test phone `+421944400166` keeps premium-equivalent document capacity for validation flows.

Paid plans also show that lawyer review is available after an extra payment.

The five-column legal section uses defensive word wrapping so long legal terms remain inside each card at narrower desktop widths and high browser zoom levels.


## GDPR and EU AI Act content

The legal section on the corporate web page now explicitly covers:

- GDPR-oriented personal data handling principles (lawfulness, minimization, retention controls).
- EU AI Act transparency expectations for AI-assisted legal workflows.
- Human oversight requirements and user notification for AI-generated output.

- Added legal section #data-processing-consent for GDPR/AI Act data-processing disclosures and registration consent linking from mobile app.

## Contact delivery

The contact form sends requests to `POST /v1/contact` on the configured API base URL, which sends an email to `info@jurisdigta.eu` from the backend using the configured SMTP server. Local corporate-web preview uses `http://127.0.0.1:8080/v1/contact`; deployed builds inject the selected GitHub Environment API URL. The page does not open a local mail-client draft.

When the selected GitHub Environment defines `TURNSTILE_SITE_KEY`, the deploy workflow injects it into the static page and shows Cloudflare Turnstile on the contact form. The API must also have `CONTACT_CAPTCHA_REQUIRED=true` and secret `TURNSTILE_SECRET_KEY` configured so the token is verified server-side before SMTP delivery.
The static page lazy-loads Turnstile only after a real site key is present. If Cloudflare returns `400` for a real key on `jurisdigta.aiagenticsolutions.eu`, configure that exact hostname in the Turnstile widget's allowed domains or use a widget key created for that hostname.
The API also applies a lightweight per-IP contact throttle using `CONTACT_RATE_LIMIT_MAX_REQUESTS` and `CONTACT_RATE_LIMIT_WINDOW_SECONDS` to reduce repeated SMTP abuse.
