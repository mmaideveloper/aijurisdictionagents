# aijurisdictionagents

Scaffold for a multi-agent legal discussion system with a Lawyer, Judge, and Orchestrator.

## VS Code
code -profile "mmaideveloper"
check:
git config --get user.name
git config --get user.email

Recommended: open the workspace file so the `.conda` interpreter is auto-detected.

```bash
code aijurisdictionagents.code-workspace
```

GitHub CLI (multiple accounts, refresh scopes):

```bash
gh auth status
gh auth switch --hostname github.com --user <USERNAME>
gh auth refresh -s read:project --hostname github.com
```

Project status automation (GitHub Project v2):

```powershell
.\scripts\project_status.ps1 -IssueNumber 2 -Status "In progress"
.\scripts\project_status.ps1 -IssueNumber 2 -Status "In review" -Comment "Implemented by Codex"
```

Requirements:
- `gh` authenticated to the correct account
- Scopes: `read:project` (list items) and `project` (edit status)

## Portable Codex Skills

Project Codex skills are versioned under `skills/` so the same workflows can be used on another computer after cloning the repository.

Available repo-local skills:
- `api`
- `chatsimulatr`
- `start-api`
- `start-mobile`
- `start-mobile-app`

Preview the skills that would be synced into your local Codex profile:

```bash
python examples/project_skills_demo.py
```

Install or refresh the repo skills into `~/.codex/skills` on the current machine:

```bash
python scripts/sync_codex_skills.py --force
```

For details, see `docs/PROJECT_SKILLS.md`.

Project polling automation (local scripts):

```bash
python scripts/project_poll.py --config .github/automation.yml --output runs/automation/latest_snapshot
```

Move Ready tasks with PRs to In review:

```bash
python scripts/project_in_review.py --config .github/automation.yml --plan-output runs/automation/latest_snapshot/in_review_plan.json
```

Offline fixture demo:

```bash
python examples/project_poll_demo.py
```

For details, see `docs/AUTOMATION_POLLING.md`.

Note:
- Automatic project polling/pooling and lifecycle GitHub workflows were removed.
- Reason: Codex automation requires `OPENAI_KEY` and a separate paid OpenAI API account (ChatGPT subscription alone is not sufficient).

