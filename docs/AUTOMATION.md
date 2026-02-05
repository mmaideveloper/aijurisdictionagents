# Automation

This repository includes automation utilities for managing GitHub Project workflows (task creation and status updates).

## Requirements

- `gh` CLI authenticated to the correct account.
- Scopes: `read:project` (list items) and `project` (edit status).
- If available, the automation uses `scripts/project_status.ps1` on Windows.

## Create tasks and set Ready status

Provide tasks in a JSON file (list or `{ "tasks": [...] }`).

Example `automation_tasks.json`:

```json
{
  "tasks": [
    {"title": "Task A", "body": "Details for task A"},
    {"title": "Task B", "body": "Details for task B"}
  ]
}
```

Run the command:

```bash
python -m aijurisdictionagents.automation.cli create-ready --file examples/automation_tasks.json
```

Dry-run (no GitHub changes):

```bash
python -m aijurisdictionagents.automation.cli create-ready --file examples/automation_tasks.json --dry-run
```

A minimal example script is available at `examples/automation_demo.py`.
