# AI Architect Toolkit

JurisDigta stores its architecture artifacts in `architecture/` but obtains the generic Codex authoring skills from [mmaideveloper/aiarchitecttoolkit](https://github.com/mmaideveloper/aiarchitecttoolkit). The exact source commit and selected skills are recorded in `architecture/toolkit.lock.json`.

## Install or refresh

From the repository root:

```powershell
.\conda\python.exe scripts\sync_aiarchitect_toolkit.py --force
```

Preview without writing:

```powershell
.\conda\python.exe scripts\sync_aiarchitect_toolkit.py --dry-run
```

For a previously cloned toolkit checkout, avoid a network clone and verify that it is at the pinned commit:

```powershell
.\conda\python.exe scripts\sync_aiarchitect_toolkit.py --source C:\path\to\aiarchitecttoolkit --dry-run
```

The repository-local `idea-task` and `prepare-task` remain JurisDigta-specific adapters because they contain GitHub Project, channel-parity, and compliance rules. Generic architecture skills are not duplicated here.

The pinned generic set also includes security, Azure, and final-solution review skills. Updating the pin requires reviewing the toolkit changes, updating both the lock file and CI workflow to the same commit, and rerunning the validation below.

## Validate a use case in GitHub Actions

Run the `Validate architecture use case` workflow manually with a synthetic `UC-NNN` identifier. The caller in `.github/workflows/validate-architecture-use-case.yml` invokes the reusable toolkit workflow at the exact commit recorded in `architecture/toolkit.lock.json` and uploads the validation report, rendered Mermaid diagrams, and PDF.

The pinned toolkit commit must exist in `mmaideveloper/aiarchitecttoolkit` before the workflow can run. Keep the workflow `uses` value, its `toolkit_ref`, and `architecture/toolkit.lock.json` aligned.

## Artifact workflow

```text
idea
  -> optional BDR business decision
  -> reviewed use case
  -> ADD with only the necessary C4 views
  -> one ADR per independently changeable architecture decision
  -> implementation-ready task
  -> implementation
  -> architecture conformance review
```

Use `architecture/index.md` as the traceability entry point. Existing files under `docs/` remain valid and should be migrated or linked incrementally when changed.

## Governance

The toolkit supplies project-neutral workflow guidance. `AGENTS.md` and `architecture/toolkit-profile.yaml` supply the JurisDigta GDPR, EU AI Act, human-oversight, worktree, versioning, testing, and release requirements. Never treat the profile as evidence that a particular classification or approval has been established.