Lifecycle automation demo (issue #69 MVP):

```bash
python examples/lifecycle_automation_demo.py
```

Lifecycle workflow:
- GitHub workflow automation for lifecycle is currently removed; use local lifecycle scripts/docs.

For details, see `LIFECYCLE_AUTOMATION.md`.

Auto-activate the conda env on open (workspace setting expects a local env at `.conda`):

```bash
conda env create -f environment.yml -p ./.conda
conda activate ./.conda
```

Then open the folder in VS Code; the Python extension will pick up `.conda` automatically.
For more details, see `docs/WORKSPACE.md`.

Conda notes:

- The local `.conda/` environment is intentionally gitignored.
- `environment.yml` provisions both editable Python packages in this monorepo: the root `aijurisdictionagents` package and `api/aijuristiction-api`.
- To update the environment later, run: `conda env update -f environment.yml --prune`
- Conda manages the interpreter and system packages; `pyproject.toml` defines the Python project metadata,
  dependencies, and tooling (needed for `pip install -e .`).


## Local Fake Payment Service

A fake PayPal-compatible payment simulator is available in `service/` for local integrations and demos.

```bash
node service/fake_paypal_service.js
```

Minimal runnable demo:

```bash
./service/examples/paypal_payment_demo.sh
```

For full endpoint details, see `service/README.md`.

## End-to-end contract simulations

Deterministic end-to-end test scenarios for contract summarization and Slovak `prenajom` lease modernization are documented in `docs/E2E_CONTRACT_TESTS.md`.

Run the minimal example:

```bash
python examples/minimal_demo.py
```

Slovak company verification prompt demo (Obchodný register-first flow):

```bash
python examples/slovak_company_check_minimal_demo.py
```

See `docs/SLOVAK_COMPANY_CHECKS.md` for the workflow details.

Run the end-to-end tests:

```bash
pytest e2etests/test_contract_end_to_end.py root_contract_end_to_end_test.py
```

## Features

- Document ingestion from `data/` (txt/md, PDF optional)
- Structured messages with `role`, `agent_name`, `content`, `sources[]`
- Orchestrated discussion (Lawyer -> Judge) with a final synthesis
- Trace artifacts under `runs/YYYYMMDD_HHMMSS/`

## Setup

Python 3.10+ is required.

Using conda:

```bash
conda create -n aijurisdictionagents python=3.10 -y
conda activate aijurisdictionagents
pip install -e ".[dev]"
```

Or using `environment.yml`:

```bash
conda env create -f environment.yml
conda activate aijurisdictionagents
pip install -e ".[dev]"
```

## Run the demo

For a complete execution matrix (all CLI options and both discussion types), see
`docs/RUN_DISCUSSION_TYPES.md`.

Put documents in `data/` and run (country required):

```bash
python -m aijurisdictionagents --country SK --data-dir "data/case_prenajom" --instruction "Priprav mi zmluvu na prenajom bytu." --discussion-type advice
```

Windows note: if `python` is not available in PATH, use one of:

```powershell
py -m aijurisdictionagents --country SK --data-dir "data/case_prenajom" --instruction "Priprav mi zmluvu na prenajom bytu." --discussion-type advice
```

```powershell
.\.conda\python.exe -m aijurisdictionagents --country SK --data-dir "data/case_prenajom" --instruction "Priprav mi zmluvu na prenajom bytu." --discussion-type advice
```

To run without documents, omit `--data-dir` (it defaults to none).

During the discussion, agents may ask follow-up questions. You have up to 5 minutes
(or the remaining discussion time) to reply by default. If you do not respond in time,
the system continues with a note that the user could not answer.

After each round, the CLI asks if you have more questions. Type `finish` to end the
discussion and generate the final result. If an agent asks you a question and you
answer it, the CLI will proceed without asking an extra follow-up prompt in that round.

Override the answer timeout (minutes):

```bash
python -m aijurisdictionagents --country SK --question-timeout-minutes 2 --instruction "..."
```

The console log includes the initial user instruction and each agent response so
the full conversation is visible.

Set a maximum discussion time (minutes); `0` means unlimited:

```bash
python -m aijurisdictionagents --country SK --data-dir data --discussion-max-minutes 15 --instruction "We believe the contract was breached due to late delivery."
```

Example (full setup + run):

```bash
conda activate ./.conda
python -m aijurisdictionagents --country SK --data-dir data --instruction "We believe the contract was breached due to late delivery."
```

Country and language parameters:
- `--country` is required (ISO 3166-1 alpha-2 or alpha-3 recommended, e.g. `SK`, `US`).
- `--language` is optional (BCP-47 tag recommended, e.g. `sk-SK`, `en-US`). If omitted, outputs default to the user's input language. If set, agent discussion and final outputs follow the requested language.

Discussion type:
- `--discussion-type advice` (default): Lawyer gives advice without judge review.
- `--discussion-type court`: Judge must approve or reject the lawyer's response; on rejection the lawyer retries. In court mode, the lawyer asks whether to draft filings when a court action is recommended, and the judge challenges weaknesses and requests missing documents.
- Document drafting workflow: when a user asks for any contract/legal document, the lawyer agent first asks whether the user already has an older version, requests upload for review, and updates it only if incorrect or out of date with current law; otherwise it proposes minimal edits or confirms no rewrite is needed.

Case storage (Slovak advice mode):
- For `--discussion-type advice` with `--country SK` (or Slovakia), a case folder is created under `cases/`.
- Uploaded files are copied to `cases/<case-id>/documents/` with a date prefix.
- Use `--case-id <guid>` to append a new discussion entry to an existing case.

Environment variables are loaded from `.env` if present. Copy `.env.example` to `.env`
and edit as needed.

To use OpenAI, set:

- `LLM_PROVIDER=openai`
- `OPENAI_KEY=...`
- `OPENAI_MODEL=gpt-4o-mini` (optional override)
- `OPENAI_TEMPERATURE=0.2` (optional override)

To use Azure Foundry (Azure OpenAI), set:

- `LLM_PROVIDER=azurefoundry`
- `AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE_NAME.openai.azure.com/`
- `AZURE_OPENAI_DEPLOYMENT=your_deployment_name`
- `AZURE_OPENAI_API_KEY=...` (or `AZURE_OPENAI_AD_TOKEN=...`)
- `AZURE_OPENAI_API_VERSION=2023-09-01-preview` (optional override)

Or use the minimal example script:

```bash
python examples/minimal_demo.py
```

Validator demo (conversation scoring):

```bash
python examples/validator_demo.py
```

For details, see `docs/AI_AGENTS_VALIDATOR.md`.

Example (minimal demo with conda):

```bash
conda activate ./.conda
python examples/minimal_demo.py
```

Optional PDF ingestion (requires `pypdf`):

```bash
pip install pypdf
python -m aijurisdictionagents --allow-pdf --instruction "Analyze the attached PDFs."
```

## Output

The CLI prints:

- Final recommendation
- Key citations (filename + snippet)
- Judge rationale

Trace artifacts are written to `runs/YYYYMMDD_HHMMSS/`:

- `run.log`
- `trace.jsonl`

`run.log` includes the active LLM provider (azurefoundry/openai/mock) at startup.
When using Azure Foundry, `run.log` also records the auth method, endpoint, deployment, API version, and temperature,
and temperature at INFO level.
`run.log` also includes masked token details at DEBUG level (never the full key).

## Debugging

Recommended: run under the VS Code debugger and watch the Debug Console.

1) Open Run & Debug (Ctrl+Shift+D)
2) Select **Run aijurisdictionagents**
3) Press **F5**

