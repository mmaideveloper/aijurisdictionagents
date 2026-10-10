"""Metadata-only causal projection of retained diagnostic events.

Timestamps order observations, but never establish causality. Request IDs group
observations; only recorded, unambiguous parent IDs establish operation edges.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence


def build_causal_flow(
    events: Sequence[Mapping[str, Any]], *, truncated: bool = False,
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    unlinked: list[str] = []
    for event in events:
        request_id = str(event.get("request_id") or "")
        if request_id:
            grouped[request_id].append(event)
        else:
            unlinked.append(str(event.get("event_id") or ""))

    nodes: list[dict[str, Any]] = []
    parents: dict[str, str] = {}
    gaps: set[str] = set()
    if truncated:
        gaps.add("event_page_truncated")
    if unlinked:
        gaps.add("request_id_not_recorded")
    for request_id, rows in grouped.items():
        parent_ids = {str(row.get("parent_request_id") or "") for row in rows}
        session_ids = {str(row.get("session_id")) for row in rows if row.get("session_id")}
        row_gaps: list[str] = []
        parent = next(iter(parent_ids)) if len(parent_ids) == 1 else ""
        if len(parent_ids) > 1 or len(session_ids) > 1:
            row_gaps.append("ambiguous_request_identity")
            parent = ""
        elif parent == request_id:
            row_gaps.append("self_parent")
            parent = ""
        elif parent and parent not in grouped:
            row_gaps.append("parent_not_recorded")
        elif parent:
            parents[request_id] = parent
        labels = list(dict.fromkeys(
            f"{row.get('component', 'unknown')}:{row.get('stage', 'unknown')}" for row in rows
        ))
        nodes.append({
            "id": request_id, "label": " / ".join(labels),
            "parent_link_source": "none" if not parent else "request_header_unverified" if any(
                row.get("component") == "api" and row.get("stage") == "http_request"
                for row in rows
            ) else "runtime",
            "parent_request_id": parent,
            "session_ids": sorted(session_ids),
            "observations": [{
                "event_id": str(row.get("event_id") or ""),
                "created_at": str(row.get("created_at") or ""),
                "component": str(row.get("component") or ""),
                "stage": str(row.get("stage") or ""),
                "status": str(row.get("status") or ""),
            } for row in rows],
            "evidence_gaps": row_gaps,
        })
        gaps.update(row_gaps)

    # Suppress ambiguous ancestry and cycles instead of inventing a root turn.
    ambiguous = {node["id"] for node in nodes if "ambiguous_request_identity" in node["evidence_gaps"]}
    for child, parent in list(parents.items()):
        if parent in ambiguous:
            del parents[child]
            gaps.add("ambiguous_parent_identity")
    cyclic: set[str] = set()
    for start in parents:
        path: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current in parents and current not in positions:
            positions[current] = len(path)
            path.append(current)
            current = parents[current]
        if current in positions:
            cyclic.update(path[positions[current]:])
    for node_id in cyclic:
        parents.pop(node_id, None)
    if cyclic:
        gaps.add("cyclic_parent_links")
    unresolved = {node["id"] for node in nodes if node["evidence_gaps"]} | cyclic
    unresolved.update(node["id"] for node in nodes if node["parent_request_id"] in ambiguous)
    for node in nodes:
        current = node["id"]
        while current in parents:
            current = parents[current]
        node["root_request_id"] = None if current in unresolved else current
        if node["id"] in cyclic:
            node["evidence_gaps"].append("cyclic_parent_links")
    return {
        "schema_version": 1,
        "edge_basis": "recorded_parent_request_id",
        "nodes": nodes,
        "edges": [{"from": parent, "to": child} for child, parent in parents.items()],
        "unlinked_event_ids": unlinked,
        "completeness": "partial" if gaps else "recorded_evidence_only",
        "evidence_gaps": sorted(gaps),
    }
