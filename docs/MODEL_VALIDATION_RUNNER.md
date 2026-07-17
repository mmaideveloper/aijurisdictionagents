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

Passing deterministic checks means the output conforms to the reviewed fixture; it is not automatic
approval of legal correctness. A qualified human must review material legal changes and any output
intended for signing, filing or reliance.

## Adding coverage

Follow the native-export steps in `tests/modelsTesting/README.md`. Keep missing fixture coverage
separate from model-validation failures. Create another GitHub issue only if the scenario exposes a
missing product behavior, document template/flow pack, or legal-source integration.
