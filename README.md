# aijurisdictionagents

Scaffold for a multi-agent legal discussion system with a Lawyer, Judge, and Orchestrator.

## VS Code
code -profile "mmaideveloper"
check:
git config --get user.name
git config --get user.email

Auto-activate the conda env on open (workspace setting expects a local env at `.conda`):

```bash
conda env create -f environment.yml -p ./.conda
conda activate ./.conda
```

Then open the folder in VS Code; the Python extension will pick up `.conda` automatically.

Conda notes:

- The local `.conda/` environment is intentionally gitignored.
- To update the environment later, run: `conda env update -f environment.yml --prune`


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

Put documents in `data/` and run:

```bash
python -m aijurisdictionagents --instruction "We believe the contract was breached due to late delivery."
```

To use OpenAI, set:

- `LLM_PROVIDER=openai`
- `OPENAI_API_KEY=...`
- `OPENAI_MODEL=gpt-4o-mini` (optional override)
- `OPENAI_TEMPERATURE=0.2` (optional override)

Or use the minimal example script:

```bash
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

## Tests

```bash
pytest
```

## Architecture

See `docs/ARCHITECTURE.md` for module boundaries and flow.

## Assumptions

- The default LLM provider is a deterministic mock (`LLM_PROVIDER=mock`).
- PDF ingestion is optional and requires installing `pypdf`.
- The initial version keeps all conversation state in memory.

## Tech info

1. set of ai agents to simulate layer, judge, mediator ...
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
