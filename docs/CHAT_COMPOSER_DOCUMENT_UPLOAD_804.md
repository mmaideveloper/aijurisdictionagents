# Chat composer document upload

The assistant composer exposes a paperclip upload control for the currently selected API-backed case. It accepts PDF, DOCX, common image formats, and text-based files. Uploads are submitted to the existing case document ingestion pipeline; the composer remains available while processing runs asynchronously.

The status line lists the selected filenames and stays visible through upload, processing, completion, or failure. Pending documents are explicitly described as unavailable for retrieval until processing and indexing finish. Retrying a failed filename removes the prior failed record before submitting the new upload, which prevents failed retries from accumulating duplicate case documents.

This flow is privacy by design: only the selected case receives the files, user-facing errors avoid internal paths and identifiers, and legal answers must not treat a pending document as retrieved evidence. The existing document retention and deletion controls remain authoritative, and the upload status does not replace required human legal review of generated answers.
