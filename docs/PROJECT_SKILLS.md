# Project Skills

This repository vendors the Codex skills needed for local development so they are available after cloning on another computer.

## Repo-local skills

- `api`: alias for starting the local API with the same skill name used in the local Codex profile
- `chatsimulatr`: starts the local chat simulator app and verifies both `/health` and `/chat-simulator`
- `start-api`: project-native API launcher
- `start-mobile`: alias for the mobile launcher with the same skill name used in the local Codex profile
- `start-mobile-app`: project-native Flutter mobile launcher
- `laws-collector`: starts and verifies the local laws collector worker loop
- `prepare-task`: prepares ideas or GitHub Project tasks for implementation by reviewing repository context, asking required questions, and updating or creating the task description

## Skill files

Each skill lives under `skills/<name>/` and contains:

- `SKILL.md`: trigger metadata and workflow instructions
- `agents/openai.yaml`: UI metadata for Codex skill chips
- `scripts/`: optional executable helpers when the workflow needs deterministic startup logic

## Sync To Another Computer

After cloning the repository on a different machine, install or refresh the project skills in the local Codex profile:

```bash
python scripts/sync_codex_skills.py --force
```

Dry-run preview:

```bash
python scripts/sync_codex_skills.py --dry-run
```

## Minimal Example

Use the example wrapper to verify the repo sees all skills and to preview the sync plan:

```bash
python examples/project_skills_demo.py
```

The default repository demo also prints the task-preparation skill contract:

```bash
python examples/minimal_demo.py
```
