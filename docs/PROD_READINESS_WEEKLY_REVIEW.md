# JurisDigta Weekly Production Readiness Review

This runbook defines the weekly production-readiness review that reports what
still blocks JurisDigta from production and paid public launch.

## Automation

- Automation id: `jurisdigta-weekly-prod-readiness-review`
- Schedule: every Monday morning at 08:00 in the local Codex runtime timezone
- Runtime: Codex cron automation in an isolated worktree
- Report sections: Technical, Business, Legal

The automation must inspect repository documentation, GitHub issues, and Project
5/6 status before reporting. For business or legal requirements that can change,
it should verify official/current sources where possible.

## Current Production Blocker List

### Technical

| Area | Issue | Required outcome |
| --- | --- | --- |
| AI model routing production validation | #387 | Model-router foundation is merged to `main`, tested end to end, and proven for free local-only routing, paid external routing, budget fallback, EU data-zone checks, and usage ledger metrics. |
| Payment system | #363 / #362 | Production payment provider, webhook verification, subscription lifecycle, failed payment, cancellation, refund, VAT/tax, and checkout security are implemented and tested. |
| Invoicing | #364 | Canonical invoice domain, UBL XML, PDF output, credit notes/corrective invoices, email transport, audit events, and future Peppol-ready boundaries are implemented. |
| User data encryption | #384 / #182 | Encryption in transit and at rest is designed and implemented with key management that fits AI processing and user-controlled confidentiality requirements. |
| Audit trail and correlation id | #206 / #303 | User, case, mobile, API, system, model, source, tool-call, and document-generation steps are traceable per request without leaking sensitive content. |
| Disaster recovery | #385 | Encrypted backups, retention, restore script, restore rehearsal, RTO/RPO evidence, and monitoring status are complete. |
| Dedicated test/pre-prod environment | #388 | A non-production environment exists with isolated data, secrets, deployment workflows, monitoring, and end-to-end validation. |
| AI output validation | #297 / #298 / #301 | Hallucination checks, source validation, fairness/quality reports, confidence scoring, and output guardrails are implemented for legal-risk outputs. |
| Admin web | #378 | Admin-only model routing, pricing, user-group, local-model, and audit-management UI/APIs are implemented on top of the model-router foundation. |

### Business

| Area | Issue | Required outcome |
| --- | --- | --- |
| Paid subscription commercial launch package | #390 | Pricing, plan limits, refund/cancellation policy, support/SLA, checkout wording, complaint process, and subscription operations are owner-approved and aligned with payment/invoicing. |
| Grant and funding readiness | #393 | Prepare JurisDigta grant dossier and application path. Recommended sequence: EIC Accelerator as the strategic target, SIEA EIC advisory voucher after an EIC short-proposal GO, Digital Europe cascade calls as a parallel watch, and EDIH support for test-before-invest and funding guidance. |
| Production operating model | linked to #385 / #388 / #390 | Define who approves releases, monitors incidents, handles user support, processes refunds, and owns legal/compliance escalations. |

### Legal

| Area | Issue | Required outcome |
| --- | --- | --- |
| Consent, DSAR, retention, and AI transparency | #389 | GDPR consent ledger, data subject rights, retention/deletion jobs, AI response transparency metadata, and compliance event logging are implemented. |
| Slovak legal-service positioning and advertising review | #391 | JurisDigta marketing, checkout, onboarding, and product wording are reviewed so the product is not misrepresented as unauthorized lawyer representation or guaranteed legal advice. |
| Customer-facing documents | #390 / #391 | Terms of Service, Privacy Policy, Cookie Policy, Refund/Cancellation Policy, withdrawal/withdrawal-exception wording, complaint process, and AI limitations notice are ready in SK, EN, and GE before public paid launch. |
| Third-party processor and AI provider governance | #389 / #387 | Provider list, data-processing basis, external-model acknowledgement, EU data-zone policy, and processor records are documented and implemented. |

## Weekly Report Requirements

Every Monday report must include:

1. Technical blockers and changed status since last review.
2. Business blockers and any owner decisions needed.
3. Legal blockers and any official-source changes that affect launch.
4. Newly created GitHub tasks, if the automation found a missing blocker.
5. Top 5 next actions for the coming week.

The automation must avoid duplicate issues. It should search open and closed
issues before creating a new blocker task, then add new tasks to Project 5 with
status `Ready` when GitHub Project access is available.

## Compliance Baseline

Every production-readiness item must be evaluated against GDPR and the EU AI
Act. The default controls are privacy by design, data minimization, explicit
consent where required, retention/deletion controls, user transparency,
traceable logging, and human oversight for legal-risk outputs.

## Minimal Runnable Example

The repository default smoke check remains:

```powershell
python examples/minimal_demo.py
```
