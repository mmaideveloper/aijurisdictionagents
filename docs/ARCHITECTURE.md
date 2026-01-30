# Architecture

## Components

- Agents: `Lawyer` advocates for the user and `Judge` evaluates and asks clarifying questions.
- Orchestration: `Orchestrator` manages the turn-taking and synthesis.
- Documents: `load_documents` ingests files from `data/` and `select_sources` builds citations.
- Cases: `CaseStore` persists Slovak advice cases to `cases/` (case.json, documents, discussion logs).
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

1. User instruction and case context (country + output language preference) are recorded.
2. Lawyer responds with advocacy grounded in documents (if provided) and the target jurisdiction.
3. Judge responds with questions and evaluation in the user's language (no direct document access).
4. If either agent asks a question, the user is prompted (up to 5 minutes by default, or the remaining discussion time). A timeout is recorded as "User could not answer within X minutes."
5. For `advice` mode, the user can optionally request judge review.
6. For `court` mode, the judge must approve/reject the lawyer's response; rejection triggers another lawyer attempt.
7. After each round, the user is prompted for additional questions (type "finish" to end).
8. Discussion continues while follow-up questions are provided, or until the max discussion time is reached (default 15 minutes, 0 = unlimited).
9. Orchestrator synthesizes a final recommendation and rationale in the requested output language and stores trace artifacts.
10. For Slovak advice runs, the CLI persists a case folder under `cases/` with documents and discussion logs.

See `docs/SEQUENCE.md` for a high-level sequence diagram.
