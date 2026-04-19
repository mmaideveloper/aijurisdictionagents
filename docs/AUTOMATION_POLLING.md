# Project Polling Automation

This repository uses local polling scripts to drive Project V2 automation.

Automatic polling/pooling GitHub workflow execution is disabled/removed.
Reason: project automation is kept local/manual for predictable control of task transitions and comments.

## Local automation

- Purpose: fetch Project V2 items and write snapshot JSON files, then move Ready tasks with PRs to In review.
- Run manually or from your own scheduler/CI.

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


Review tasks that are missing the `codex - business requirements reviewed` comment:

```bash
python scripts/project_requirements_review.py --config .github/automation.yml --output runs/automation/latest_snapshot/requirements_review_plan.json
```

Apply comments directly to GitHub issues (posts marker comment where missing):

```bash
python scripts/project_requirements_review.py --config .github/automation.yml --apply --output runs/automation/latest_snapshot/requirements_review_plan.json
```

Apply comments **and** auto-fix missing requirements sections in issue descriptions:

```bash
python scripts/project_requirements_review.py --config .github/automation.yml --apply --fix-body --output runs/automation/latest_snapshot/requirements_review_plan.json
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

Requirements-review dry-run example:

```bash
python examples/project_requirements_review_demo.py
```

## VS Code manual run

This workspace now includes `.vscode/tasks.json` with ready-to-run commands:

- `Automation: Poll projects snapshot`
- `Automation: Requirements review (dry run)`
- `Automation: Requirements review (apply + fix body)`
- `Automation: Move Ready -> In review`

Run them from **Terminal -> Run Task...**.

Recommended extensions are listed in `.vscode/extensions.json`:

- GitHub Pull Requests and Issues (`github.vscode-pull-request-github`) for issue/PR visibility.
- Python (`ms-python.python`) for running/debugging local scripts.

## Scheduling every 15 minutes

VS Code tasks are manual by default. For scheduling, use your OS scheduler and call the same command.

Linux/macOS cron example:

```bash
*/15 * * * * cd /path/to/aijurisdictionagents && python scripts/project_requirements_review.py --config .github/automation.yml --apply --fix-body --output runs/automation/latest_snapshot/requirements_review_plan.json >> runs/automation/scheduler.log 2>&1
```

Windows Task Scheduler action example:

```powershell
python scripts/project_requirements_review.py --config .github/automation.yml --apply --fix-body --output runs/automation/latest_snapshot/requirements_review_plan.json
```
