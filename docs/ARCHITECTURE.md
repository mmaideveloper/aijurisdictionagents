# Architecture

## Components

- Agents: `Lawyer` advocates for the user and `Judge` evaluates and asks clarifying questions.
- Orchestration: `Orchestrator` manages the turn-taking and synthesis.
- Documents: `load_documents` ingests files from `data/` and `select_sources` builds citations.
- Observability: `TraceRecorder` writes `trace.jsonl` and `setup_logging` writes `run.log`.
- LLM Clients: `MockLLMClient` for offline runs, `OpenAIClient` for OpenAI, and `AzureFoundryClient` for Azure OpenAI.
- Logs include the LLM provider name and client class at startup.
- Azure Foundry logs auth method plus endpoint, deployment, API version, and temperature on client init.

## Message Schema

Each agent message includes:
- role
- agent_name
- content
- sources[] (filename + snippet)

## Flow

1. User instruction is recorded.
2. Lawyer responds with advocacy grounded in documents.
3. Judge responds with questions and evaluation.
4. Orchestrator synthesizes a recommendation and stores trace artifacts.

See `docs/SEQUENCE.md` for a high-level sequence diagram.
