from __future__ import annotations

from app.case_workflows.models import RegisteredGraphResponse


LEGAL_DOCUMENT_GRAPH_VERSION = 2


_LEGAL_DOCUMENT_NODES = (
    "route_case_type",
    "load_flow_pack",
    "retrieve_legal_requirements",
    "verify_input",
    "collect_missing_facts",
    "offer_optional_verification",
    "execute_consented_tools",
    "resolve_conflicts",
    "draft_documents",
    "verify_output",
    "verify_safety_and_gdpr",
    "review_case",
    "finalize_or_escalate",
)

REGISTERED_GRAPHS: tuple[RegisteredGraphResponse, ...] = (
    RegisteredGraphResponse(
        graph_key="legal_document_workflow",
        graph_version=1,
        node_names=_LEGAL_DOCUMENT_NODES,
        supports_interrupt_resume=True,
        supports_automated_finalization=True,
    ),
    RegisteredGraphResponse(
        graph_key="legal_document_workflow",
        graph_version=LEGAL_DOCUMENT_GRAPH_VERSION,
        node_names=_LEGAL_DOCUMENT_NODES,
        supports_interrupt_resume=True,
        supports_automated_finalization=True,
    ),
    RegisteredGraphResponse(
        graph_key="unsupported_or_human_review",
        graph_version=1,
        node_names=("route_case_type", "require_human_review"),
        supports_interrupt_resume=False,
        supports_automated_finalization=False,
    ),
)


def get_registered_graph(graph_key: str, graph_version: int) -> RegisteredGraphResponse | None:
    return next(
        (
            graph
            for graph in REGISTERED_GRAPHS
            if graph.graph_key == graph_key and graph.graph_version == graph_version
        ),
        None,
    )
