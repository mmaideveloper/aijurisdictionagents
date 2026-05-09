# Prepare Task Skill

The `prepare-task` skill turns a loose chat idea or an existing GitHub Project task into implementation-ready technical work.

Use it when an idea needs repository-aware analysis before implementation. In chat, phrases such as "here is my idea", "I have an idea for a feature", or "turn this into a GitHub task" should start the skill. It instructs Codex to review relevant docs/source/tests/workflows, ask only necessary questions, draft the task details, and then ask for explicit confirmation before creating or updating a GitHub issue/project task.

The workflow includes the repository compliance baseline before implementation: GDPR privacy-by-design, data minimization, consent/transparency, retention/deletion, traceable logging, and EU AI Act human-oversight safeguards for legal-risk outputs.

Minimal runnable example:

```bash
python examples/minimal_demo.py
```

It now includes an explicit cross-channel parity gate so features that work in one surface (for example chat simulator document previews) are not considered ready until expected API/mobile/frontend behavior is specified as well.


## Running the Skill Across Codex Surfaces

Use one of these prompts in chat:

- `$prepare-task`
- `Here is my idea for a feature. Prepare the task.`
- `Turn this into a GitHub task and ask me all missing technical/compliance questions first.`

Supported usage pattern (same intent in each surface):

- **VS Code:** start repository chat with `$prepare-task` (or a trigger phrase), answer follow-up questions, and confirm before any GitHub updates.
- **Codex Web:** run the same prompt in workspace chat and continue the readiness interview flow.
- **Codex Desktop:** use the same prompt in project chat; keep the same readiness gate before implementation.
