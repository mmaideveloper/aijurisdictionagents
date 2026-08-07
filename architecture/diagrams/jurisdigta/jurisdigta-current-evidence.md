# Jurisdigta diagram evidence

| Diagram element or relation | Source | Confidence | Notes |
|---|---|---:|---|
| Lawyer, Judge, and Orchestrator responsibilities | `docs/ARCHITECTURE.md`; `src/aijurisdictionagents/agents.py`; `src/aijurisdictionagents/orchestrator.py` | High | Core legal-agent architecture. |
| React/Vite web application | `frontend/aijurisdictionfronend/package.json`; `infra/bicep/frontend.containerapp.bicep` | High | Implemented client and Azure Container App definition. |
| Flutter mobile application | `mobile_app/pubspec.yaml`; `mobile_app/README.md` | High | Implemented mobile client. |
| FastAPI API with REST and SSE | `docs/API_ARCHITECTURE_RFC.md`; `api/aijuristiction-api/pyproject.toml`; `api/aijuristiction-api/app/main.py` | High | Dedicated API container on port 8080. |
| API-key protected functional routes | `api/aijuristiction-api/app/auth.py`; route modules under `api/aijuristiction-api/app/` | High | Material routes declare `require_api_key`; individual exceptions require endpoint-level review. |
| Azure Container Apps deployment boundary | `infra/bicep/main.bicep`; `infra/bicep/frontend.containerapp.bicep` | High | API/frontend resources and shared managed environment are defined. |
| PostgreSQL and pgvector persistence | `infra/bicep/main.bicep`; `src/aijurisdictionagents/api_db/store.py`; `docs/API_DATABASE_LAYER.md` | High | API and law databases are defined on PostgreSQL Flexible Server; vector extension enabled. |
| Private Azure Blob Storage | `infra/bicep/main.bicep`; `src/aijurisdictionagents/api_db/store.py` | High | Public access disabled; HTTPS-only and TLS 1.2 minimum configured. |
| Document processor job and its storage/data flow | `infra/bicep/document_processor.job.bicep`; `src/services/document_processor/`; `tests/test_document_processor_worker.py` | High | Scheduled worker uses PostgreSQL, Blob Storage, and local/cloud embeddings. |
| Laws collector job and Slov-Lex flow | `infra/bicep/laws_collector.job.bicep`; `docs/LAWS_COLLECTOR_ARCHITECTURE.md`; `src/services/laws_collector/` | High | Scheduled import/enrichment flow is implemented. |
| Email scheduler and SMTP delivery | `infra/bicep/email_scheduler.job.bicep`; `api/aijuristiction-api/app/services/email_scheduler.py`; `infra/README.md` | High | Scheduled job consumes a PostgreSQL-backed outbox and sends via configured transport. |
| Azure OpenAI/Foundry LLM and embedding inference | `src/aijurisdictionagents/llm/azure_foundry_client.py`; `src/aijurisdictionagents/llm/embeddings.py`; `infra/bicep/main.bicep` | High | Azure Foundry is the documented default; embeddings may be local or cloud. |
| External verification sources | `docs/SLOVAK_SCREENING_TOOLS.md`; `docs/SLOVAK_COMPANY_CHECKS.md`; tool modules under `src/aijurisdictionagents/tools/` | Medium | Exact provider/protocol differs by tool and environment, so the view groups them. |
| Application Insights and Log Analytics | `infra/bicep/main.bicep`; `api/aijuristiction-api/app/observability.py`; `infra/README.md` | High | API and worker telemetry integration is documented and implemented. |
| Managed identity access to ACR, Blob Storage, and Log Analytics | `infra/bicep/main.bicep` | High | User-assigned managed identity and RBAC assignments are explicit. |
| Consent, retention, DSAR, transparency, and human-oversight gaps | `docs/GDPR_AI_ACT_COMPLIANCE_REVIEW.md` | High | Review findings are carried into the architecture review, not presented as implemented containers. |

## Assumptions

- The diagrams represent the Azure-oriented current architecture implemented in the repository, not a live inventory of the production subscription.
- Browser and mobile clients use the same public API contract; exact public hostname/DNS routing is intentionally omitted.
- Legal prompts, uploaded documents, messages, and generated documents may contain personal and legally sensitive data; annotations therefore use conservative aggregate classifications.
- The human reviewer is shown at system-context level because repository policy requires human oversight, while the technical enforcement gate remains a documented gap.

## Unresolved questions

- Which conditional Bicep resources and jobs are enabled in the current production environment?
- What are the approved data classifications, legal bases, retention periods, and regional-residency requirements for each data class?
- Which external verification providers are approved processors/subprocessors, and what data is sent to each?
- Is production PostgreSQL reachable only through restricted networking, despite the current `AllowAzureServices` rule?
- What recovery objectives, availability targets, stream concurrency targets, and disaster-recovery controls have been approved?
- Which legal intents require mandatory human approval, and who is authorized to approve them?

## Generated

- State: current
- C4 views: system context and container
- Generated on: 2026-07-22
