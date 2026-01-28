Tech stack (Python/Node), target runtime, dependencies

Architecture: agents, orchestration, documents ingestion, evaluation/judging, logging

Coding standards: typing, linting, tests, error handling

Output requirements: always create/update docs, add minimal runnable example
Minimal runnable example (default): `python examples/minimal_demo.py`

Read task for implementation from project https://github.com/users/mmaideveloper/projects/5 and 
tasks with status "Ready". 

Ask for implementation of task.  Create for each task separate branch.
If you start working move task to in progress.
Before moving a task to In review:
- Commit your changes.
- Create a pull request targeting `main`.
If you finish change status to In review and send me notice.
Add a comment to the issue: "Implemented by Codex".
Use scripts/project_status.ps1 when possible and ensure gh has read:project + project scopes.

Always activate the conda environment in `./conda` before running any project command.

If the user asks to close a task:
- Review the PR and perform a code review.
- If acceptable, approve and merge to `main`.
- Add a comment to the issue with the review/merge outcome.
- Delete the feature branch and comment that deletion on the issue.
- Move the task to Done (closed).

