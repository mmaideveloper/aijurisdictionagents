"""Privacy-minimized serialization of executable LangGraph definitions."""

from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any, Mapping


GRAPH_EVIDENCE_SCHEMA_VERSION = 1
_SAFE_GRAPH_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:@+-]{0,199}$")


def serialize_compiled_graph(
    graph: Any, *, graph_key: str, graph_version: int
) -> dict[str, Any]:
    """Return a deterministic allowlisted snapshot from the compiled graph itself."""

    raw = graph.get_graph().to_json()
    nodes = [
        {"id": _safe_id(str(item.get("id", ""))), "label": _label(str(item.get("id", "")))}
        for item in raw.get("nodes", [])
        if isinstance(item, Mapping) and _is_safe_id(str(item.get("id", "")))
    ]
    known_nodes = {item["id"] for item in nodes}
    edges: list[dict[str, Any]] = []
    for raw_edge in raw.get("edges", []):
        if not isinstance(raw_edge, Mapping):
            continue
        source = str(raw_edge.get("source", ""))
        target = str(raw_edge.get("target", ""))
        if source not in known_nodes or target not in known_nodes:
            continue
        branch = str(raw_edge.get("data", ""))[:100] if raw_edge.get("conditional") else ""
        edge_id = _edge_id(source, target, branch)
        edges.append(
            {
                "id": edge_id,
                "source": source,
                "target": target,
                "conditional": bool(raw_edge.get("conditional", False)),
                "branch": branch,
            }
        )
    definition: dict[str, Any] = {
        "schema_version": GRAPH_EVIDENCE_SCHEMA_VERSION,
        "graph_key": _safe_id(graph_key),
        "graph_version": graph_version,
        "nodes": nodes,
        "edges": sorted(edges, key=lambda item: item["id"]),
    }
    canonical = json.dumps(definition, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    definition["digest_algorithm"] = "sha256"
    definition["digest"] = sha256(canonical.encode("utf-8")).hexdigest()
    return definition


def transition_id(
    topology: Mapping[str, Any], *, source: str, target: str
) -> str:
    """Resolve a persisted transition identity only when the topology is unambiguous."""

    matches = [
        str(edge.get("id", ""))
        for edge in topology.get("edges", [])
        if isinstance(edge, Mapping)
        and edge.get("source") == source
        and edge.get("target") == target
    ]
    return matches[0] if len(matches) == 1 else ""


def _edge_id(source: str, target: str, branch: str) -> str:
    suffix = f":{branch}" if branch else ""
    return f"{source}->{target}{suffix}"


def _is_safe_id(value: str) -> bool:
    return bool(_SAFE_GRAPH_ID.fullmatch(value))


def _safe_id(value: str) -> str:
    if not _is_safe_id(value):
        raise ValueError("Graph definition contains an unsafe identifier")
    return value


def _label(value: str) -> str:
    if value == "__start__":
        return "Start"
    if value == "__end__":
        return "End"
    return value.replace("_", " ").strip().title()[:200]
