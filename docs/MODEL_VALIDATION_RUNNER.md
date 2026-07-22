# Golden-case model validation runner

Issue #472 uses exported JurisDigta cases as reviewed inputs for repeatable model and legal-document
checks. The source of truth is a manually reviewed export made with synthetic facts. A ZIP assembled
outside JurisDigta is only a development seed because it does not prove the real case, chat,
document-rendering and model-audit path.

## Offline validation

Run the minimal scenario-01 fixture check:

```powershell
.\conda\python.exe examples\model_validation_runner_demo.py
.\conda\python.exe -m pytest tests\test_golden_cases.py tests\test_models_testing_fixtures.py
```

The reusable loader accepts the native `jurisdigta.case-export.v1` ZIP and the legacy scenario-01
seed. It extracts user prompts, assistant answers, generated document sources, actual model audit
entries and export warnings. Comparison normalizes Unicode, diacritics, case and whitespace, then
checks similarity plus required and forbidden text. PDF byte equality is intentionally unsupported.

## Live replay contract

A live runner should create isolated synthetic free and paid accounts, verify the free route is
local Ollama, activate the paid Case plan through the sandbox payment flow, replay the exported user
turns, and answer matching assistant questions from the golden transcript. An unmatched question may
receive a conservative configured answer, but the result must contain a warning.

For each run, write ignored artifacts under `runs/model-validation/<run-id>/`: transcript, warnings,
actual `provider`, `model`, `route_type`, status, fallback reason, timing/token/cost fields, exported
ZIP/PDF text and comparison JSON. Authentication secrets and payment details must never be copied to
fixtures or reports.

The native export records the models used twice: `manifest.json.models_used` provides a compact
summary and `ai-model-audit.json.entries` preserves the detailed trace. A fixture is automation-ready
only when at least one audit entry exists and every entry contains non-empty `provider`, `model`,
`route_type` and `status`. Whether the case facts were entered manually or generated synthetically
does not change this requirement: the model identity must come from the persisted server audit, never
from a manually typed fixture label.

Passing deterministic checks means the output conforms to the reviewed fixture; it is not automatic
approval of legal correctness. A qualified human must review material legal changes and any output
intended for signing, filing or reliance.

## Tester workflow: build golden-case data

Use this checklist for every scenario that will become automated golden-test data:

1. Create a dedicated JurisDigta test account. Do not use a customer or personal account.
2. Create a new case with a stable scenario ID, for example
   `01-private-loan-payment-confirmation`.
3. Enter only synthetic data: invented names and addresses, clearly fake identity numbers, fixed
   amounts and dates, and no customer or production data.
4. Run the complete conversation through JurisDigta using the same channel and wording that the
   automated replay will exercise.
5. Answer assistant follow-up questions with the predefined synthetic facts. Keep the answers stable
   and record any unmatched or improvised answer as a warning.
6. Generate the final legal document and rendered PDF through JurisDigta.
7. Manually review the parties and identifiers, amount and currency, transfer/payment method and
   date, receipt-versus-repayment meaning, signature blocks, citations, legal wording, and the
   human-review disclosure. Record the reviewer and review date outside sensitive fixture content.
8. Export the reviewed case through the JurisDigta case-export UI or endpoint. Do not assemble the
   production golden ZIP manually.
9. Verify the ZIP contains `manifest.json`, `case.json`, `messages.jsonl`,
   `ai-model-audit.json`, `citations.json`, `warnings.json`, source/generated document artifacts,
   rendered PDFs, and `sha256sums.txt`.
10. Verify model traceability in both `manifest.json.models_used` and
    `ai-model-audit.json.entries`. Every audit entry must contain the actual non-empty `provider`,
    `model`, `route_type`, and `status` persisted by the server. Never type these values into the
    fixture manually.
11. Copy the reviewed immutable ZIP to `tests/modelsTesting/cases/` using a stable filename.
12. Register the fixture in `tests/modelsTesting/index.json`, including its SHA-256, scenario ID,
    classification, expected route, required/forbidden assertions, citations, document type/count,
    and similarity thresholds.
13. Set `fixture_status` to `native_reviewed` only after the content review and model-audit checks
    pass. Legacy or incomplete fixtures must remain marked as seeds and are not automation-ready.
14. Run `.\conda\python.exe examples\model_validation_runner_demo.py --fixture <zip-path>` and
    `.\conda\python.exe -m pytest tests\test_golden_cases.py
    tests\test_models_testing_fixtures.py`.
15. Keep every later replay export separate under ignored `runs/model-validation/<run-id>/` and
    compare normalized text, required facts, citations, document type/count, decision/status, and
    model audit. Never compare raw PDF bytes or overwrite the reviewed golden ZIP.

If any step fails, do not promote the ZIP to `native_reviewed`. Correct the synthetic case in
JurisDigta, repeat the human review, create a new export, and update the registered checksum.

## Adding coverage

Follow the native-export steps in `tests/modelsTesting/README.md`. Keep missing fixture coverage
separate from model-validation failures. Create another GitHub issue only if the scenario exposes a
missing product behavior, document template/flow pack, or legal-source integration.
