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
- Project Polling: `scripts/project_poll.py` snapshots Project V2 items across configured projects; `scripts/project_requirements_review.py` flags issues missing the `codex - business requirements reviewed` marker and can patch missing requirement sections; `scripts/project_in_review.py` moves Ready tasks with PRs to In review.
- Lifecycle Automation: local lifecycle pipeline code remains under `aijurisdictionagents.lifecycle` and supporting scripts/docs are used for Ready -> In progress -> PR -> In review flow.

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
5. For `advice` mode, the lawyer runs the consultation without a judge.
6. For `court` mode, the judge must approve/reject the lawyer's response; rejection triggers another lawyer attempt.
7. After each round, the user is prompted for additional questions (type "finish" to end).
8. Discussion continues while follow-up questions are provided, or until the max discussion time is reached (default 15 minutes, 0 = unlimited).
9. Orchestrator synthesizes a final recommendation and rationale in the requested output language and stores trace artifacts.
10. For Slovak advice runs, the CLI persists a case folder under `cases/` with documents and discussion logs.

## API document-task planning

The API chat reply flow can add policy-driven task-planning guidance for uploaded-document requests before sending the prompt to the lawyer agent.
Case-backed chat memory relies on persisted `uploaded`, `chat_attachment`, and `session_history` documents being available to the active document-processing path so later sessions can retrieve earlier inline uploads and refreshed transcript snapshots.

- Mixed requests such as "review/update uploaded document and summarize it" are converted into an ordered internal task plan.
- The task order follows the user message order.
- A policy layer maps matched intents to ordered tasks plus communication rules while keeping a single legal agent/persona.
- The intent-policy feature is implemented in a dedicated chat service module so the API router can stay focused on endpoint mapping and auth wiring.
- For modernization requests, the plan explicitly instructs the model to review the uploaded document first, then update it under current law, and only then prepare any requested summary.
- Policies can also defer content-specific steps when uploaded documents are still unprocessed, instead of forcing the agent to improvise around missing evidence.
- This planning layer is separate from developer/runtime Codex skills; it is application orchestration logic used to keep user-facing communication aligned with the requested task and make future policies/tasks easier to add.

## Slovak law flow build rules (default for new legal flows)

To scale Slovak legal operations with minimal hardcoded logic, new law flows should follow a hybrid pattern:

- Keep system logic minimal and deterministic:
  - flow state transitions (`intake -> missing_info -> draft -> validate -> finalize`);
  - required-field gates and tool permissions;
  - audit trail, confidence flags, and escalation hooks.
- Keep legal reasoning model-driven:
  - legal interpretation;
  - question generation and follow-up;
  - first-draft and update text generation;
  - explanation of risks and alternatives.
- Keep jurisdiction handling tool-driven:
  - retrieve up-to-date Slovak law text and effective dates;
  - validate generated/updated documents against rule checks;
  - produce document packages from templates and known requirements.

Each new Slovak legal act (for example owner addition, `konateľ` change, company address change) should be represented as configuration data ("flow pack"), not bespoke orchestration code. A flow pack should include:

- required facts;
- required documents and evidence;
- validation rules and blocking conditions;
- output documents;
- follow-up question strategy.

### Proactive behavior requirement for `AILawyerAgent`

For every Slovak legal flow, the agent must proactively:

- ask for missing mandatory information before finalization;
- highlight contradictory or risky data and propose the safest next action;
- suggest better alternatives when available;
- identify missing documents needed for filing;
- request clarification or human-lawyer review when confidence is low.

### Minimal runnable example

Use the repository default minimal demo command for smoke checks:

`python examples/minimal_demo.py`

See `docs/SEQUENCE.md` for a high-level sequence diagram.

## Durable case orchestration

Every normal chat question first enters a typed primary LangGraph router. It classifies only against
active dedicated assignments backed by enabled, published immutable flow packs, using the current
question and verified facts. High-confidence matches enter the pinned case graph, low-confidence or
ambiguous matches ask for clarification, and no match delegates to the generic LangGraph route.
Guided cases use persisted checkpoints, sanitized ordered events, and independent
input/output/privacy/final-review gates. JurisDigta MCP supplies current legal requirements. Graph v2 verifies required facts
before retrieval and constructs a bounded query only from reviewed immutable policy terms plus
allowlisted verified-fact aliases; raw personal facts and unrestricted model-generated queries are
excluded. The legacy orchestrator remains
available as a fail-closed rollout fallback. See `docs/LANGGRAPH_CASE_ORCHESTRATION.md` and
`docs/ADR-635-LANGGRAPH-CASE-ORCHESTRATION.md`.