If it crashes, the full stack trace appears in the Debug Console and is also written to
the latest `runs/*/run.log`.

You can also run with extra diagnostics in a terminal:

```powershell
$env:PYTHONFAULTHANDLER="1"
$env:PYTHONTRACEMALLOC="1"
python -m aijurisdictionagents --instruction "We believe the contract was breached due to late delivery."
```

To change verbosity, use `--log-level` (default: DEBUG):

```bash
python -m aijurisdictionagents --log-level INFO --instruction "..."
```

## Tests

```bash
pytest
```

## CI

GitHub Actions runs unit tests on every pull request and on pushes to `main`.
Primary workflow names:
- `CoreSystemBuild`
- `web_build_deploy`
- `infra_deploy`

## Architecture

See `docs/ARCHITECTURE.md` for module boundaries and flow.

## API infrastructure (Azure)

Infrastructure-as-code and local deployment scripts for the API are in `infra/`.

Quick start:

```powershell
.\infra\scripts\deploy_api.ps1 -SubscriptionId "<your-subscription-id>" -AcrName "<globally-unique-acr-name>"
```

Local API docs (when API runs on port `8080`):
- Swagger UI: `http://localhost:8080/docs`
- OpenAPI JSON: `http://localhost:8080/openapi.json`

Project skill for local API startup:

```powershell
.\skills\start-api\scripts\start_api.ps1
```

Background mode:

```powershell
.\skills\start-api\scripts\start_api.ps1 -Background
```

For full details, see `infra/README.md`.

## Corporate website

The static corporate presentation site lives in `corporate-web`.

Quick preview:

```bash
cd corporate-web
python -m http.server 8000
```

Then open `http://localhost:8000` in a browser. For details, see `docs/CORPORATE_WEB.md`.

## Frontend demo app

The React + TypeScript demo app lives in `frontend/aijurisdictionfronend`.

Quick start:

```bash
cd frontend/aijurisdictionfronend
npm install
npm run dev
```

Then open `http://localhost:5173` in a browser. For details, see `docs/FRONTEND_DEMO.md`.

## Mobile app

Project skill for local mobile app startup:

```powershell
.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background
```

This launcher now asks for `localApi` or `publicDevApi`.
If you choose `localApi`, it also asks for database mode (`local`, `postgres`, `azure`) and storage mode (`local`, `azure`), then starts the API in a visible console window so live API logs are shown there.
Use `-ConsoleWindow` if you also want live Flutter logs in a separate terminal window.
If the local API is already running in the background, `-ConsoleWindow` also opens a separate PowerShell window that tails the API log files so request logs stay visible locally.

Examples:

```powershell
.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -ApiMode localApi -DatabaseOption postgres -DbCloud "postgresql://postgres:postgres@localhost:5432/aijurisdiction"
```

```powershell
.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -ApiMode localApi -DatabaseOption azure -DbCloud "<postgres-connection-string>" -StorageOption azure -StoreCloud "<azure-storage-connection-string>"
```

Project skill for the local chat simulator:

```powershell
.\skills\chatsimulatr\scripts\start_chat_simulator.ps1 -Background
```

### Deployment

