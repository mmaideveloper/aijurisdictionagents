# Assistant Architecture

The internal JurisDigta assistant should use JurisDigta MCP as its source-of-truth tool layer for Slovak legal answers.

## Runtime Flow

1. The frontend starts or resumes a `/v1/chat` session.
2. The chat API records the user turn and gathers case history, uploaded documents, and processed document chunks.
3. For Slovak legal turns, the chat API builds an internal MCP law context by calling `searchLaws` and `getLawText` over the configured MCP endpoint (`INTERNAL_MCP_BASE_URL` in production, with an in-process fallback for local tests).
4. The lawyer model receives the user conversation, case documents, uploaded documents, and the internal MCP law context.
5. The model must cite MCP law identifiers and relevant sections when the MCP context contains them, and must say when current-law lookup was unavailable or inconclusive.
6. Document drafting remains a separate validated workflow: ask for missing facts, require explicit user confirmation before final drafting, then export generated assets through the document export endpoints.

## Quality Target

Claude-like quality here means the assistant is not answering from model memory alone. It must ground Slovak legal answers in current JurisDigta MCP data, preserve case context, use uploaded documents when available, and produce downloadable documents only after the user confirms the drafting step.

## Local Models

Local models are acceptable for low-risk support tasks such as routing, summarization, anonymization, and offline demos. Production legal answers should continue to use the configured cloud provider until local models pass the same law-citation and document-quality evaluations as the production model.
