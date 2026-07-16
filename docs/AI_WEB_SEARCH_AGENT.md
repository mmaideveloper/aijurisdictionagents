# EntityScreeningAgent (formerly AIWebSearchAgent)

`EntityScreeningAgent` is a lightweight global screening agent for company/person internet checks.
`AIWebSearchAgent` remains as a backward-compatible alias.

## Behavior

- Requires user consent before searching (`build_screening_consent_prompt`).
- Legal-source fallback for Slovak law/court-decision answer preparation is blocked unless the current turn has explicit user approval for external web search. MCP legal-source retrieval is attempted first, and the frontend/mobile stream shows the backend MCP proof notice before any answer is prepared.
- Supports entity-level screening prompts (person, company, car, etc.).
- Performs a web lookup and returns structured records (`title`, `url`, `snippet`).
- Falls back to DuckDuckGo HTML results when the instant-answer JSON endpoint does not return search hits.
- Can be attached as a **global workflow step** (`global_entity_screening`) for all countries when:
  - user explicitly requests screening, or
  - model suggests screening based on risk/context.
  - workflow engine auto-detects screening intent from question text (e.g., `Over mi jana hraska`).
- Provides structured English prompt templates usable across countries:
  - `CompanySearchAgent.build_search_prompt(...)`
  - `PersonSearchAgent.build_search_prompt(...)`

## Permanent memory model metadata

When API metadata is requested and the current model cutoff is not cached yet, the
system uses `EntityScreeningAgent` (or `AIWebSearchAgent` alias) to discover the current model page and stores a
permanent-memory key `llm_model_setup` with:

- `llm_modelname`
- `cutoff_date`
- `cutoff_source`

This is stored in the API `permanent_memory` table and reused by `/version`.

## Minimal runnable example

```bash
python examples/ai_web_search_agent_minimal_demo.py
```
