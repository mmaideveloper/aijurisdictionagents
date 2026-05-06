# Corporate Website

Location: `corporate-web`

This folder contains a single-page corporate presentation site for AI Jurisdiction.
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

Environments: `dev`, `test`, `prod` (manual dispatch).

FTP upload is used for all environments. Configure each GitHub Environment with:

- `corporate_web_ftp` (URL/host)
- `corporate_web_ftp_username`
- secret `corporate_web_ftp_password`

Remote FTP folder: `www_root_aiagenticsolutions_eu`.

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


## GDPR and EU AI Act content

The legal section on the corporate web page now explicitly covers:

- GDPR-oriented personal data handling principles (lawfulness, minimization, retention controls).
- EU AI Act transparency expectations for AI-assisted legal workflows.
- Human oversight requirements and user notification for AI-generated output.

- Added legal section #data-processing-consent for GDPR/AI Act data-processing disclosures and registration consent linking from mobile app.
