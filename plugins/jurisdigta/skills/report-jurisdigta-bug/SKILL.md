---
name: report-jurisdigta-bug
description: Investigate a reported Jurisdigta defect using user-provided symptoms, optional screenshots, privacy-minimized production logs, and the aijurisdictionagents repository, then ask focused follow-up questions and create a structured GitHub issue only after human confirmation. Use when a user says Jurisdigta is broken, reports unexpected behavior or an incident, asks to inspect server logs for a defect, or wants a bug filed in mmaideveloper/aijurisdictionagents.
---

# Report a Jurisdigta Bug

Create a reproducible, evidence-based bug report without copying secrets, personal data, legal-case content, or unnecessary production logs into GitHub.

## Workflow

1. Restate the reported symptom and distinguish fact from hypothesis.
2. Ask whether the user has screenshots or screen recordings and invite them to attach any relevant images. Treat images as optional; continue if none exist.
3. Collect the minimum intake details:
   - concise description;
   - expected and actual behavior;
   - approximate time with timezone;
   - environment and affected channel;
   - reproduction steps, frequency, and user impact;
   - request ID or correlation ID when available.
4. Review relevant repository code, tests, documentation, recent changes, and existing GitHub issues before diagnosing.
5. Ask for permission before accessing production logs. Explain that only a narrow time window and relevant services will be queried.
6. Collect server evidence read-only. Prefer existing repository diagnostics such as `infra/scripts/tail_api_logs.ps1`. For the self-managed host, use `ssh -o BatchMode=yes jurisdigta-server` with bounded `docker logs`, `journalctl`, or `tail` queries. Never access `.env`, private keys, database rows, uploaded documents, prompts, message bodies, or full legal-case content.
7. Sanitize evidence before analysis or storage. Follow [privacy-and-log-handling.md](references/privacy-and-log-handling.md).
8. Correlate the description, image evidence, logs, code paths, tests, and similar issues. State the likely component and confidence; do not present an unverified root cause as fact.
9. Ask up to three focused questions only when missing answers materially affect reproducibility, severity, security/privacy handling, or acceptance criteria.
10. Draft the issue using [github-issue-template.md](references/github-issue-template.md) for `mmaideveloper/aijurisdictionagents`.
11. Show the complete title and body to the user. Require explicit confirmation before creating the GitHub issue or uploading sanitized images/log excerpts, unless the user has already explicitly approved that exact draft.
12. Create the issue through the connected GitHub tool when available, with `gh` as fallback. Apply existing repository bug labels when confidently known; do not invent labels.
13. Return the issue link and summarize what evidence was included and deliberately excluded.

## Safety and compliance gates

- Stop and report a potential security incident privately instead of filing a public issue when evidence contains credentials, authentication tokens, exploitable security details, or a suspected personal-data breach.
- Minimize production-log access by service, time window, identifiers, and line count. Do not persist raw production logs in the repository.
- Redact names, email addresses, phone numbers, IP addresses, session/user/case/document IDs, access tokens, cookies, authorization headers, connection strings, prompts, document text, and legal facts unless a specific non-personal identifier is essential and approved.
- Treat screenshots as potentially sensitive. Inspect them before upload and ask for a redacted replacement when sensitive data is visible.
- Keep legal-risk conclusions subject to human review. The issue may describe software behavior but must not make legal determinations about an affected user.
- Record the evidence source and collection time in the issue, but include only the smallest sanitized excerpt needed for reproduction and triage.

## Image handling

When images are attached:

- confirm which action and timestamp each image represents;
- inspect for sensitive content and metadata;
- extract only relevant visible error text;
- prefer a redacted crop over a full-screen upload;
- obtain confirmation before attaching the sanitized image to GitHub.

## GitHub write boundary

Reading logs, code, and issues is diagnostic work. Creating or editing a GitHub issue is an external write. Never perform the write until the user has reviewed and confirmed the final sanitized draft.
