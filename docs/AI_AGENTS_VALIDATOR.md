# AIAgentsValidator

`AIAgentsValidator` evaluates conversation artifacts (for example Playwright chat simulator output) and produces a weighted accuracy score.

## Inputs

- communication payload (`qaPairs` or `messages`)
- `ValidatorInputs`:
  - `country`
  - `question`
  - `expected_points` (legal anchors you expect the system to cover)
- final result text from the core system
- optional `final_contract` text
- optional `reference_contracts` (public template excerpts for comparison)

## Scoring criteria

Default weighted criteria:

- `legal_accuracy` (30%)
- `coverage` (20%)
- `clarity` (10%)
- `risk_awareness` (10%)
- `human_likeness` (15%)
- `contract_alignment` (15%)

The output is a `ValidationReport` with:

- `weighted_accuracy` (0-100)
- `human_likeness` (0-100)
- `contract_similarity` (0-100)
- per-criterion scores and rationale
- summary sentence

## Model choice guidance for legal evaluation

Default behavior is deterministic heuristic scoring (good for CI regression trends).

For deeper legal quality review, pass a production LLM client (OpenAI/Azure Foundry) to `AIAgentsValidator(llm=...)` and use model-assisted scoring. Suggested profile:

- model family with strong reasoning and instruction-following
- low temperature (0.0-0.2)
- strict JSON schema parsing and fallback to heuristic scores

## Minimal runnable examples

```bash
python examples/validator_demo.py
python examples/slovakia_rental_10min_validation_demo.py
```
