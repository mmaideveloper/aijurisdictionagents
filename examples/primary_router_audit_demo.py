"""Offline synthetic example: python examples/primary_router_audit_demo.py."""

from aijurisdictionagents.correlation import correlation_scope
from aijurisdictionagents.orchestration.primary_router import PrimaryClassification, PrimaryLangGraphRouter


def main() -> None:
    events = []
    with correlation_scope(
        correlation_id="synthetic-router-demo",
        debug_sink=lambda context, component, stage, status, payload: events.append(
            (status, payload)
        ),
    ):
        router = PrimaryLangGraphRouter(classifier=lambda *_: PrimaryClassification(status="no_match"))
        decision = router.route(question="Synthetic general question", verified_facts={}, candidates=[])
    final_status, evidence = events[-1]
    print(f"route={decision.route} status={final_status}")
    print(f"graph={evidence['graph_key']} digest={evidence['topology']['digest']}")
    for occurrence in evidence["occurrences"]:
        print(occurrence["transition_id"])


if __name__ == "__main__":
    main()
