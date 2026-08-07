# ADR-0002: Route Each Legal Task by Cost per Verified Legal Answer

## Status

Accepted

## Date

2026-08-06

## Context

JurisDigta can use local Ollama models and external models provided through Azure AI Foundry or other approved providers. A single legal case can contain multiple user questions, and one question can require materially different operations, such as:

- extracting facts and personal data from the conversation or uploaded documents;
- retrieving current legislation and case law;
- drafting a legal document;
- providing legal advice about the document;
- validating legal claims and citations; and
- rendering a user-confirmed document.

Selecting one model for an entire case, or even one model for an entire question, unnecessarily sends data to external providers, can use an expensive model for simple extraction, and does not account for different model strengths. Selecting only by token price is also misleading: a cheap answer that contains a legal error, fabricated citation, or requires a retry or human correction can cost more than a higher-priced answer that passes verification on the first attempt.

The business optimization metric is therefore **cost per verified legal answer (CPVLA)**, not price per token:

```text
CPVLA =
    total inference, retrieval, verification, retry, escalation,
    rendering, and attributable human-review cost
    / number of accepted legal answers
```

An accepted answer is the complete user-visible outcome after all required stages have passed. The denominator must use the measured joint pass count; separate legal-accuracy and citation-pass rates must not be multiplied as if they were independent.

The existing model usage ledger already records request-level provider, model, route, token counts, estimated cost, case, session, question, and answer identifiers. This provides the base for question-level provenance without duplicating prompts or sensitive legal content.

## Decision

### 1. Route task stages, not whole cases

A case may use multiple providers and models. A question may also use multiple models when it contains multiple task stages.

The backend orchestrator, rather than the browser or an unconstrained LLM, decomposes a question into approved task types and selects an eligible model profile for each stage. Initial task types include:

- `fact_extraction`;
- `data_minimization`;
- `legal_retrieval`;
- `document_drafting`;
- `legal_advice`;
- `citation_verification`;
- `legal_review`; and
- `document_rendering`.

Retrieval and rendering do not have to call an LLM. Deterministic services are preferred when they can perform the task reliably.

Model eligibility is evaluated per **model profile and task type**. Passing an extraction evaluation does not authorize the same model to provide production legal advice.

### 2. Optimize only among models that pass hard gates

For each task type and legal-risk class, routing selects the eligible model or cascade with the lowest measured CPVLA. Token price alone must not determine production routing.

A production legal answer must fail closed or move to human review when any mandatory gate fails. Mandatory gates include:

- correct jurisdiction and decision date;
- no fabricated statute, judgment, identifier, quotation, or citation;
- every material legal claim is supported by retrieved evidence;
- cited evidence exists, is current for the decision date, and entails the claim;
- authoritative sources are preferred over secondary sources;
- facts, legal interpretation, uncertainty, and assumptions are distinguishable;
- missing facts are requested or disclosed rather than invented;
- required external-provider acknowledgement and data-zone policy are satisfied; and
- high-risk output receives the configured human oversight.

One fabricated material citation is an automatic failure. A weighted score cannot compensate for it.

CPVLA includes failed attempts, retries, fallback calls, citation checks, escalation calls, and attributable human review. Price and evaluation results are time-versioned because provider prices and model behavior change.

### 3. Prefer a governed cascade

The default strategy is a cost-aware cascade:

1. Keep raw personal data local when a validated local model or deterministic parser can perform extraction and minimization.
2. Retrieve law and case-law evidence through the governed JurisDigta MCP and document stores.
3. Use the lowest-cost eligible drafting or advice model.
4. Verify source existence, temporal validity, and claim support.
5. Escalate to a stronger eligible model when verification fails, the question is complex, or confidence is insufficient.
6. Require human review for configured high-risk outcomes.
7. Merge personal data into a generated document locally when placeholders can avoid disclosing those data to an external model.

The cascade is configured through task route policies and model profiles. Exact model versions are configuration and evaluation data, not permanent business logic.

### 4. Example: loan repayment confirmation

For the user question:

> Chcem pripraviť dokument pre potvrdenie splatenia pôžičky a právnu radu, ako ho podpísať.

an eligible route can be:

1. **Local Ollama `qwen3:4b` — fact extraction and minimization.** Extract lender, borrower, agreement date, amount, repayment date, payment method, and missing facts. Keep raw identifiers local and create placeholders for external drafting where practical.
2. **JurisDigta MCP — legal retrieval.** Retrieve current Slovak legal sources relevant to repayment, acknowledgement, discharge, evidence, signatures, and any applicable form requirements. Retrieval is not delegated to model memory.
3. **Azure AI Foundry GPT-5.4 mini — document drafting.** Draft the confirmation from minimized structured facts and retrieved legal context. The user must confirm the drafting step and review the populated document.
4. **Azure AI Foundry GPT-5.5 — legal advice and review.** Explain signing options, evidentiary considerations, remaining risks, and when professional review is appropriate, with citations to the supplied evidence.
5. **Citation verifier — deterministic checks plus an independently evaluated reviewer when required.** Confirm that identifiers resolve, sources were effective on the relevant date, and each material claim is entailed by its citation.
6. **Local renderer — final assembly.** Insert locally held personal fields and generate the confirmed DOCX/PDF without sending those fields back to an external provider when avoidable.

This chain is illustrative. GPT-5.4 mini, GPT-5.5, or `qwen3:4b` remains eligible only while its task-specific evaluation satisfies the required quality, privacy, latency, and CPVLA thresholds. A simpler question can use one model; an unresolved or high-risk question can use additional verification and human review.

### 5. Record model provenance for every question and stage

Every model call is appended to the existing usage ledger and linked to:

