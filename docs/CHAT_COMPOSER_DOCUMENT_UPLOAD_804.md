# Chat composer document upload

The assistant composer exposes a paperclip upload control for the currently selected API-backed case. It accepts PDF, DOCX, common image formats, and text-based files. Uploads are submitted to the existing case document ingestion pipeline; the composer remains available while processing runs asynchronously.

The status line lists the selected filenames and stays visible through upload, processing, completion, or failure. Pending documents are explicitly described as unavailable for retrieval until processing and indexing finish. Retrying a failed filename removes the prior failed record before submitting the new upload, which prevents failed retries from accumulating duplicate case documents.

This flow is privacy by design: only the selected case receives the files, user-facing errors avoid internal paths and identifiers, and legal answers must not treat a pending document as retrieved evidence. The existing document retention and deletion controls remain authoritative, and the upload status does not replace required human legal review of generated answers.

## Real local browser test

`scripts/chat_upload_e2e.py` provides the task-specific synthetic setup (`seed`), API/MCP launch modes (`api`, `mcp`), and browser runner (`test`). It requires the migrated loopback PostgreSQL database `juris_chat_upload_804`, the approved credential bootstrap, and the configured synthetic E2E password. The browser uses real sign-in with seeded one-hour MFA/device verification, uploads through the file picker, checks persisted processing state, and verifies the unsent composer draft survives. No browser API responses are intercepted. Run from the repository root: `python scripts/chat_upload_e2e.py test` after starting the local services.

Screenshots and the sanitized result manifest live under ignored `runs/chat-upload-804/` for at most seven days. Authentication traces/video are disabled to avoid recording passwords. This upload test does not establish semantic-answer or legal-citation correctness; those require a separate complete retrieval assertion. Remove synthetic case/account records and task storage after review.
