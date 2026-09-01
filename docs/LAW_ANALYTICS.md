# MCP-first Slovak law analytics

JurisDigta answers simple analytical law questions with deterministic MCP calculations rather
than model-generated counts. `rankLawsByAmendments` ranks laws published in a selected year by
distinct imported amending acts in an amendment year. `getLawHistory` returns the imported
versions and relations used to explain a ranking.

Example question:

> What is the most incorrect recent law with most amendments from 2025?

The chat API treats “most incorrect” only as the disclosed proxy “most frequently amended.” It
returns the metric, candidate year, amendment year, amendment count, separate stored-version
count, source citation, corpus limitation, and human-review warning. Frequent amendment does not
prove that legislation is wrong, invalid, or low quality.

Simple rankings use the direct chat → MCP → laws database path. LangGraph remains appropriate
only when a later analytical request needs clarification or multiple dependent operations; graph
nodes must consume the same MCP evidence and must never calculate or invent counts.

## MCP calls

```json
{
  "name": "rankLawsByAmendments",
  "arguments": {
    "country_code": "SK",
    "published_year": 2025,
    "amendment_year": 2025,
    "limit": 5
  }
}
```

Counts include only imported `amends` relations. `coverage.complete=false` is deliberate until
the collector can prove complete source coverage for the requested period. Consumers must show
that limitation and require human review for legal reliance.

Run the focused example against the configured local laws database:

```powershell
python examples/law_analytics_demo.py --year 2025
```

The real E2E acceptance path uses synthetic 2025 law and amendment records in local PostgreSQL,
compares direct MCP output with the frontend answer, and stores its sanitized screenshot and
manifest under `runs/e2e/issue-721-law-analytics/`.
