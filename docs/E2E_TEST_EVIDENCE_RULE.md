# E2E test evidence rule

Every user-facing E2E scenario must prove both the machine contract and the result visible to a user. A passing HTTP response without final UI evidence is not sufficient.

## Required evidence

1. Capture at least one final-state screenshot after the last business outcome is visible and stable.
2. Keep a trace on failure and a concise machine-readable result manifest.
3. For generated documents, retain the PDF, verify its `%PDF-` signature, non-zero size, expected page count, and extracted expected text.
4. Render the first PDF page to PNG next to the final UI preview screenshot.
5. Use ordered names: `01-audio-transcript.png`, `02-message-submitted.png`, `03-document-preview.png`, `04-generated-document.pdf`, and `05-pdf-first-page.png`.

For a golden document scenario, use `prepare-golden-test` after exporting the case. Its ignored
quarantine must retain the final-state screenshot when the scenario is user-facing, the generated
PDF, extracted expected text, and the first-page PNG. The validator checks PDF structure and text;
the screenshot remains visual evidence and cannot replace those checks. The tracked golden ZIP
remains the only fixture, while extracted evidence stays transient.

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
- A legal-basis scenario must assert the same verified provision and named act in the document
  preview, extracted PDF text, and structured citations. Use an official source URL and keep the
  deterministic fixture's effective/as-of date visible in its metadata; the fixture does not
  substitute for a separate live-law freshness integration test.

## Canonical audio-to-PDF scenario

`mobile_app/e2e-playwright/cases/audio-payment-confirmation.json` represents a synthetic request for confirmation of a EUR 5,000 payment to Janko Hraško at Testovo 10, due by the end of the year.

Minimal runnable example:

```powershell
cd mobile_app/e2e-playwright
npm ci
npm run test:case-rule
```

Run the full controlled browser scenario with:

```powershell
cd mobile_app/e2e-playwright
npm ci
npm run test:audio
```

The command generates an approved synthetic WAV locally, passes it to Chromium as the fake microphone source, controls the browser Web Speech boundary, verifies that the reviewed transcript is the exact message submitted to the system, and downloads a valid PDF. The fixture may use a non-Slovak installed synthetic voice because speech recognition is controlled in this test; the manifest must record `sttBoundary: controlled-browser-web-speech` and the result must not be reported as a live Azure STT accuracy measurement.

A separate provider integration test is required to claim live Slovak Azure STT accuracy. That test must use a working Cognitive Services subscription/resource, remain opt-in, and must not replace the deterministic browser E2E gate.

## Retention

Local evidence belongs under ignored `mobile_app/e2e-playwright/artifacts/` and should be deleted after review or within seven days. CI retention must be seven days or less unless a documented audit requirement mandates longer.
