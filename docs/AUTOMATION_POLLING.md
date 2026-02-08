# Project Polling Automation

This repository uses a scheduled polling workflow to drive Project V2 automation (GitHub Actions has no native
"project status changed" trigger).

## Workflow

- File: `.github/workflows/project_polling.yml`
- Triggers: `schedule` (default: every 15 minutes) and `workflow_dispatch`
- Purpose: fetch Project V2 items and write snapshot JSON files, then move Ready tasks with PRs to In review

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
    },
    {
      "name": "project-7",
      "owner": "mmaideveloper",
      "repo": "mmaideveloper/aijurisdictionagents",
      "project_number": 7,
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

For Project V2 read/write access, set a PAT as `GH_PROJECT_TOKEN` with scopes:

- `read:project`
- `project`

`GH_PROJECT_TOKEN` is required by the workflow. `GITHUB_TOKEN` is not used for Project V2 access
because it can fail with errors like:

- `GraphQL: Could not resolve to a ProjectV2 with the number <N>. (user.projectV2)`

## Local usage

```bash
python scripts/project_poll.py --config .github/automation.yml --output runs/automation/latest_snapshot
```

Move Ready tasks with PRs to In review:

```bash
python scripts/project_in_review.py --config .github/automation.yml --plan-output runs/automation/latest_snapshot/in_review_plan.json
```

For multiple projects, the script writes:

- `runs/automation/latest_snapshot/project_<project_number>.json`
- `runs/automation/latest_snapshot/summary.json`

Offline fixture run:

```bash
python scripts/project_poll.py --config .github/automation.yml --fixture examples/project_poll_fixture.json
```

Offline in-review dry run:

```bash
python scripts/project_in_review.py --config .github/automation.yml --fixture examples/project_poll_fixture.json --pr-fixture examples/project_pr_fixture.json --dry-run
```

## Minimal runnable example

```bash
python examples/project_poll_demo.py
```

In-review dry-run example:

```bash
python examples/project_in_review_demo.py
```
