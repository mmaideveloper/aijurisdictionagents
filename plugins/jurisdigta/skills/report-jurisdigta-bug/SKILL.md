---
name: report-jurisdigta-bug
description: Investigate a reported Jurisdigta defect using user-provided symptoms, optional screenshots, environment-routed local or jurisdigta-server logs, and the aijurisdictionagents repository, then ask focused follow-up questions and create a structured GitHub issue only after human confirmation. Use when a user says Jurisdigta is broken, reports unexpected behavior or an incident, asks to inspect local or server logs for a defect, or wants a bug filed in mmaideveloper/aijurisdictionagents.
---

# Report a Jurisdigta Bug

Create a reproducible, evidence-based bug report without copying secrets, personal data, legal-case content, or unnecessary production logs into GitHub.

## Workflow

1. Restate the reported symptom and distinguish fact from hypothesis.
2. Get a concise description of the error, including the visible message or behavior.
3. Ask: **"Did this error happen locally or on `jurisdigta-server`?"** Do not inspect any logs until the user answers. If the original description already states the environment unambiguously, acknowledge and confirm that environment instead of asking a redundant question.
4. Ask whether the user has screenshots or screen recordings and invite them to attach any relevant images. Treat images as optional; continue if none exist.
5. Collect the remaining minimum intake details:
   - expected and actual behavior;
   - approximate time with timezone;
   - affected channel and service;
   - reproduction steps, frequency, and user impact;
   - request ID or correlation ID when available.
6. Review relevant repository code, tests, documentation, recent changes, and existing GitHub issues before diagnosing.
7. Route diagnostics according to [diagnostic-routing.md](references/diagnostic-routing.md):
   - for **local**, inspect only local terminal output, local `runs/` logs, and local container/service logs;
   - for **`jurisdigta-server`**, ask for permission before remote log access, then use only bounded read-only SSH/server queries;
   - never combine local and server logs unless evidence shows a cross-environment problem and the user approves expanding scope.
8. Sanitize evidence before analysis or storage. Follow [privacy-and-log-handling.md](references/privacy-and-log-handling.md).
9. Correlate the description, image evidence, environment-specific logs, code paths, tests, and similar issues. State the likely component and confidence; do not present an unverified root cause as fact.
10. Ask up to three focused questions only when missing answers materially affect reproducibility, severity, security/privacy handling, or acceptance criteria.
11. Draft the issue using [github-issue-template.md](references/github-issue-template.md) for `mmaideveloper/aijurisdictionagents`.
12. Show the complete title and body to the user. Require explicit confirmation before creating the GitHub issue or uploading sanitized images/log excerpts, unless the user has already explicitly approved that exact draft.
13. Create the issue through the connected GitHub tool when available, with `gh` as fallback. Apply existing repository bug labels when confidently known; do not invent labels.
14. Return the issue link and summarize what evidence was included and deliberately excluded.

## Safety and compliance gates

- Stop and report a potential security incident privately instead of filing a public issue when evidence contains credentials, authentication tokens, exploitable security details, or a suspected personal-data breach.
- Do not access `jurisdigta-server` when the user says the error is local. Do not diagnose a server-reported error solely from local logs.
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
