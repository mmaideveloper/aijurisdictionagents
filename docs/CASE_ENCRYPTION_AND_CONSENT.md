# Case encryption and consented exports (#922)

## Approved scope

On 2026-10-19 the user selected platform-managed per-case encryption, a 24-hour
request-specific consent lifetime, one download, a one-hour temporary archive
lifetime, and web consent controls first. This resolves the key-custody choice
for #922; #384's user-held-key proposal is not implemented here. The platform
can decrypt for authorized processing. This is not end-to-end encryption.

## Storage contract

AES-256-GCM encrypts each payload with a random 96-bit nonce. Each case has a
random 256-bit data key wrapped by the active platform key. Wrapped keys live
in `case_encryption_keys`; the platform key ring is a separate protected runtime
file named by `CASE_ENCRYPTION_KEY_FILE`. Keys and plaintext never belong in Git.
Authenticated additional data binds ciphertext to its case and field or file
path. Corruption and unavailable keys fail closed. Runtime `from_env()` requires
the key file; direct constructors without keys are for isolated offline fixtures.

Implemented fields: case titles, document filenames, document/transcript bytes,
communication summaries/presentation JSON, extracted document text, chunk text
and vector values. Citations, model audit previews/metadata, catalog previews/events,
software assessments, document reviews, processing errors, privacy-artifact metadata, workflow state/events/checkpoints and
case-related queued email content are also encrypted. Opaque file names avoid leaking uploaded names in file paths.
Owner data exports decrypt these fields but exclude key tables. Search decrypts
only the selected case's existing in-memory retrieval inputs. This does not
change the embedding model or ranking algorithm. A bounded 128-entry key cache
expires after 15 seconds; key-ring changes invalidate cached keys. No decrypted
document cache is introduced. Storage encryption/TLS remain required for all
databases, backups, metadata and transports.

Workflow checkpoint primitives are forced into encrypted blobs; operational checkpoint metadata keeps only source, step and parent IDs. Detailed legacy admin debug/trace endpoints are disabled for encrypted deployments because they would bypass owner consent. Operational IDs, status, timestamps, sizes, model routes, ownership relationships and email routing recipients remain searchable metadata. Platform disk/database/backup encryption and restricted service access are required for that metadata. Non-case account and public legal-source data use their existing controls.

## Consent and authorization

Case APIs authenticate device tokens and bind the supplied owner to that token.
Exports use `/v1/case-exports`. A dedicated `case_export_permissions` row and an
enabled admin account are both required; legacy API keys and local admin-header
bypasses do not authorize this new export path. Operators grant this permission
through controlled database administration; there is no self-granting API.

The admin requests an immutable case set and purpose. Each owner sees only their
case IDs, recipient administrator, purpose and full archive content disclosure.
Each owner must approve. Denial/revocation invalidates the whole request. Both
generation and download recheck the administrator, every owner, ownership,
case status, unchanged case revision and expiry. Requests cannot expand after consent. Row locks serialize
revocation, generation and one-time download. A consumed download is not retried
automatically after a network failure: obtain a new consented request.

The API worker checks pending approved requests every 15 seconds. Archives are
encrypted before persistence. Their deadline is the earlier of consent expiry
and generation plus one hour. Expired artifacts are cleared within the next
worker cycle; downloads reject them immediately at the deadline. Worker downtime
can delay physical cleanup, but cannot extend download authorization. Startup
resumes cleanup. Successful download clears the artifact in the same transaction
that consumes the grant. The owner sees completion in the web request list.
Each request is limited to 50 cases and 64 MiB of source bytes/archive bytes; larger requests fail safely. Downloaded copies cannot be remotely recalled. Archive SHA-256 manifests detect
accidental corruption; they are not digital signatures against a malicious
recipient rewriting both content and manifest.

## Migration, rotation, recovery and deletion

Stop API, email and workflow writers before running `python scripts/migrate_case_encryption.py --offline-confirmed`, then `python scripts/migrate_case_workflow_encryption.py --offline-confirmed` for PostgreSQL workflow storage. Take an encrypted backup under the approved retention
policy first. The migration verifies round trips, atomically replaces files with
ciphertext, and can resume after interruption. Legacy plaintext is rejected by
encrypted reads until migration completes. Historical file names are replaced with opaque names. An encrypted migration journal permits recovery across file/DB updates and is removed after old-file cleanup.
Rollback restores an encrypted backup and the matching key ring, not a live
plaintext deployment. Never discard recovery keys before verifying restore.

The key-ring format is `{"active":"key-id","keys":{"key-id":"BASE64_32_BYTES"}}`.
Load a new key alongside the previous key, set it active, rewrap case keys with
`CaseCipher.rotate(case_id)`, verify reading every case and restore a backup, then
retire old keys according to backup retention. This first implementation uses a
protected mounted key ring, not remote Key Vault unwrap operations. Production
key distribution, ACLs and recovery are operator responsibilities.

Soft deletion is not cryptographic erasure. Permanent erasure must clear case
rows, payloads, wrapped keys, grants, queues, caches and recoverable backups under
the documented retention policy. Do not promise instant erasure while backups
or the bounded key cache remain recoverable.

## Validation

Run `python examples/encrypted_case_export_demo.py`,
`python -m pytest tests/test_case_encryption_exports.py`, API lint/type checks,
the full API suite and the frontend build. Offline tests do not count as final
E2E evidence. `scripts/run_issue922_e2e.py` isolates synthetic users and sources
in local PostgreSQL and uses the approved real Azure Foundry model. Evidence
belongs in ignored `runs/issue922/`, is retained at most seven days, and must
exclude private authentication files and key material. Remove private auth
files immediately after acceptance. Final evidence must include ciphertext
inspection, real-model route, grounded answer, consent and denial checks,
downloaded ZIP validation and a stable screenshot.

