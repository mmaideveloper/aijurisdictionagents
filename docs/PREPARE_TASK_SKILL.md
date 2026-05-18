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
- `/prepare-task I want to improve speech to text for the mobile app`
- `/prepar-task I want to improve speech to text for the mobile app`
- `/prepare-task -url "https://github.com/mmaideveloper/aijurisdictionagents/issues/318"`
- `/prepar-task -url "https://github.com/mmaideveloper/aijurisdictionagents/issues/318"`
- `Here is my idea for a feature. Prepare the task.`
- `Turn this into a GitHub task and ask me all missing technical/compliance questions first.`

Supported usage pattern (same intent in each surface):

- **VS Code:** start repository chat with `$prepare-task`, `/prepare-task [description]`, `/prepar-task [description]`, `/prepare-task -url [issue-url]`, `/prepar-task -url [issue-url]`, or a trigger phrase. Answer follow-up questions when details are missing.
- **Codex Web:** run the same prompt in workspace chat and continue the readiness interview flow.
- **Codex Desktop:** use the same prompt in project chat; keep the same readiness gate before implementation.

Slash-triggered requests mean the user already wants a GitHub Project task created. Codex should still review the repository, prepare technical requirements, run the GDPR/EU AI Act readiness check, and ask up to three focused questions when details are missing. Once the task is ready, Codex should create the GitHub issue/project item in the appropriate project. If the task is not ready and the user accepts open questions, Codex can create the task with a clear "Not Ready Yet" section.

For `-url` requests, Codex should read the linked GitHub issue as the basic idea source, inspect available issue metadata/comments/project status, review the repository, ask for missing details, and then write the prepared technical section back to that same issue at the end of the conversation. The original issue text should be preserved unless the user explicitly asks to replace it.
