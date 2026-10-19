# ADR-004: Require explicit per-user and per-bank grants

## Record
- Status: Accepted (product access decision only)
- Date: 2026-10-18
- Decision owner/source: product owner, [#924](https://github.com/mmaideveloper/aijurisdictionagents/issues/924) and originating explicit confirmation.
- Supersedes: None (changes the public-reading requirement in historical #840).
- Superseded by: None
- Related: [UC-004](../use-cases/UC-004-private-study-banks.md), [ADD-003](../design/ADD-003-private-study-banks.md).

## Context and options
Current reader exposes published Q&A anonymously. The owner requests private restricted banks for selected learners and existing administrators.

Option A, registration-only access: simple, but cannot implement explicit selected-person/bank access. Option B, global user approval: supports restricted people but cannot separate firearms and medical banks. Option C, user approval plus bank grants: supports both restrictions, at the cost of additional request/grant UI and authorization checks. All options reuse central identity; independent tests accounts would add synchronization and privacy risk without user value.

## Decision and consequences
Confirmed: select C. Existing enabled central administrators administer only the tests interface. Everyone else needs an approved tests user and an approved exact bank grant. No automatic future-bank grants or grandfathering of existing sessions. Check role and grants from authoritative stores on each protected request. Public catalogue exposes metadata only.

Positive: explicit scope, predictable revocation and reusable banks. Trade-off: approval overhead and a compatibility change for previous public reader links. Operational rollback must not silently restore anonymous book-content access.

## Security, privacy and follow-up
Keep user/email profiles central, display email only to authenticated admins and minimize redacted audit metadata. Test direct reads, session/submission, search, history/export, private collection ownership, expired access and role demotion. This accepted product decision is not legal, architecture-board or production release approval. Content rights, retention policy and AI classification remain operator review responsibilities under UC-004.
