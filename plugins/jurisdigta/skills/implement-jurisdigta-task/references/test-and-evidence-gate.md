# Test and Evidence Gate

## Unit-test requirement

Map every acceptance criterion and changed behavior to at least one focused test. Cover:

- success behavior;
- relevant validation and error paths;
- authorization, consent, or human-oversight boundary changes;
- retention/deletion or audit behavior when affected;
- regressions reproduced by bug fixes.

Use the component's established test framework and conventions. Test externally observable behavior; avoid assertions coupled only to implementation details.

## Playwright feasibility

Mark Playwright **applicable** when a browser or browser-driven API flow can verify the acceptance criteria, including:

- web UI behavior, layout, responsive states, accessibility-relevant interactions, or localization;
- authentication, signup, MFA, consent, subscription, or browser session flows;
- browser-to-API integration;
- document preview, generation, download, upload, or navigation;
- a bug whose reproduction steps occur in a web browser.

Mark Playwright **not applicable** only for changes such as isolated internal algorithms, workers with no browser contract, documentation-only changes, or infrastructure behavior that cannot be meaningfully exercised through the existing browser suites. Record the reason and add the strongest practical integration, contract, or service test instead.

## Select the existing suite

| Scope | Preferred location | Typical command source |
| --- | --- | --- |
| Frontend with mocked API or UI-only behavior | `frontend/aijurisdictionfronend/e2e/` | `frontend/aijurisdictionfronend/package.json` and README |
| Live frontend/API or API-driven browser scenario | `api/aijuristiction-api/e2e-playwright/tests/` | its `package.json`, Playwright config, and README/workflow |
| Mobile-only Flutter behavior | Flutter integration/widget tests first | Use Playwright only when a web surface or browser contract is also in scope |

Inspect the selected suite's configuration and nearby tests before adding a spec. Reuse its fixtures, web server startup, synthetic users, output paths, retries, and trace settings.

## Screenshot evidence

Capture screenshots only after the tested state is reached and assertions pass.

- Use deterministic synthetic accounts and content.
- Prefer the relevant page/region over unrelated full-desktop capture.
- Use stable descriptive names such as `issue-<id>-<flow>-<state>.png`.
- Save runtime output under `runs/e2e/` or Playwright's test output.
- Attach screenshots to the Playwright report with `testInfo.attach` when that suite uses attachments.
- For durable review evidence, copy only sanitized selected images to `docs/screenshots/issue-<id>/` and document the generation command.
- Add Markdown image links to the PR and task result after the branch is pushed.
- If the change has no visual state, do not manufacture a meaningless screenshot; state `Screenshot evidence: not applicable` with the E2E feasibility reason.

## Privacy review

Before publishing an image, verify it contains none of:

- real names, email addresses, phone numbers, postal addresses, IP addresses, or user identifiers;
- tokens, cookies, authorization headers, signed URLs, connection strings, or secret values;
- real legal-case facts, uploaded document content, payment data, or private messages;
- local usernames, browser bookmarks/history, notifications, or unrelated applications.

Regenerate with synthetic data or crop/redact before commit or upload. Never rely on a PR reviewer to catch sensitive content.

## Completion table

Include this table in the task result and PR:

| Gate | Result | Evidence |
| --- | --- | --- |
| Latest `origin/main` base | Pass/Fail | Commit SHA |
| Unit tests | Pass/Fail | Command and test files |
| Component validation | Pass/Fail | Commands |
| Playwright feasibility | Applicable/Not applicable | Reason |
| Playwright E2E | Pass/Fail/Not applicable | Command and spec |
| Screenshots | Added/Not applicable | Sanitized links or reason |
| GDPR/EU AI Act | Pass/Blocked | Controls reviewed |
