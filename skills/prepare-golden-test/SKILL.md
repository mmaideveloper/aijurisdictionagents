---
name: prepare-golden-test
description: Prepare a native JurisDigta case-export ZIP as a deterministic golden-test fixture. Use when a developer supplies an exported case ZIP and source GitHub issue, asks to prepare or promote a golden case, or invokes `/prepare-golden-test`; validate safety, native schema, checksums, PDFs, persisted model audit, source facts, assertions, review state, and registry metadata before delivery.
---

# Prepare Golden Test

Prepare one exported synthetic case per dedicated branch/worktree. Treat legal correctness as a human decision: automation can create `technical_reviewed`, but only explicit human approval can promote the same PR to `native_reviewed`.

## Preparation workflow

1. Read the source issue, `docs/CASE_EXPORT_TEST_FIXTURES.md`, and `tests/modelsTesting/README.md`. Confirm the issue declares synthetic data and identify source facts, required/forbidden content, document type, and legal markers. Do not invent provider, model, route type, or status.
2. Before editing, run the repository environment-profile pull, create a task-specific branch/worktree with `scripts/new_task_worktree.ps1`, and move the issue to `In progress` with `scripts/project_status.ps1`.
3. Create a quarantine-only assertions JSON under `runs/model-validation/issue-<number>/`. Include:
   - `case_key`, `scenario_id`, `language`, `country`, `category`, and `fixture_purpose`;
   - non-empty `source_facts` present in both the issue and reviewed output;
   - `answer` and `document` `must_contain`, `must_not_contain`, and similarity thresholds;
   - `document.type` and `marker_phrases` for `document_title`, `parties`, `operative_statement`, `signature_block`, `limited_claim_scope`, and `human_review_disclosure`.
4. Run from repository root:

   ```powershell
   .\skills\prepare-golden-test\scripts\prepare_golden_test.ps1 prepare `
     --issue 602 `
     --zip C:\path\case-export.zip `
     --assertions-json runs\model-validation\issue-602\assertions.json `
     --expected-scenario-id 01-private-loan-payment-confirmation
   ```

   The command copies the unchanged ZIP into quarantine first, rejects unsafe/incomplete content, writes a validation report plus transient PDF/text/first-page evidence, copies the approved bytes to `tests/modelsTesting/cases/`, and updates `index.json` as `technical_reviewed`.
5. Inspect the generated registry diff. Run the skill validator, focused tests, PDF checks, and `python examples/minimal_demo.py`. Run other affected gates in proportion to the change.
6. Commit, push, open a PR to `main`, comment `Implemented by Codex`, and move the source task to `In review`. Never merge the PR.

The canonical production route defaults to `azurefoundry`. If the persisted audit does not match the requested route, stop; never substitute mock or another provider.

## Human promotion

After a human reviews the genuine production conversation, document, PDF, checksums, and model audit, save their approval evidence in ignored quarantine as JSON:

```json
{
  "reviewer": "github-handle",
  "approval_reference": "https://github.com/OWNER/REPO/pull/123#pullrequestreview-456",
  "approved_at": "2026-08-09T12:00:00Z",
  "production_path_confirmed": true
}
```

Then update the same branch/PR:

```powershell
.\skills\prepare-golden-test\scripts\prepare_golden_test.ps1 promote `
  --issue 602 `
  --case-key issue-602-private-loan-payment-confirmation `
  --human-approval-json runs\model-validation\issue-602\approval.json
```

Promotion revalidates the unchanged fixture and requires native export provenance plus the explicit approval record. A manually assembled ZIP can remain `technical_reviewed`, but do not confirm its production path or promote it. Commit the small state change, rerun validation, and leave merge to the human-approved close-task workflow.

## Safety and retention

- Keep `runs/model-validation/issue-<number>/<run-id>/` ignored and delete it after review/merge or within seven days.
- Keep only immutable approved ZIPs under `tests/modelsTesting/cases/`; quarantine is not a second golden database.
- Reject traversal, archive bombs, executables, secrets, tokens, payment credentials, unrelated cases, missing audits, invalid PDFs, and non-synthetic inputs before tracked promotion.
- Compare normalized text and assertions, not raw PDF bytes or exact model wording. Model output is never proof of legal correctness.
