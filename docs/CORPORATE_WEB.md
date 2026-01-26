# Corporate Website

Location: `src/corporate-web`

This folder contains a single-page corporate presentation site for AI Jurisdiction.
It is static HTML/CSS and can be hosted on any static web server.

## Quick preview

From repo root:

```bash
cd src/corporate-web
python -m http.server 8000
```

Then open `http://localhost:8000` in a browser.

## Language

- Default language: Slovak (`sk`).
- Additional languages: German (`de`), English (`en`).
- The toggle persists in `localStorage` under `aj_lang`.

## Files

- `index.html` - main single-page layout
- `styles.css` - branding, layout, and motion
- `assets/aj-logo.svg` - placeholder logo
- `assets/hero-graph.svg` - hero illustration
- `README.md` - local debugging notes
