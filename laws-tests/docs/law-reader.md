# Public law references (#840)

The question and original answer expose deterministic `linked_body` and `linked_answer`
text tokens alongside the unchanged original strings. Numbered `…/… Z. z.` references
open the JurisDigta Tests public reader in a separate tab (`noopener noreferrer`). This
does not require login and does not expose attempts, identities or LLM evaluation.

Bare provision references require editorial `legal_references` annotations on the question
or subquestion. Never infer the law from the last number, category, or an LLM. An annotation
must match a unique exact quote in the specified field; stale/ambiguous annotations remain
ordinary text. Example (SQL imports use JSONB, not user-supplied HTML):

```json
[{"field":"answer","quote":"§ 4 ods. 2 písm. j)","law_number":190,
  "law_year":2003,"section":"4","paragraph":"2","letter":"j"}]
```

This is a formatting example, not a legal assertion. Review attribution together with the
source bank in #841. Draft A-20 annotations are development-only. References spanning
multiple paragraphs intentionally open their common section instead of claiming a single
paragraph represents the whole citation.

The API resolves `/api/laws/{year}/{number}?test={id}&section=4&paragraph=2&letter=j`
against the course's **server-side legal_date**. Public links cannot override that date or
access a draft course in production. Missing dates return 409, missing source versions 404,
and unavailable library connections 503 with a Slovak explanation. There is no fallback
to today's or a future version. Metadata effective-to dates prevent displaying an expired
version as applicable. Collector import completeness and publication review remain release
prerequisites; this reader cannot reconstruct missing historical source versions.

The read-only collector connection is `LAWS_TEST_LAWS_DATABASE_URL` in `.env-laws-test`.
It must have only SELECT on `law_documents`, `law_versions`, `law_metadata`,
`law_provisions`, and `source_artifacts`. Production uses a dedicated reader role;
development accepts loopback PostgreSQL only. SQL is parameterized, read-only and bounded
by a five-second statement timeout. Source HTML is never executed; React displays plain
text. Official source links are restricted to HTTPS Slov-Lex hosts. No model, consent,
profile copying, or new personal-data retention is involved (GDPR/EU AI Act assessment).

Native collector anchors (`paragraf-4.odsek-2.pismeno-j.text`) select the exact block and
descendants. Missing anchors produce an explicit notice with no misleading highlight.
The reader displays all available collected provisions, the course date, effective dates,
and the official version artifact link if available.

## Runnable local example and checks

With the isolated PostgreSQL service prepared per the README:

```powershell
$env:PYTHONPATH='laws-tests/api;src'
.\conda\python.exe -m laws_tests.cli migrate
.\conda\python.exe -m laws_tests.cli seed-development
.\conda\python.exe -m pytest laws-tests/tests/test_legal.py -q
.\conda\python.exe laws-tests/tests/reader_fixture.py
.\conda\python.exe laws-tests/tests/run_local_service.py tests
# Separate terminal: start the tests frontend, then:
cd laws-tests/web
npx playwright test e2e/law-reader.spec.ts
```

The fixture applies all current collector migrations to the separate local
`laws_tests_sources_840` database in the isolated cluster under
`runs/storage/laws-tests/postgres/data`. SQL assets are under
`databases/laws-collector/seeds/issue840/`. It creates a unique synthetic course/source and
two source versions to prove date selection. The browser opens links from actual question
and answer content, checks the API source/version IDs, exact highlighting, missing-date
and missing-anchor states, new-tab behavior, desktop/mobile overflow and absence of a
login cookie. Cleanup removes its course and source records; rerun cleanup explicitly if
interrupted. Evidence stays in ignored `runs/issue840/evidence` for 14 days.

This is reader-specific integration/browser evidence. It does not replace the broader
frontend → API → MCP → real-model case-answer legal retrieval acceptance required by
`docs/E2E_TEST_EVIDENCE_RULE.md`, or the exact-commit production deployment checks.
