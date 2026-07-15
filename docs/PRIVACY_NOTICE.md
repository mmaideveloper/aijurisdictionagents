# Jurisdigta privacy notice

The localized privacy notice for `https://agent.jurisdigta.eu/privacy` is maintained in
`frontend/aijurisdictionfronend/src/content/legal.ts` and rendered by `PrivacyPolicy.tsx`.

## Verified controller details

- Controller: Esolutions SK s.r.o.
- IČO: 46491261
- DIČ: 2820020907
- Registered address: Partizánska 665/101, 059 18 Spišské Bystré, Slovakia
- Privacy contact: `info@jurisdigta.eu`
- DPO: none appointed as of 15 July 2026; the Article 37 assessment must be documented separately

## Processing and AI-routing disclosure

- Jurisdigta currently acts as controller for its own users.
- Local Ollama is the default model route and runs in Jurisdigta-controlled infrastructure.
- Microsoft Azure AI Foundry is configured for an EU data region and may receive approved case
  content only after the user explicitly approves the external route.
- Jurisdigta makes no solely automated approvals or legal decisions. Legal-risk AI output remains
  a draft subject to human review.
- Case submissions may contain third-party, special-category, or criminal-offence data. The notice
  requires data minimization and a valid GDPR/Slovak-law condition for such processing.

## Retention criteria

Do not advertise a universal retention period. The notice uses category-specific criteria:

- account data: active-account lifetime plus the period needed to close the account;
- case content, uploads, prompts, and outputs: while required by the case/account and longer only
  where a legal obligation or legal claim justifies it; users can request deletion through the
  published privacy contact;
- security logs and approval evidence: only as needed for security and compliance evidence;
- accounting documents: the applicable statutory period, generally ten years following the
  relevant accounting year under Slovak Act No. 431/2002 Coll.

Any new persistent data category must define its purpose, legal basis, recipient access, and an
enforceable deletion/retention rule before release. If actual runtime behavior differs from the
notice, fix the behavior or update and approve the notice before deployment.

## Release checks

- Verify and document the runtime retention/deletion behavior for database rows, uploaded files,
  generated documents, logs, and backups. The notice deliberately does not claim an automated
  hard-deletion schedule that the repository cannot currently demonstrate.
- Complete and retain the GDPR Article 37 assessment for whether a DPO must be appointed.
- Obtain approval of the final wording from the responsible privacy/legal owner before production
  deployment.

## Regulatory sources

- GDPR Article 13: <https://eur-lex.europa.eu/eli/reg/2016/679/art_13/oj>
- Slovak Act No. 18/2018 Coll., sections 19 and 29:
  <https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2018/18/20240701>
- Slovak Accounting Act No. 431/2002 Coll., section 35:
  <https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2002/431/20260601>
- Slovak Data Protection Office contact: <https://dataprotection.gov.sk/sk/kontakt/>

## Minimal verification

From `frontend/aijurisdictionfronend`:

```powershell
npm test -- --run src/__tests__/privacyPolicy.test.tsx
npx playwright test e2e/privacy-notice.spec.ts
npm run build
```

For a manual check, start the frontend, open `/privacy`, and select SK, EN, and DE. Confirm that the
controller identity, local/external model disclosure, retention criteria, user rights, complaint
link, and human-oversight statement remain visible in every language.

The Playwright test saves its full-page Slovak evidence screenshot to
`runs/e2e/privacy-notice-sk.png`.
