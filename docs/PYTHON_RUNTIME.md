# Python Runtime Baseline

JurisDigta uses Python 3.13 as its minimum and canonical Python runtime. Local conda
environments, package metadata, static-analysis targets, GitHub Actions jobs, monitoring
helpers, and deployed Python containers must use the same minor version.

## Supported runtime

- Minimum package requirement: Python 3.13.
- Local environment: `environment.yml` and `.python-version` select Python 3.13.
- Containers: repository-owned Python services use `python:3.13-slim`.
- CI: Python build, test, migration, deployment, and PDF-evidence jobs use Python 3.13.
- Python 3.10, 3.11, and 3.12 are not supported deployment or development targets.

Python 3.14 is intentionally outside the current support contract. Adopt a newer minor
version only in a dedicated migration after the complete binary dependency set—including
PyTorch, ONNX Runtime, OCR, image, and PDF packages—has published wheels for every supported
Windows and Linux target and the production container builds pass.

The Python 3.13 migration replaces the legacy `rapidocr-onnxruntime` distribution, which
declares Python `<3.13`, with the maintained `rapidocr` package plus an explicit ONNX Runtime
dependency. The document processor consumes the current structured `RapidOCROutput.txts`
contract; OCR failures retain the existing safe empty-result behavior and never fabricate text.

## Local setup

Create or refresh the repository environment with the task-worktree helper or conda:

```powershell
conda env update -f environment.yml --prune
conda activate ./conda
python --version
```

The reported interpreter must be Python 3.13.x. Package installers fail closed on older
interpreters because every repository Python package declares `requires-python = ">=3.13"`.

## Validation contract

Runtime migrations must validate all of the following on Python 3.13:

1. Root dependency installation, tests, static analysis, and `python examples/minimal_demo.py`.
2. API lint, mypy, and unit-test gates via `./scripts/validate_api.ps1` and the tracked
   pre-commit hook.
3. Chat simulator and document-engine focused tests.
4. API, laws collector, document processor, document engine, and monitoring helper container
   builds or safe import/health smoke checks as applicable.
5. Frontend PDF-evidence dependencies and Playwright evidence tests.

Compatibility failures must be fixed explicitly. Runtime migration must never change the
configured LLM provider, silently select `mock`, expose secrets in logs, or use production
personal data for validation. Synthetic test data and evidence remain under ignored `runs/`
or `artifacts/` paths according to `docs/E2E_TEST_EVIDENCE_RULE.md`.

## Upgrade policy

Treat a Python minor-version change as a system task. Use a dedicated branch/worktree, update
all declarations in one change, bump affected component revisions, validate Windows and Linux
wheel availability, and require every applicable build/test gate to pass for the exact commit
before deployment. Database schemas, retention/deletion behavior, consent controls, audit
logging, and human oversight for legal-risk outputs must remain unchanged unless separately
designed and reviewed.
