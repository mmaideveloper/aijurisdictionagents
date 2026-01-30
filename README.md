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

Auto-activate the conda env on open (workspace setting expects a local env at `.conda`):

```bash
conda env create -f environment.yml -p ./.conda
conda activate ./.conda
```

Then open the folder in VS Code; the Python extension will pick up `.conda` automatically.
For more details, see `docs/WORKSPACE.md`.

Conda notes:

- The local `.conda/` environment is intentionally gitignored.
- To update the environment later, run: `conda env update -f environment.yml --prune`
- Conda manages the interpreter and system packages; `pyproject.toml` defines the Python project metadata,
  dependencies, and tooling (needed for `pip install -e .`).


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
```

## Run the demo

Put documents in `data/` and run (country required):

```bash
python -m aijurisdictionagents --country SK --data-dir data --instruction "We believe the contract was breached due to late delivery."
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
- `--discussion-type advice` (default): Lawyer gives advice; judge review is optional.
- `--discussion-type court`: Judge must approve or reject the lawyer's response; on rejection the lawyer retries. In court mode, the lawyer asks whether to draft filings when a court action is recommended, and the judge challenges weaknesses and requests missing documents.

Case storage (Slovak advice mode):
- For `--discussion-type advice` with `--country SK` (or Slovakia), a case folder is created under `cases/`.
- Uploaded files are copied to `cases/<CASE-ID>/documents/` with a date prefix.
- Use `--case-id CASE-...` to append a new discussion entry to an existing case.

Environment variables are loaded from `.env` if present. Copy `.env.example` to `.env`
and edit as needed.

To use OpenAI, set:

- `LLM_PROVIDER=openai`
- `OPENAI_API_KEY=...`
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

`run.log` includes the active LLM provider (mock/OpenAI) at startup.
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

## Architecture

See `docs/ARCHITECTURE.md` for module boundaries and flow.

## Corporate website

The static corporate presentation site lives in `src/corporate-web`.

Quick preview:

```bash
cd src/corporate-web
python -m http.server 8000
```

Then open `http://localhost:8000` in a browser. For details, see `docs/CORPORATE_WEB.md`.

### Deployment

The corporate site is deployed via GitHub Actions (`corporate_web` workflow) using FTP per environment.
Live URL: `https://www.aiagenticsolutions.eu/`

## Assumptions

- The default LLM provider is a deterministic mock (`LLM_PROVIDER=mock`).
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
