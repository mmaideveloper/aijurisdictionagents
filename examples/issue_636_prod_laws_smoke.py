"""Run the issue-636 law search locally against a configured PostgreSQL laws database.

The script loads the repository ``.env`` without printing credentials and writes a
privacy-minimized JSON plus HTML report under ``runs/issue-636`` by default.
"""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import sys
import time
from typing import Any, Sequence

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "api" / "aijuristiction-api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app import mcp_api  # noqa: E402
from app.mcp_law_retrieval import build_legal_query_profile  # noqa: E402


DEFAULT_QUERY = "pripare kupno predoajnu zmluvu"


def _collect_index_names(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return _collect_index_names(json.loads(value))
        except json.JSONDecodeError:
            return names
    if isinstance(value, dict):
        index_name = value.get("Index Name")
        if isinstance(index_name, str):
            names.add(index_name)
        for child in value.values():
            names.update(_collect_index_names(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            names.update(_collect_index_names(child))
    return names


def _collect_plan_nodes(value: object) -> list[dict[str, str]]:
    nodes: list[dict[str, str]] = []
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return _collect_plan_nodes(json.loads(value))
        except json.JSONDecodeError:
            return nodes
    if isinstance(value, dict):
        node_type = value.get("Node Type")
        if isinstance(node_type, str):
            node = {"node_type": node_type}
            for source, target in (
                ("Relation Name", "relation"),
                ("Index Name", "index"),
                ("CTE Name", "cte"),
            ):
                field = value.get(source)
                if isinstance(field, str):
                    node[target] = field
            nodes.append(node)
        for child in value.values():
            nodes.extend(_collect_plan_nodes(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            nodes.extend(_collect_plan_nodes(child))
    return nodes


def _query_plan(query: str) -> tuple[list[str], list[dict[str, str]], dict[str, object]]:
    profile = build_legal_query_profile(query)
    captured: list[tuple[str, tuple[object, ...]]] = []

    def capture(sql: str, params: tuple[object, ...]) -> list[Sequence[Any]]:
        captured.append((sql, params))
        return []

    mcp_api._query_provision_candidates(
        laws=mcp_api._LawsQueryConfig(backend="postgres", query_all=capture, param="%s"),
        profile=profile,
        country_code="SK",
        published_year=None,
        law_year=None,
        law_number=None,
        candidate_limit=300,
    )
    sql, params = captured[-1]
    with mcp_api._LawsQuerySession(statement_timeout_ms=30_000) as laws:
        laws.query_all("SELECT set_config('enable_seqscan', 'off', true)", ())
        plan_rows = laws.query_all(f"EXPLAIN (FORMAT JSON) {sql}", params)
        index_rows = laws.query_all(
            """
            SELECT i.indisvalid, i.indisready, pg_get_indexdef(i.indexrelid)
            FROM pg_index AS i
            WHERE i.indexrelid = to_regclass('idx_law_provisions_body_text_fts')
            """,
            (),
        )
    index_health: dict[str, object] = {"present": bool(index_rows)}
    if index_rows:
        index_health.update(
            {
                "valid": bool(index_rows[0][0]),
                "ready": bool(index_rows[0][1]),
                "definition": str(index_rows[0][2]),
            }
        )
    return (
        sorted(_collect_index_names(plan_rows)),
        _collect_plan_nodes(plan_rows),
        index_health,
    )


def _result_summary(result: dict[str, Any]) -> dict[str, object]:
    return {
        "law_identifier": result.get("law_identifier_text"),
        "title": result.get("title"),
        "effective_from": result.get("effective_from"),
        "relevant_sections": result.get("relevant_sections", []),
        "confidence": result.get("confidence"),
        "source_url": result.get("source_url"),
    }


def _render_html(report: dict[str, object]) -> str:
    results = report.get("results", [])
    cards = []
    identifiers: list[str] = []
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            identifiers.append(str(item.get("law_identifier") or ""))
            sections = ", ".join(str(value) for value in item.get("relevant_sections", []))
            source_url = str(item.get("source_url") or "")
            cards.append(
                "<article><h2>"
                + escape(str(item.get("law_identifier") or "Unknown law"))
                + "</h2><p>"
                + escape(str(item.get("title") or ""))
                + "</p><dl><dt>Effective from</dt><dd>"
                + escape(str(item.get("effective_from") or "unknown"))
                + "</dd><dt>Relevant sections</dt><dd>"
                + escape(sections or "none")
                + "</dd><dt>Confidence</dt><dd>"
                + escape(str(item.get("confidence") or "unknown"))
                + "</dd></dl><a href=\""
                + escape(source_url, quote=True)
                + "\">Official source</a></article>"
            )
    expected = [str(value) for value in report.get("expected_laws", [])]
    missing = [
        value for value in expected if not any(identifier.startswith(value) for identifier in identifiers)
    ]
    expected_check = ""
    if expected:
        outcome = "passed" if not missing else "missing: " + ", ".join(missing)
        expected_check = (
            '<p class="ok">Expected-law check: '
            + escape(outcome)
            + " ("
            + escape(", ".join(expected))
            + ")</p>"
        )
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Issue 636 production MCP database smoke test</title>
<style>
body{font:16px/1.45 system-ui;background:#f4f7fb;color:#172033;margin:0;padding:32px}
main{max-width:960px;margin:auto}header,article{background:white;border:1px solid #dbe3ef;border-radius:14px;padding:20px;margin:0 0 16px}
h1{font-size:26px;margin:0 0 12px}h2{margin:0;color:#174ea6}code{background:#eef3fa;padding:3px 6px;border-radius:5px}
.ok{color:#137333;font-weight:700}.meta{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.meta div{background:#eef3fa;padding:12px;border-radius:9px}
dl{display:grid;grid-template-columns:150px 1fr;gap:6px 12px}dt{font-weight:700}dd{margin:0}footer{color:#526274;font-size:13px}
</style></head><body><main><header><h1>Issue #636 — production MCP database smoke test</h1>
<p>Query: <code>""" + escape(str(report["query"])) + """</code></p>
<div class="meta"><div>Status<br><span class="ok">""" + escape(str(report["status"])) + """</span></div>
<div>Duration<br><strong>""" + escape(str(report["duration_ms"])) + """ ms</strong></div>
<div>Result count<br><strong>""" + escape(str(report["result_count"])) + """</strong></div></div>
""" + expected_check + """
<p>Planner indexes: <code>""" + escape(", ".join(report.get("plan_indexes", []))) + """</code></p></header>
""" + "".join(cards) + """<footer>Synthetic query only. Credentials and provision bodies are excluded. Results require human legal review.</footer>
</main></body></html>"""


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--expect-law", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "runs" / "issue-636")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    config = mcp_api._laws_db_config()
    if config.backend != "postgres" or not config.cloud_uri:
        raise SystemExit("A configured PostgreSQL laws database is required; credentials stay redacted.")

    plan_indexes, plan_nodes, fts_index = _query_plan(args.query)
    started = time.perf_counter()
    payload = mcp_api._search_laws(
        query=args.query,
        country_code="SK",
        limit=max(1, min(args.limit, 50)),
        offset=0,
        published_year=None,
        year_filter_mode="published_in",
        law_year=None,
        law_number=None,
        metadata_only=True,
        sort="relevance",
    )
    duration_ms = round((time.perf_counter() - started) * 1_000)
    summarized_results = [_result_summary(item) for item in payload.get("results", [])]
    report: dict[str, object] = {
        "query": args.query,
        "status": payload.get("status"),
        "duration_ms": duration_ms,
        "result_count": len(summarized_results),
        "retrieval_mode": payload.get("retrieval_mode"),
        "query_concepts": payload.get("query_concepts", []),
        "human_review_required": payload.get("human_review_required"),
        "expected_laws": args.expect_law,
        "plan_indexes": plan_indexes,
        "plan_nodes": plan_nodes,
        "fts_index": fts_index,
        "results": summarized_results,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "prod-mcp-db-results.json"
    html_path = args.output_dir / "prod-mcp-db-results.html"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_render_html(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"HTML evidence: {html_path}")

    if payload.get("status") != "ok" or not summarized_results:
        raise SystemExit(1)
    if "idx_law_provisions_body_text_fts" not in plan_indexes:
        raise SystemExit("The production plan did not use the provision full-text GIN index.")
    returned_laws = {str(item.get("law_identifier")) for item in summarized_results}
    missing_laws = sorted(
        expected
        for expected in args.expect_law
        if not any(identifier.startswith(expected) for identifier in returned_laws)
    )
    if missing_laws:
        raise SystemExit("Expected laws missing from bounded results: " + ", ".join(missing_laws))


if __name__ == "__main__":
    main()
