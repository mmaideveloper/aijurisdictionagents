# Voice Intent Router

The backend exposes a client-agnostic voice intent endpoint for web, mobile, and API clients:

```text
POST /v1/voice/intent
```

The endpoint accepts a raw STT transcript and returns a structured action decision. Clients should call this endpoint before sending STT text into normal chat when the user may be issuing a command.

Example request:

```json
{
  "client_type": "web",
  "language_code": "SK",
  "user_id": "user-123",
  "execute": true,
  "transcript": "chcem vytvoriť prípad s názvom splnomocnenie 1.0, pošli"
}
```

Example response:

```json
{
  "intent": "create_case",
  "confidence": 0.93,
  "slots": {
    "title": "splnomocnenie 1.0"
  },
  "requires_confirmation": false,
  "clarification_question": null,
  "routing_strategy": "rules_v1",
  "transcript_redaction_hint": "store_title_only",
  "execution": {
    "status": "executed",
    "case_id": "case-id",
    "title": "splnomocnenie 1.0",
    "message": null
  }
}
```

If the router recognizes a case-creation command but cannot extract the title, it returns `intent=create_case`, empty `slots`, and one clarification question. Clients should show or speak that question instead of creating a case from the full transcript.

Repeat prefixes such as `ešte raz` are ignored before intent matching. For example, `Ešte raz vytvor nový prípad test` resolves to `create_case` with title `test`.

Clear confirmation answers return `confirm_yes` or `confirm_no` for `yes`, `no`, `ano`, `áno`, and `nie`. When a client has a pending confirmation, it should treat those intents as the decision and continue the pending action immediately instead of asking again.

Single-word send markers `koniec` and `end` are treated like `pošli` / `send`: by themselves they return `send_message`, and at the end of a command they are removed before slot extraction.

Compliance notes:

- The endpoint returns `transcript_redaction_hint` so clients and logs can avoid retaining raw STT content by default.
- The deterministic router stores no transcript. If `execute=true`, only the extracted case title is persisted through the case API.
- Legal advice and document generation should continue to require appropriate user confirmation and human-oversight safeguards.
- Future model-based routing can keep the same response schema and replace `routing_strategy` with a model-backed classifier.