- case, session, user question, and resulting answer;
- task stage and task type;
- provider and immutable model/deployment snapshot where available;
- route policy and reason for selection or escalation;
- local, external, regional, or EU Data Zone route classification;
- input, cached-input, output, and total tokens;
- provider-currency and EUR cost estimate;
- status, retry, fallback, and parent-stage correlation;
- evaluation/verification outcome identifiers; and
- timestamps and correlation identifiers.

The audit record stores bounded metadata and hashes, not duplicated prompts, full answers, source bodies, hidden reasoning, personal data, or provider secrets.

The user-facing case history shows the primary model for each assistant answer. An expandable provenance view shows all contributing stages and models, for example:

```text
Question 12
  fact_extraction       local_ollama / qwen3:4b
  document_drafting     azure_foundry / gpt-5.4-mini
  legal_advice          azure_foundry / gpt-5.5
  citation_verification deterministic + reviewer profile
```

Administrators can view costs, routing reasons, failures, and verification status. Users do not receive hidden chain-of-thought, internal prompts, secrets, or sensitive operational metadata.

### 6. Evaluate end-to-end outcomes

Promotion requires a versioned evaluation set representing Slovak and EU legal work, including:

- statutory questions and temporal validity;
- questions requiring multiple legal sources;
- procedural deadlines;
- contract and document analysis;
- document drafting;
- incomplete and contradictory facts;
- cases where the safe result is uncertainty or human escalation; and
- adversarial requests containing non-existent laws or decisions.

Gold expectations contain jurisdiction, decision date, acceptable conclusions, authoritative sources, required points, and critical failure conditions. Legal experts approve the gold set and blindly review a representative sample. LLM judges may assist with screening but cannot be the sole authority for legal correctness or citation validity.

Model-only tests use the same evidence pack to compare generation capability. The primary production metric is an end-to-end route evaluation that includes retrieval, orchestration, retries, verification, and human-review cost.

Production promotion additionally requires a statistically meaningful sample, recorded uncertainty, latency and availability limits, privacy eligibility, and a rollback route. If no candidate passes the hard gates, cost optimization is not performed and the task fails closed or is sent to human review.

### 7. Apply privacy, transparency, and human-oversight controls

Routing follows data minimization and purpose limitation:

- synthetic or anonymized cases are used when testing providers without approved production data terms;
- raw case data stays local unless the selected external route is necessary and authorized;
- external processing requires the configured acknowledgement and provider agreement;
- personal data sent externally is minimized or pseudonymized where practical;
- production legal routes that require EU processing use an eligible EU Data Zone or regional profile;
- retention and deletion follow the parent case lifecycle;
- users can see that AI models contributed and which primary model produced an answer; and
- consequential or high-risk legal outputs retain meaningful human oversight.

The system must not claim that an LLM is a lawyer, guarantee a legal outcome, or hide uncertainty behind an aggregate score.

## Alternatives considered

### One model per case

Rejected because a case can contain unrelated tasks with different risk, privacy, and capability requirements. It also makes inexpensive local preprocessing and selective escalation impossible.

### One model per user question

Rejected as the general rule because one question can request both document creation and legal advice. It remains valid when a single eligible model can complete and verify the whole outcome at the lowest measured CPVLA.

### Always use the strongest model

Rejected because it unnecessarily increases cost and external data disclosure for deterministic or low-risk operations.

### Always start with the cheapest model

Rejected because repeated failures, weak citations, and escalation can make the complete outcome more expensive and less safe.

### Let users or an LLM freely select providers

Rejected as the production authority. Users can express preferences when permitted, but the backend must enforce task eligibility, consent, budgets, data-zone restrictions, evaluation status, and human-review requirements.

## Consequences

### Positive

- Cost is measured against accepted legal outcomes instead of raw tokens.
- Personal data can remain local during extraction and final document population.
- Strong models are reserved for stages where they measurably improve the result.
- Every answer has question-level and stage-level provider/model provenance.
- Model or price changes can be handled through evaluation and configuration rather than hard-coded chains.
- GDPR, EU AI Act transparency, auditability, and human oversight are incorporated into routing.

### Negative

- Multi-stage routes add latency and orchestration complexity.
- Citation verification and legal gold-set maintenance require ongoing expert work.
- Cost accounting must attribute non-LLM retrieval, retries, verification, and human review.
- Provider and model eligibility must be re-evaluated after material model, prompt, retrieval, or pricing changes.
- User interfaces need a concise provenance summary without exposing sensitive internals.

## Implementation guidance

1. Extend task route policies so eligibility and CPVLA statistics are scoped by task type and legal-risk class.
2. Add stage and parent-stage correlation metadata to the existing usage ledger instead of introducing a second model-call ledger.
3. Store versioned evaluation runs, hard-gate failures, accepted outcomes, and CPVLA aggregates without copying case content into analytics tables.
4. Add an orchestrator task plan with deterministic data minimization, retrieval, verification, escalation, and fail-closed behavior.
5. Show the primary answer model and expandable stage provenance in case history and administrator audit views.
6. Start with the existing model-routing example and extend it when this ADR is implemented:

   ```powershell
   python examples/model_routing_minimal_demo.py
   ```

7. Roll out in shadow evaluation before enabling automatic multi-model production routing.

## Follow-up actions

- Create a separate implementation task for the task-stage schema and usage-ledger extension.
- Create a separate implementation task for the CPVLA evaluation store and benchmark runner.
- Create a separate implementation task for orchestrator decomposition, verification, and escalation.
- Create a separate frontend task for per-answer and per-stage model provenance.
- Define the initial lawyer-reviewed Slovak/EU gold evaluation set and promotion thresholds.
- Record provider DPA, retention, regional processing, and EU Data Zone eligibility before enabling production case data.
