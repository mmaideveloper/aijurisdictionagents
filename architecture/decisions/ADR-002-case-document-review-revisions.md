# ADR-002: Case-private extraction and explicit document revisions

Status: Accepted for the combined #800/#623 implementation authorized by the product owner.

## Decision

Reuse the case processor, configured embeddings, model router and internal MCP corpus.
Preserve uploaded bytes and extracted reading order. Keep text/chunks/vectors in the
owning case; public law searches receive only act identifiers or a generic legal query.
Paragraph identifiers refer to extracted text, not original page geometry.

Require authenticated device identity and case ownership for review. External review
requires explicit acknowledgement. Validate each exact original paragraph, source ID
and law section before storing a proposal. Persist proposals, evidence and decisions
in `document_reviews` with cascading deletion through the original document/case.
Bind decisions/exports to the text hash and optimistic revision. A stable client UUID
maps retries to one review without resetting decisions. Export only after every change
has been accepted or rejected. Preserve DOCX paragraph/table hierarchy where unambiguous.

Use one typed legal-basis resolver for generated document storage and PDF rendering.
A corpus match proves section presence, not official-source freshness or applicability.
Disclose that limitation and reduce unverified numerical scores to zero; unavailable
scores remain unavailable. Do not infer the legal regime from a document title.

## GDPR and EU AI Act design assessment

This adds assisted drafting and human choices, not autonomous legal decisions. The
existing case-processing purpose and applicable lawful basis govern derived text,
vectors, proposals and decisions. External acknowledgement is a processing control,
not a substitute for a lawful basis for third-party data. Minimize uploaded facts,
inherit retention/legal-hold/deletion controls, and exclude private review bodies from
model logs and debug bundles. Production classification and organizational obligations
remain with the responsible privacy/legal owner; this ADR does not certify compliance.

## Alternatives and consequences

Whole-document replacement and automatic acceptance were rejected because unrelated
changes become difficult to detect. Native Word tracked changes, pixel-perfect scan
reconstruction and a claim of live official-law verification are not provided.
Malformed/ambiguous extraction and ungrounded responses fail visibly. OCR confidence
warnings require source inspection; model proposals remain drafts needing human review.

See [UC-002](../use-cases/UC-002-review-uploaded-legal-document.md) and the
[implementation guide](../../docs/DOCUMENT_REVIEW_800.md).
