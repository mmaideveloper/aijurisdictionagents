# Private banks and reviewed imports (#924)

This replaces #840's anonymous Q&A reading. Visitors see published bank metadata only.
Registration stays on JurisDigta. Registered users request access; an existing central
administrator approves their tests user AND specific banks. Selecting all current banks
never grants future banks. Existing sessions receive no automatic grants. Tests management
is only on tests.jurisdigta.eu; agent administration has no new controls.

## Administrator workflow (desktop or mobile browser)

1. Sign in using an existing enabled administrator account; open **Správa testov**.
2. **Žiadosti a schválení používatelia** lists requested/approved accounts with a transient
   central email lookup. Enable the user, select banks and save. Save with no banks or disable
   the user to revoke access. A pending request saved without approval becomes rejected.
3. **Banky a import** creates draft banks and edits metadata, edition, categories, bank tags,
   dates and publication state. LF UK biology and chemistry start as empty drafts.
   Legal banks explicitly require a legal reference date; other subjects are not restricted
   to a hardcoded medical-subject list. Existing firearms banks retain their legal-date gate.
   Publish only after content review, source references and verified content rights. The checkbox is
   an administrator attestation; purchasing a book is not a completed rights assessment.
4. Import a text/scanned PDF or PNG/JPEG pages. Maximum: 100 MB combined, 500 pages per job.
   Multiple files retain the displayed order; move a file higher before upload where needed.
   Uploads use generated names and remain private. A separate worker processes one page at
   a time; progress survives restarts, cancellation and explicit retries.
5. Open the draft and original source files. Check numbering, categories, wording, reference
   answers, options, formulae, subquestion boundaries and source pages. Low-confidence OCR,
   page continuations and duplicates are flagged. Correct/omit records and explicitly save
   the review, then install. Installed questions are inactive; use Q&A editing to activate
   them after checking the bank's publication/rights conditions. Select all or individual records
   to activate/disable a reviewed batch with revision-conflict checks.
6. Q&A editing preserves existing direct/grouped structure and subquestion identities.
   Changed content has a revision and prior snapshot; conflicting edits return 409. Disabling
   a question blocks new reads/submissions and invalidates saved selections containing it.
7. Select questions, enter an AI tagging request AND rubric, then run the proposal.
   Example: use the agreed gymnasium curriculum to classify `school-year:1` through
   `school-year:4`. Review each question alongside tags/rationale; uncertain proposals require a clearer rubric or
   manual tags. Apply explicitly. Batch undo refuses to overwrite later question changes.

Diagrams remain in retained source pages and uncertain transcription must be reviewed;
this initial open-text renderer does not yet reproduce diagram-dependent exam layouts.
Exact LF UK choice/scoring rules remain deferred until an authorized sample is inspected.
No missing official answer is generated from general model knowledge.

## Learner workflow

Request a bank from the catalogue. After approval, open it, filter by text/category/tags,
select questions and save a named private study selection. Commas separate tags: choices
within the same prefix are OR; different prefixes are AND. For example,
`subject:biology,school-year:1,school-year:2` means biology AND (year 1 OR year 2).
Firearms category A remains a category; tags do not alter its official A–E exam selection.
Saved selections are learning/practice, never an assertion of official exam equivalence.

Grant/role changes are checked on subsequent requests, including existing sessions, history,
exports and saved sets. Expired banks cannot start/submit practice; granted historical content
is read-only. Future start dates block content opening. Withdrawn banks cannot start practice.
Previous attempts retain the exact submitted-content snapshot rather than adopting later edits.

## API, storage and privacy

- Public: `/api/tests`, sign-in/config/health and independent public law sources.
- Learner: bank access requests, private study sets and protected questions/sessions/history/export.
- Administrator: `/api/admin/users`, bank and Q&A management, import/tagging jobs, source viewing,
  draft review and explicit apply/retry/cancel/undo actions.
- Every mutation keeps exact origin and CSRF protection. Current central role determines admin;
  no client claim or copied tests-local role grants administrator authority.
- Migrations 005–006 add approvals/grants, revisions, tags/options/relations, saved sets, jobs,
  audit and explicit legal scope for generic bank publication.
  SQL stays in `databases/laws-tests`; runtime files stay under ignored `runs/storage/laws-tests`.

Jobs and original sources expire after 30 days, nonapproved requests after 90 days, minimized
audit events after 12 months; collections/grants are deleted on user removal. Existing attempt
retention remains 12 months. The worker cleans hourly; `laws_tests.cli purge` also performs
source/job cleanup and removes records for deleted central identities. Do not log raw book
content, prompts, answers, credentials or tokens. Send only source/questions and admin rubric
to the model, without learner account/progress data. Operator review of lawful basis, retention
and AI applicability is still required before rollout; this is study assistance, not admission
or certification decisions or medical advice.

## Run and validate locally

Use the task worktree, verified `codex-agent`/`laws-tests-dev` profiles and branch-local conda.
Install `pip install -e laws-tests/api`, migrate and seed as documented in the README. Alongside
the API and frontend, run from repository root:

```powershell
$env:PYTHONPATH='laws-tests/api;src'
.\conda\python.exe -m laws_tests.jobs
# One checkpoint only (one page or one question):
.\conda\python.exe -m laws_tests.jobs --once
.\conda\python.exe -m pytest laws-tests/tests -q
.\conda\python.exe -m ruff check laws-tests
.\conda\python.exe laws-tests/examples/minimal_demo.py --offline
```

Real synthetic acceptance uses `laws-tests/tests/run_private_acceptance.ps1`: dedicated ports
8940/8941 and isolated PostgreSQL 5494/container `laws-tests-924-postgres`. It invokes the approved
server-to-local credential bootstrap, tests PNG/JPEG/scanned PDF/text PDF and actual AI tagging/
practice. Sanitized screenshots/manifests under ignored `runs/issue924/evidence` expire after
14 days. Private device credentials are removed with synthetic accounts. Missing real services/
credentials leave acceptance pending. General offline example: `python examples/minimal_demo.py`.
The combined runner reuses its selected PostgreSQL instance for both suites; it never starts
two servers on the same data directory. Standalone private acceptance defaults to instance
924/port 5494; pass `-Instance` and `-DatabasePort` to reuse an existing worktree-owned instance.
Its bootstrap uses `--skip-account`; only the uniquely named private fixture accounts are created.

## Relationship to #841 and rollout

#924 owns the generic importer. #841 remains necessary to prepare the actual firearms book
dataset, reconstruct A–E grouping/ordered subquestions, validate legal dates and law anchors,
resolve uncertain citations and obtain human/rights publication review. It should reuse this
importer rather than build another one. Do not close #841 merely because this platform exists.

Deployment requires the worker/shared restricted volume and new least-privilege grants; see
`docs/manual_infrastucture_setup.md` and `docs/GITHUB_ENVIRONMENTS.md`. No production deployment
is authorized by implementation. Rollback must retain the private access gate or use maintenance
mode; never expose private banks by reverting to the old anonymous reader.

For parallel local verification in one task worktree, the legacy reader/account runner can use
`run_acceptance.ps1 -Instance 924 -DatabasePort 5494 -SkipPrivate` after the private suite has
been run separately. These are local harness parameters, not GitHub workflow inputs. Default
CI invocation still runs both suites. The instance check refuses containers owned by other
worktrees; the explicit legacy synthetic account remains confined to the selected local database.
