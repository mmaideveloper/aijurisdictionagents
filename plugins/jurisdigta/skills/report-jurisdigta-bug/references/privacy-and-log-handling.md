# Privacy and Log Handling

## Collection contract

- Obtain permission for production-log access.
- Query the smallest useful time range, starting with 15 minutes around the reported event.
- Select only relevant services and cap output, normally at 200 lines.
- Prefer request/correlation IDs and aggregate operational events over free-text searches for user data.
- Keep commands read-only and report the exact source and UTC collection time.

## Prohibited sources

Do not read or copy:

- `.env`, secret stores, private keys, tokens, cookies, or authorization headers;
- database records, uploaded documents, prompt/response bodies, email bodies, or legal-case facts;
- broad log archives when a bounded query can answer the question.

## Redaction checklist

Before showing or uploading evidence, remove or replace:

- names, emails, phone numbers, postal addresses, IP addresses, and device identifiers;
- user, tenant, case, document, session, and payment identifiers;
- credentials, connection strings, query parameters containing personal data, and signed URLs;
- document text, chat content, legal facts, filenames, and stack-frame local paths that reveal usernames.

Use stable placeholders such as `[EMAIL_REDACTED]`, `[CASE_ID_REDACTED]`, and `[TOKEN_REDACTED]`. Preserve timestamps, error codes, service names, source locations, and request/correlation IDs only when non-personal and necessary.

## Retention

- Keep raw production output ephemeral in the current diagnostic session.
- Do not write raw logs under the repository.
- Put only sanitized excerpts in GitHub and state that raw logs were excluded.
- Delete temporary local evidence after the draft is confirmed or abandoned.

## Escalation

If credentials, a suspected breach, special-category data, or exploitable security details appear, stop public issue creation. Notify the user that private security/privacy handling is required and provide only a sanitized summary.
