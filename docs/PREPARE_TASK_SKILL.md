# Prepare Task Skill

The `prepare-task` skill turns a loose idea or an existing GitHub Project task into implementation-ready technical work.

Use it when an idea needs repository-aware analysis before implementation. The skill instructs Codex to review relevant docs/source/tests/workflows, ask only necessary questions, and then insert a structured "Prepared Technical Details" section into the existing task description. If no task exists, it creates a new GitHub issue/project task when GitHub access is available.

The workflow includes the repository compliance baseline before implementation: GDPR privacy-by-design, data minimization, consent/transparency, retention/deletion, traceable logging, and EU AI Act human-oversight safeguards for legal-risk outputs.

Minimal runnable example:

```bash
python examples/minimal_demo.py
```
