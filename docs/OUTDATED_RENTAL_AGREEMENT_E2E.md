# Outdated Slovak Rental Agreement E2E

This scenario covers issue #426. It verifies that JurisDigta can review an
uploaded synthetic Slovak rental agreement, compare it with the current live
laws collector/RAG corpus, show extracted facts, suggest law-grounded changes,
and generate a corrected agreement for both Free and Paid users.

## Fixtures

- Original synthetic agreement:
  `api/chat-simulator-app/testcases/outdated-najomna-zmluva-2026.txt`
- Expected extracted fields and outdated themes:
  `api/chat-simulator-app/testcases/outdated-najomna-zmluva-2026.expected.json`
- Chat simulator prepared case:
  `api/chat-simulator-app/testcases/sample_outdated_najomna_zmluva_2026.txt`
- Human-readable suggested changes:
  `api/chat-simulator-app/testcases/outdated-najomna-zmluva-2026.suggested-changes.md`
- Human-readable corrected reference draft:
  `api/chat-simulator-app/testcases/outdated-najomna-zmluva-2026.corrected-reference.txt`

The fixture uses only synthetic people, addresses, identity-card numbers, and
bank-account data. Do not replace it with real lease-party data.

## E2E Command

Start the local API with live laws collector data available, then run:

```powershell
cd api/aijuristiction-api/e2e-playwright
npm run test:outdated-rental
```

The test checks:

- Free user route is local/free.
- Paid user route has an active Case-plan policy.
- The uploaded fixture is processed and appears in document debug context.
- The assistant message shows the extracted parties, property, rent, deposit,
  dates, and payment data from the old document.
- The assistant does not ask for those already-known fields.
- Suggested changes reference current Slovak law sources from the live corpus.
- The exported corrected agreement PDF contains the extracted facts and avoids
  unresolved placeholders.

## Compliance Notes

- GDPR: synthetic fixture only, no real personal data.
- GDPR minimization: the test asserts selected field values and diagnostics
  without dumping full generated documents into shared logs.
- EU AI Act: legal-risk output must remain transparent and subject to human
  review. The generated agreement is a draft for review, not guaranteed legal
  representation or filing.

The repository default minimal runnable example remains:

```powershell
python examples/minimal_demo.py
```
