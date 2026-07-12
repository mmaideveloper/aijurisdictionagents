# E2E test evidence rule

Every user-facing E2E scenario must prove both the machine contract and the result visible to a user. A passing HTTP response without final UI evidence is not sufficient.

## Required evidence

1. Capture at least one final-state screenshot after the last business outcome is visible and stable.
2. Keep a trace on failure and a concise machine-readable result manifest.
3. For generated documents, retain the PDF, verify its `%PDF-` signature, non-zero size, expected page count, and extracted expected text.
4. Render the first PDF page to PNG next to the final UI preview screenshot.
5. Use ordered names: `01-audio-transcript.png`, `02-message-submitted.png`, `03-document-preview.png`, `04-generated-document.pdf`, and `05-pdf-first-page.png`.

## Voice scenarios

- Use only an approved synthetic audio fixture; real-person recordings are prohibited.
- Record the fixture locale and expected normalized transcript.
- Verify speech-to-text before submit and prove the submitted normalized text equals the reviewed UI transcript.
- Raw audio is transient input and must not be copied into logs, traces, screenshots, reports, or databases.
- Keep voice consent explicit; never bypass the application consent control.

## Legal-document safeguards

- Use synthetic identities and addresses only.
- Preview and PDF must say the output is a draft requiring human review before signing or reliance.
- Assert document type, parties, amount, due date, and currency in extracted PDF text. Visual comparison supplements these assertions; it does not replace them.
- Fail when preview is missing, PDF download fails, facts materially differ, or human-review wording is absent.

## Canonical audio-to-PDF scenario

`mobile_app/e2e-playwright/cases/audio-payment-confirmation.json` represents a synthetic request for confirmation of a EUR 5,000 payment to Janko Hraško at Testovo 10, due by the end of the year.

Minimal runnable example:

```powershell
cd mobile_app/e2e-playwright
npm ci
npm run test:case-rule
```

The full browser test additionally requires an approved Slovak synthetic WAV fixture or controlled Azure Speech configuration. Do not substitute another language and claim it validates Slovak STT.

## Retention

Local evidence belongs under ignored `mobile_app/e2e-playwright/artifacts/` and should be deleted after review or within seven days. CI retention must be seven days or less unless a documented audit requirement mandates longer.
