"""Bounded source diagnostics and explicit, audited operator dispositions.

Raw reference files and review evidence must stay in restricted ignored storage.
No response bodies, URLs, raw references or reviewer identities are printed.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .config import CourtDecisionCollectorConfig
from .postgres_store import PostgresCourtDecisionStore

INFOSUD_BASE = "https://obcan.justice.sk/pilot/api/ress-isu-service/v1"


def inspect_reference(
    client: httpx.Client, *, source_guid: str, page: int, size: int,
    base_url: str = INFOSUD_BASE,
) -> dict[str, Any]:
    """At most three single requests; absence/404 never proves withdrawal.

    Use a client with finite timeouts, TLS verification and no transport retries.
    Restrict public probes to the known source, without following redirects.
    """
    if base_url.rstrip("/") != INFOSUD_BASE:
        raise ValueError("source review only supports the allowlisted InfoSud endpoint")
    if not source_guid or source_guid != source_guid.strip() or any(
        ord(char) < 32 for char in source_guid
    ) or page < 0 or not 1 <= size <= 100:
        raise ValueError("invalid reference or bounded page parameters")
    result: dict[str, Any] = {
        "reference_hash": sha256(source_guid.encode()).hexdigest()[:16],
        "classification": "unresolved_missing",
        "permanent_unavailability_confirmed": False,
        "requests": 0,
    }

    def get(path: str, params: dict[str, int] | None = None) -> httpx.Response:
        result["requests"] += 1
        return client.get(
            INFOSUD_BASE + path, params=params, timeout=15, follow_redirects=False,
        )

    try:
        detail = get("/rozhodnutie/" + quote(source_guid, safe=":"))
        result["detail_http_status"] = detail.status_code
        if detail.status_code == 200:
            result["classification"] = (
                "detail_available" if detail.json().get("guid") == source_guid
                else "source_contract_mismatch"
            )
            return result
        if detail.status_code not in (404, 410):
            result["classification"] = "source_request_failed"
            return result
        listing = get("/rozhodnutie", {"page": page + 1, "size": size})
        result["listing_http_status"] = listing.status_code
        if listing.status_code != 200:
            result["classification"] = "source_endpoint_unavailable"
            return result
        entries = listing.json().get("rozhodnutieList")
        if not isinstance(entries, list) or any(
            not isinstance(entry, dict) or not isinstance(entry.get("guid"), str)
            or not entry["guid"] for entry in entries
        ):
            result["classification"] = "source_contract_mismatch"
            return result
        result["listed_on_sampled_page"] = any(entry["guid"] == source_guid for entry in entries)
        alternate = next((entry for entry in entries if entry["guid"] != source_guid
                          and source_guid in (entry.get("id"), entry.get("uuid"))), None)
        control = alternate or next((entry for entry in entries if entry["guid"] != source_guid), None)
        if control:
            response = get("/rozhodnutie/" + quote(control["guid"], safe=":"))
            result["control_http_status"] = response.status_code
            control_valid = response.status_code == 200 and response.json().get("guid") == control["guid"]
            result["control_identity_verified"] = control_valid
            if alternate and control_valid:
                result["classification"] = "identifier_mismatch_verified"
            elif not control_valid:
                result["classification"] = "source_endpoint_unconfirmed"
        return result
    except (httpx.RequestError, ValueError, TypeError, AttributeError) as exc:
        result["classification"] = "probe_incomplete"
        result["error_type"] = type(exc).__name__
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "quarantine", "requeue"))
    parser.add_argument("--reference-file", type=Path, required=True,
                        help="Restricted JSON file with source_guid, page (zero-based), size.")
    parser.add_argument("--evidence-category", choices=("source_withdrawal",
                        "operator_verified_unavailable", "operator_requeue", "verified_source_change"))
    parser.add_argument("--evidence-sha256")
    parser.add_argument("--reviewer-sha256")
    parser.add_argument("--confirm-permanent-unavailability", action="store_true",
                        help="Human has verified withdrawal, correct identity and working source.")
    args = parser.parse_args()
    try:
        reference = json.loads(args.reference_file.read_text(encoding="utf-8-sig"))
        guid = reference["source_guid"]
        if not isinstance(guid, str) or not guid:
            raise ValueError("invalid reference")
        config = CourtDecisionCollectorConfig.from_env()
        if args.action == "inspect":
            with httpx.Client(verify=True, transport=httpx.HTTPTransport(retries=0)) as client:
                result = inspect_reference(client, source_guid=guid,
                                           page=int(reference["page"]), size=int(reference["size"]),
                                           base_url=config.source_base_url)
        else:
            if args.action == "quarantine" and not args.confirm_permanent_unavailability:
                parser.error("quarantine requires --confirm-permanent-unavailability after human review")
            if not all((args.evidence_category, args.evidence_sha256, args.reviewer_sha256)):
                parser.error("review requires evidence category, evidence digest and reviewer digest")
            config.validate()
            store = PostgresCourtDecisionStore.from_config(config)
            # Apply migration 0006 before using this command. Never silently
            # initialize/migrate a production database during an operator action.
            changed = store.review_work_availability(
                source_system="infosud", source_guid=guid,
                unavailable=args.action == "quarantine", evidence_category=args.evidence_category,
                evidence_sha256=args.evidence_sha256, reviewer_sha256=args.reviewer_sha256,
            )
            result = {"reference_hash": sha256(guid.encode()).hexdigest()[:16],
                      "action": args.action, "changed": changed}
        print(json.dumps(result, sort_keys=True))
    except Exception as exc:
        # Even database/HTTP exceptions may contain connection strings or GUIDs.
        print(json.dumps({"error_type": type(exc).__name__, "action": args.action}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
