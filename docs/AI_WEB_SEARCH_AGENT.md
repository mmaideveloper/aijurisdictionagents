# AIWebSearchAgent

`AIWebSearchAgent` is a lightweight agent that can be used for internet screening support in document workflows.

## Behavior

- Requires user consent before searching (`build_screening_consent_prompt`).
- Supports entity-level screening prompts (person, company, car, etc.).
- Performs a web lookup and returns structured records (`title`, `url`, `snippet`).
- Falls back to DuckDuckGo HTML results when the instant-answer JSON endpoint does not return search hits.

## Permanent memory model metadata

When API metadata is requested and the current model cutoff is not cached yet, the
system uses `AIWebSearchAgent` to discover the current model page and stores a
permanent-memory key `llm_model_setup` with:

- `llm_modelname`
- `cutoff_date`
- `cutoff_source`

This is stored in the API `permanent_memory` table and reused by `/version`.

## Minimal runnable example

```bash
python examples/ai_web_search_agent_minimal_demo.py
```