GDPR controls include data minimization, purpose-specific export authorization,
withdrawal before download and owner disclosure. Consent to this export does
not establish the lawful basis for every underlying processing operation or
third party's personal data. Preserve human review of legal-risk AI output;
this change is not a legal compliance certification.

## Validation evidence

Use `runs/issue922/` for synthetic-only transient validation. Real-model browser acceptance must include the final screenshot, actual provider/model route, ciphertext inspection and verified ZIP/PDF content. Unit tests alone are not E2E acceptance. Delete private authentication files immediately after the run, clean task-specific database records/files, and delete sanitized evidence within seven days. No deployment is authorized by this implementation.


## Performance and review limits

The synthetic local PostgreSQL benchmark uses 100 chunks, 384-dimensional fixed
vectors and 40 alternating measured iterations after warm-up. It compares the
same database-read, vector-parsing and cosine-ranking workload with and without
encryption. Top-five results are identical. Batched key resolution measured
172.17 ms plaintext p95 and 176.74 ms encrypted p95 (+2.66%), below the provisional
10% overhead target. This is a small-workload regression check, not a production
capacity guarantee or end-to-end model latency benchmark. Re-run
`python scripts/benchmark_case_encryption.py` on representative case sizes before
capacity decisions; it uses the isolated #922 local database configuration.

This implementation review covers unauthorized case access, consent bypass,
archive replay/races, missing/rotated keys, corrupted ciphertext, migration
interruption and exposure in secondary persistence. Runtime service identities
remain trusted to decrypt authorized cases. An administrator with database plus
platform-key access, host compromise, provider-side retention and downloaded
copies are outside application-encryption protection. Release owners must verify
key-file ACLs/mounts, encrypted backups and restore, retention policy and provider
contracts separately. This is not a penetration test or compliance certification.

Permanent purge explicitly deletes dependent content even on legacy PostgreSQL
schemas without cascading foreign keys. An erasure marker prevents key recreation;
offline migration honors existing markers. Historical encrypted queues/traces and
backups remain subject to their retention/deletion procedures and cannot be read
once the corresponding key is gone. Service restart clears bounded in-memory keys.


### Local acceptance, 2026-10-19

- API Ruff and mypy: passed (118 source files); full API suite: 810 passed with five existing skips. Privacy suite: eight passed.
- Encryption/export core suite: nine passed, including concurrent single download, multi-owner consent, revocation/expiry, rotation and key recovery, permanent erasure and interrupted migration/file-journal recovery.
- Frontend production build and real browser E2E: passed. Real route: `azure_foundry / gpt-4o-mini`. Frontend 5192, API/export/document workers 8922, MCP 8923, isolated PostgreSQL databases on 5432/5433.
- Synthetic document facts EUR 7319 / BLUE-922 were returned. The expected seeded law ID `issue-635-civil-code` was returned through the frontend and direct MCP section-569 lookup.
- ZIP exact-case membership and all checksums, deliberate corruption rejection, exported source PDF byte equality/text/structure, rendered PDF and final UI screenshots: passed. Downloaded archive was removed from persistent storage and replay returned 403.
- Persisted fields/files were ciphertext; a real PostgreSQL LangGraph checkpoint round trip recovered encrypted primitive values. Both offline migrations completed and subsequent passes changed zero records. Both runnable examples passed.
- Transient evidence: `runs/issue922/result-manifest.json`, `encrypted-case-answer.png`, `owner-export-completed.png`, `verified-exported-source.pdf`, `verified-exported-source-page1.png`, `consented-export.zip`, test logs and benchmark JSON. Retain sanitized evidence at most seven days.

An existing concurrent schema-initialization deadlock was observed on the unrelated
`GET /v1/admin/ai-models` dashboard request. The export panel is independent of
that dashboard load and the consent/export scenario passed. This observation is
not a claim that the entire admin dashboard passed acceptance; address it as a
separate task. The real answer retains the existing human-review/unverified-source
disclosures; this test establishes decryption and expected source routing, not
general legal-answer correctness.


### Reproducing local acceptance

Create empty, task-only loopback PostgreSQL databases `issue922` (port 5432) and
`issue922_e2e_laws` (port 5433). Pull the approved `codex-agent` environment profile;
import/bootstrap the approved E2E Azure Foundry credential using the repository
scripts with the API target set to this loopback database. Never use customer data.
Run `python scripts/run_issue922_e2e.py setup` to seed synthetic identities, the law,
a synthetic PDF and a task-only key ring. The harness uses the approved
`E2E_AZURE_FOUNDRY_*` profile settings, not a mock model. Apply current API migrations
and start `python scripts/run_issue922_e2e.py api` and the same command with `mcp`.
Wait for both services to be ready, then run the harness with `authenticate`.
Start the frontend on port 5192 with `VITE_API_BASE_URL=http://127.0.0.1:8922`.
From the frontend directory run
`npx playwright test --config playwright.issue922.config.ts`; from the repository
root run `python scripts/benchmark_case_encryption.py` and
`python scripts/verify_issue922_evidence.py`. Verification requires Poppler on PATH.
Review the final screenshots and rendered PDF. Stop these task services and remove
only the verified task databases, `runs/storage/issue922`, private auth files and
test key ring. Keep the sanitized evidence for no more than seven days.

The recorded acceptance run completed that cleanup: both isolated databases,
runtime case storage, private auth files and the test key ring were removed.
