# Prepare Task Skill

The `prepare-task` skill turns a loose chat idea or an existing GitHub Project task into implementation-ready technical work.

Use it when an idea needs repository-aware analysis before implementation. In chat, phrases such as "here is my idea", "I have an idea for a feature", or "turn this into a GitHub task" should start the skill. It instructs Codex to review relevant docs/source/tests/workflows, ask only necessary questions, draft the task details, and then ask for explicit confirmation before creating or updating a GitHub issue/project task.

The workflow includes the repository compliance baseline before implementation: GDPR privacy-by-design, data minimization, consent/transparency, retention/deletion, traceable logging, and EU AI Act human-oversight safeguards for legal-risk outputs.

Minimal runnable example:

```bash
python examples/minimal_demo.py
```
