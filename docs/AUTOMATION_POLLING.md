# Project Polling Automation

This repository uses a scheduled polling workflow to drive Project V2 automation (GitHub Actions has no native
"project status changed" trigger).

## Workflow

- File: `.github/workflows/project_polling.yml`
- Triggers: `schedule` (default: every 15 minutes) and `workflow_dispatch`
- Purpose: fetch Project V2 items and write snapshot JSON files for downstream automation steps

## Configuration

Config file: `.github/automation.yml` (JSON content, YAML-compatible).

```json
{
  "projects": [
    {
      "name": "core",
      "owner": "mmaideveloper",
      "repo": "mmaideveloper/aijurisdictionagents",
      "project_number": 5,
      "status_field": "Status",
      "selection_strategy": "oldest_ready",
      "labels": {
        "selected": "auto:selected",
        "in_review": "auto:in-review",
        "tested": "auto:tested",
        "merged": "auto:merged"
      }
    },
    {
      "name": "frontend",
      "owner": "mmaideveloper",
      "repo": "mmaideveloper/aijurisdictionagents",
      "project_number": 6,
      "status_field": "Status",
      "selection_strategy": "oldest_ready",
      "labels": {
        "selected": "auto:selected",
        "in_review": "auto:in-review",
        "tested": "auto:tested",
        "merged": "auto:merged"
      }
    }
  ]
}
```

## Secrets

For Project V2 read/write access, prefer a PAT stored as `GH_PROJECT_TOKEN` with scopes:

- `read:project`
- `project`

The workflow uses `GH_PROJECT_TOKEN` when set, otherwise falls back to `GITHUB_TOKEN`.

## Local usage

```bash
python scripts/project_poll.py --config .github/automation.yml --output runs/automation/latest_snapshot
```

For multiple projects, the script writes:

- `runs/automation/latest_snapshot/project_<project_number>.json`
- `runs/automation/latest_snapshot/summary.json`

Offline fixture run:

```bash
python scripts/project_poll.py --config .github/automation.yml --fixture examples/project_poll_fixture.json
```

## Minimal runnable example

```bash
python examples/project_poll_demo.py
```
