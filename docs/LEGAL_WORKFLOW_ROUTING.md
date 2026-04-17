# Legal Workflow Routing (Slovakia-first, multi-country ready)

This module introduces a lightweight workflow engine for client legal questions.

## Goals

- Classify client questions into reusable legal process groups.
- Select a country-specific workflow blueprint.
- Validate required inputs before tool execution.
- Fall back to a generic clarification mode when no workflow is a safe match.

## Core components

- `WorkflowBlueprint`: process definition for a case type (keywords, required fields, and **mandatory system documents only**).
- `WorkflowStep`: explicit ordered steps within the workflow (each step can have a tool and step-specific inputs/outputs).
- `WorkflowRegistry`: stores available workflows by country.
- `WorkflowRouter`: scores intent + input coverage and selects the best candidate.
- `WorkflowEngine`: validates inputs and returns either
  - `mode=workflow` with missing fields and validation issues, or
  - `mode=fallback` with clarification prompts.
  - `required_documents` that merge:
    - `mandatory_system_documents` from blueprint, and
    - additional law-driven documents from laws connectors / legal updates (`law_required_documents`).
  - global optional step `global_entity_screening` with consent prompt when screening is requested/suggested.
  - automatic screening intent detection from question text (e.g., Slovak request `Over mi jana hraska`).
  - structured screening task prompt (`screening_task_prompt`) with company/person template in English for cross-country use.

## Built-in Slovakia examples

- `sk.company.add_co_owner.v1`: add co-owner/shareholder workflow where ORSR verification is the **first step**, followed by constraints checks and document bundle generation.
- The blueprint stores only stable mandatory system documents (`decision_of_general_meeting`, `general_meeting_minutes`).
- Any new legal requirement introduced by law updates is appended dynamically via `law_required_documents`.
- `sk.company.verify_orsr.v1`: standalone company verification workflow for verification-only requests.

## Testing different workflows and case variants

Use a matrix approach:

1. **Workflow routing tests** – verify that different intents select different workflows (`add_co_owner` vs `verify_orsr`).
2. **Missing input tests** – for each workflow verify generated clarification questions for absent required fields.
3. **Validation tests** – invalid identifiers/formats (e.g., invalid IČO).
4. **Law-change tests** – inject `law_required_documents` and verify required document merge behavior.
5. **Conflict resolution tests** – compare user input with external registry facts and verify confirmation questions are generated.
6. **Global screening tests** – verify `global_entity_screening` is included for user-requested or model-suggested screening.
7. **Natural language screening intent tests** – verify Slovak phrasing auto-triggers screening and extracts entity.

Example conflict case:

- Workflow: `sk.company.add_co_owner.v1`
- User input: `current_owner_name=Peter Novak`
- ORSR fact: `current_owner_name=Martin Novak`
- Expected behavior: add a clarification/confirmation question asking which value is legally valid before continuing.

## Testing strategy

The test suite covers:

1. Workflow selection for add-co-owner intent.
2. Required-input gap detection and clarification prompts.
3. Input validation (e.g., Slovak company ID format).
4. Dynamic merge of mandatory + law-required documents.
5. Fact conflict detection and user confirmation prompt generation.
6. Global screening step injection and consent prompt generation.
7. Natural language screening intent detection.
8. Fallback behavior when no workflow satisfies confidence threshold.

## Minimal demo

Run:

```bash
python examples/minimal_demo.py
```

The minimal demo now includes workflow routing examples alongside the existing end-to-end contract simulations.
