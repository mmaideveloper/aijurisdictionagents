# Corporate Web

Static single-page site for AI Jurisdiction.

## Local debugging

From repo root:

```bash
cd src/corporate-web
python -m http.server 8000
```

Open `http://localhost:8000` in a browser.

If port 8000 is busy:

```bash
python -m http.server 8001
```

## Language switch

The page ships with Slovak (default) and German translations. Use the `SK/DE` toggle in the header.
The selection is stored in `localStorage` (`aj_lang`).
