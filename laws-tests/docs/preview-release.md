# Owner-authorized initial preview

On 2026-09-27 the owner explicitly requested production deployment with the existing
five-question set, with complete category banks to follow under #841. This release uses
`preview` status, not `published` or `development`. Every visitor sees the incomplete,
not-legally-reviewed notice. Authentication, private result retention/deletion and real
model grading continue to apply. No rights confirmation, legal review or legal date is
fabricated. Published content still requires all original review constraints. Law readers
with no approved legal date retain the explicit unavailable explanation.

Migration 004 adds the status and mandatory notice. The gated migration imports the
versioned `seeds/preview.sql` artifact only when the entire course bank is empty. It never
overwrites or downgrades reviewed content. #841 later replaces the preview through the
normal reviewed import. Existing source wording and photographed provenance remain intact.
The model output stays labelled as practice feedback rather than official certification.
The GDPR/EU AI Act assessment is unchanged: no additional personal data, model access or
retention; added public transparency distinguishes temporary content from verified content.

## Checks and minimal example

```powershell
python -m laws_tests.cli migrate
python -m pytest laws-tests/tests/test_preview.py -q
python laws-tests/examples/minimal_demo.py
```

Full release acceptance still requires the exact-commit GitHub `laws-tests-real-e2e` job,
all applicable builds/tests and post-deployment synthetic smoke. No release gate is waived.
The account frontend's actual public host is `web.jurisdigta.eu`; its `/tests-authorize`
route and `/auth` flow are deployed from the same verified commit. `deploy_account.sh`
verifies the known static-container topology, retains the stopped previous container,
and restores it on readiness failure. It does not replace the corporate root website or
the API/MCP/document services. The previous account container is the rollback point.

## Temporary Windows acceptance runner

Use an operator-controlled Windows/X64 runner with label `laws-tests-e2e`, Node, Edge,
Docker Desktop, SSH and the approved local model credentials. `test` environment variable
`LAWS_TEST_E2E_PYTHON` optionally points to an existing trusted Python interpreter with the
project dependencies; otherwise the script uses branch-local `conda/python.exe`. Source
imports explicitly use the checked-out commit's API and `src` directories. This permits
an ephemeral runner without copying credentials or weakening model/database checks.
The variable is a local executable path, not a secret. Authoritative profiles are pulled
after checkout. All databases remain local and synthetic; every scenario cleans its records.
Screenshots/manifests are the only uploaded artifacts and expire after 14 days.
Checkout preserves ignored synthetic database storage between runs (`clean: false`);
the checked-out tracked source remains the exact requested commit. Deployment installs
and starts the hourly retention timer after the verified release becomes current.

For this release, use a checksum-verified official GitHub Actions runner archive and an
ephemeral registration scoped to this repository. Run it hidden under the current trusted
operator without installing a persistent service. After the single job it unregisters;
register another one-time instance for the final main commit if required. Never allow
untrusted fork code onto this credential-enabled runner. Retain the ignored local source
database volume for troubleshooting; stop it before another workspace claims its port.
