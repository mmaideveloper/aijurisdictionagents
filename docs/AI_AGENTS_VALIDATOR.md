# AIAgentsValidator

`AIAgentsValidator` evaluates conversation artifacts (for example Playwright chat simulator output) and produces a weighted accuracy score.

## Inputs

- communication payload (`qaPairs` or `messages`)
- `ValidatorInputs`:
  - `country`
  - `question`
  - `expected_points` (legal anchors you expect the system to cover)
- final result text from the core system

## Scoring criteria

Default weighted criteria:

- `legal_accuracy` (45%)
- `coverage` (30%)
- `clarity` (15%)
- `risk_awareness` (10%)

The output is a `ValidationReport` with:

- `weighted_accuracy` (0-100)
- per-criterion scores and rationale
- summary sentence

## Model choice guidance for legal evaluation

Default behavior is deterministic heuristic scoring (good for CI regression trends).

For deeper legal quality review, pass a production LLM client (OpenAI/Azure Foundry) to `AIAgentsValidator(llm=...)` and use model-assisted scoring. Suggested profile:

- model family with strong reasoning and instruction-following
- low temperature (0.0-0.2)
- strict JSON schema parsing and fallback to heuristic scores

## Minimal runnable example

```bash
python examples/validator_demo.py
```
