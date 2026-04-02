from __future__ import annotations

import sys

from services.laws_collector import SlovLexLiveSnapshotLoader
from services.laws_collector.import_planner import ImportTarget


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    snapshot = SlovLexLiveSnapshotLoader().load_snapshot(
        target=ImportTarget(year=2003, number=461),
        timeout_seconds=12.0,
    )

    print("Law:", f"{snapshot.number}/{snapshot.year}")
    print("Title:", snapshot.official_name)
    if snapshot.metadata is None:
        print("Metadata: missing")
        return
    print("Law identifier:", snapshot.metadata.law_identifier_text)
    print("Type:", snapshot.metadata.law_type)
    print("Approval date:", snapshot.metadata.approval_date or "")
    print("Publication date:", snapshot.metadata.publication_date)
    print("Effective from:", snapshot.metadata.effective_from)
    print("Effective to:", snapshot.metadata.effective_to or "")
    print("Author:", snapshot.metadata.author or "")
    print("Issue reference:", snapshot.metadata.issue_reference or "")
    print("Legal areas:", ", ".join(snapshot.metadata.legal_areas))
    print("Relations:")
    for relation in snapshot.relations:
        print(f" - {relation.relation_type}: {relation.target_law_identifier_text} | {relation.target_title}")


if __name__ == "__main__":
    main()
