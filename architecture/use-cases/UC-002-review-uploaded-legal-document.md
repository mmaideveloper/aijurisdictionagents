# UC-002: Review an uploaded Slovak legal document

Actor: signed-in case owner. Scope: combined #800 and #623.

1. Upload PDF, DOCX, JPEG or PNG. Validate content/limits before storage.
2. Extract embedded text or local OCR, retain the original and index case chunks.
3. Open the document in the signed-in frontend; inspect extracted text and OCR warnings.
4. Add facts and explicitly request review, acknowledging external processing when used.
5. Retrieve effective corpus sources through MCP; validate structured proposals and citations.
6. Inspect old/new wording and reasons. Accept or reject each proposal; retain choices on reload.
7. Download the server-generated DOCX/PDF revision with accepted changes and source evidence.
8. Source/case deletion removes derived reviews through the existing retention lifecycle.

Alternatives: unreadable files need a clearer upload; unavailable sources require retry;
missing facts trigger questions; invalid model references fail validation; ambiguous
DOCX mapping cannot produce a misleading Word revision. An empty review is not a legal guarantee.

Flow: frontend -> case API -> processor -> case PostgreSQL; review -> MCP -> law PostgreSQL;
approved model route -> validated proposals -> case PostgreSQL; decisions -> preview/export.
Public law searches never receive contract text.

Acceptance and retention: [Document review guide](../../docs/DOCUMENT_REVIEW_800.md).