The corporate site is deployed via GitHub Actions (`corporate_web` workflow) using FTP per environment.
Live URL: `https://www.aiagenticsolutions.eu/`

## Assumptions

- The default LLM provider is Azure Foundry (`LLM_PROVIDER=azurefoundry`).
- For local deterministic smoke testing without cloud credentials, set `LLM_PROVIDER=mock`.
- PDF ingestion is optional and requires installing `pypdf`.
- The initial version keeps all conversation state in memory.

## Tech info

1. set of ai agents to simulate lawyer, judge, mediator ...
2. allow user input about case ( question, set of documents, images)
3. start discussion and store discussion
4. create report with summary and final case results and store to folder together with case files
5. allow setup timeout for discussion, if not setup max 1h

Technical requirements:

1. use connection to OpenAI or Azure OpenAI, it is defined in .env
2. use DDD pattern as application design
3. tech. stack: python, conda - virtual environment
4. frondend over React/Next.js

Codex:
/prompt:draftpr

## Flutter mobile app (local test)

A Flutter mobile client is available in `mobile_app/` with chat UI, camera document capture, and local API mode toggles.

```bash
cd mobile_app
flutter pub get
flutter run
```

Technical design details: `docs/MOBILE_TECHNICAL_DESIGN.md`.

## Examples

- API database minimal demo: `python examples/api_database_minimal_demo.py`
- Database layout minimal demo: `python examples/database_layout_minimal_demo.py`
- Laws collector Postgres launcher demo: `powershell -ExecutionPolicy Bypass -File examples/start_laws_collector_postgres_demo.ps1`
- Laws collector live first-law demo: `python examples/laws_collector_live_first_law_demo.py`
- Slovak law corpus solution note: `docs/SLOVAK_LAW_DATA_PLATFORM.md`
- Slovak law corpus mockup preview: `powershell -ExecutionPolicy Bypass -File examples/preview_slovak_law_mockup.ps1`
- Laws collector minimal demo: `python examples/laws_collector_minimal_demo.py`
- Project skills demo: `python examples/project_skills_demo.py`

## Database layout

Database SQL assets now live only under `databases/<project>/`.
Local runtime database files now live only under `runs/storage/<project>/`.

Current database projects:

- `databases/api`
- `databases/laws-collector`

For the full layout and the rule for adding a new project database, see `docs/DATABASE_LAYOUT.md`.

## Laws collector

The laws collector package lives in `src/services/laws_collector`.
It now selects a country-specific implementation by `LAWS_COUNTRY`.
Only `slovak_laws_collector` is implemented today, and it keeps using PostgreSQL database `laws_sk`.
For Slovak records, the collector persists law year/number and also stores an optional parent law year/number when the imported act is an amendment of another law.
The Slovak sequential crawl now starts hardcoded at `1/1993`, persists the last collector run timestamp, and remembers the last processed law plus the next `number/year` probe target.
The live ingest path downloads the law from SlovLex, stores the text in the local database, computes a real embedding vector through the shared embedding client, chunk-embeds long laws to stay within model limits, and logs each processing step in the console.
The live SlovLex ingest also stores normalized law metadata in `law_metadata` and dependency links in `law_metadata_relations`, including `Predpis mení`, `Predpis je menený`, `Vykonávacie predpisy`, and `Predpis ruší`.
For debugger use, the VS Code laws-collector launch profiles now load `.env`, target the correct local Postgres port `5433`, limit each run to one live probe, and include a mock-embeddings option that avoids stepping into the OpenAI SDK.

Quick start:

```powershell
conda activate .\.conda
python examples/laws_collector_minimal_demo.py
```

Inspect the persisted sequential import state:

```powershell
conda activate .\.conda
python -m services.laws_collector --plan-import
```

Run a live Slov-Lex sequential probe loop:

```powershell
conda activate .\.conda
python -m services.laws_collector --run-sequential-import --max-probes 25
```

Inspect parsed metadata/relations for the canonical `461/2003` Slovak law:

```powershell
.\.conda\python.exe examples/laws_collector_metadata_demo.py
```

Local PostgreSQL debug example:

```powershell
conda activate .\.conda
python examples/laws_collector_postgres_debug_demo.py
```

Live first-law verification example:

```powershell
conda activate .\.conda
python examples/laws_collector_live_first_law_demo.py
```

For database, scheduling, and Azure migration guidance, see `docs/LAWS_COLLECTOR.md`.
