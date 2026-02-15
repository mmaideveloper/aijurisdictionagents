# Lifecycle Automation

GitHub Actions lifecycle workflow automation is removed from this repository.
Use local scripts and project automation helpers for lifecycle operations.

## Local flow

1. Select task in `Ready`.
2. Move task to `In progress`.
3. Implement on a feature branch.
4. Open PR to `main`.
5. Move task to `In review`.
6. Add comment `Implemented by Codex`.

## Related scripts

- `scripts/project_status.ps1`: updates project status and posts optional issue comments.
- `scripts/lifecycle_agent_run.py`: local lifecycle stage runner.

## Minimal runnable example

```bash
python examples/minimal_demo.py
```
