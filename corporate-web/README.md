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

## Video demo

The homepage switches the Jurisdigta avatar video per language:

- `assets/jurisdigta-sk.mp4` (SK)
- `assets/jurisdigta-ge.mp4` (DE)
- `assets/jurisdigta-en.mp4` (EN)

The video container constrains height to prevent oversized display on large screens.

## Minimal runnable example

Repo default: `python examples/minimal_demo.py`
Corporate web preview: `python -m http.server 8000` from `corporate-web`.
