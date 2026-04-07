# AIWebSearchAgent

`AIWebSearchAgent` is a lightweight agent that can be used for internet screening support in document workflows.

## Behavior

- Requires user consent before searching (`build_screening_consent_prompt`).
- Supports entity-level screening prompts (person, company, car, etc.).
- Performs a simple web lookup and returns structured records (`title`, `url`, `snippet`).

## Permanent memory model metadata

When API metadata is requested, the system now ensures a permanent-memory key `llm_model_setup` exists with:

- `llm_modelname`
- `cutoff_date`
- `cutoff_source`

This is stored in the API `permanent_memory` table.

## Minimal runnable example

```bash
python examples/ai_web_search_agent_minimal_demo.py
```
