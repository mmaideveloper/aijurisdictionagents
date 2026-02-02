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
