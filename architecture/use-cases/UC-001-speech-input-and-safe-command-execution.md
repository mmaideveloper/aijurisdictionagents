# UC-001: Submit questions and safely execute commands by speech

## Record

- Status: Draft
- Owner: Product owner (to assign)
- Date: 2026-08-28
- Stakeholders: JurisDigta users, product owner, legal/compliance reviewer, security reviewer, client application owners, tool owners
- Related artifacts: [`ADD-001`](../design/ADD-001-governed-speech-command-routing.md), [`ADR-001`](../decisions/ADR-001-route-speech-commands-through-policy-enforced-capabilities.md), [`docs/VOICE_INTENT_ROUTER.md`](../../docs/VOICE_INTENT_ROUTER.md), [`docs/mobile_voice_flow.md`](../../docs/mobile_voice_flow.md), [`docs/mobile_voice_compliance.md`](../../docs/mobile_voice_compliance.md), [`docs/SLOVAK_COMPANY_CHECKS.md`](../../docs/SLOVAK_COMPANY_CHECKS.md), [`docs/LEGAL_WORKFLOW_ROUTING.md`](../../docs/LEGAL_WORKFLOW_ROUTING.md), [`docs/E2E_TEST_EVIDENCE_RULE.md`](../../docs/E2E_TEST_EVIDENCE_RULE.md)

## Goal and Business Outcome

Allow a user to speak instead of type when asking JurisDigta a question or requesting an action. JurisDigta converts speech into a reviewable transcript, distinguishes questions from commands, routes confirmed requests to an available capability, and makes additional relevant capabilities discoverable without executing them automatically.

Success is measured by users being able to complete the supported synthetic question, local-file-search, and company-verification scenarios with the submitted text matching the reviewed transcript, no unconfirmed high-impact action, and no raw audio retained by default.

## Scope

### In scope

- Speech-to-text input for questions and commands on supported JurisDigta clients.
- A visible, editable transcript before ordinary submission or command authorization.
- Classification of input as a question, supported command, ambiguous request, or unsupported request.
- Routing questions through the existing question/answer path.
- Discovery of registered tools or skills that can satisfy a command.
- Safe execution of an explicitly authorized tool, including:
  - searching user-approved laptop folders for a contract matching a supplied name; and
  - checking whether a named Slovak company exists through the official ORSR capability.
- Suggesting other relevant available tools after the primary tool is identified or completed, with separate authorization for each execution.
- Localized clarification, consent, confirmation, progress, result, and error messages.
- Traceable, privacy-minimized audit metadata and human oversight for legal-risk outputs.

### Out of scope

- Unrestricted shell, PowerShell, Python, filesystem, or operating-system access generated directly from a transcript.
- Searching the whole device, network drives, cloud storage, email, or third-party applications without a separately approved connector and location scope.
- Automatically running every tool that appears related to a person or company.
- Persisting raw microphone audio by default.
- Voice authentication, speaker identification, covert/background listening, or use of a recording of another person.
- Irreversible legal filing, signature, payment, deletion, upload, or external submission based only on speech.
- Defining the final STT provider, command-classification implementation, or desktop integration architecture.

## Actors and Responsibilities

| Actor or system | Responsibility | Evidence/confidence |
|---|---|---|
| Authenticated user | Starts/stops listening, reviews or edits the transcript, grants access, confirms actions, and reviews results. | User request; Confirmed |
| JurisDigta client | Obtains microphone permission, presents processing notices, captures speech, displays the transcript and execution preview, and provides typed fallback. | `docs/mobile_voice_flow.md`; existing mobile/web behavior Confirmed, all-client coverage To verify |
| Speech recognition capability | Converts the active audio segment to text and reports recognition failures or uncertainty. | `docs/mobile_voice_flow.md`; Confirmed |
| Intent and command router | Distinguishes a question from a command, extracts minimum required inputs, discovers eligible registered capabilities, and asks for clarification when routing is unsafe. | `docs/VOICE_INTENT_ROUTER.md`; partial behavior Confirmed, generalized discovery Proposed |
| Question/answer system | Processes an authorized question through the normal JurisDigta request path and returns a reviewable answer. | User request and current product behavior; Confirmed |
| Tool/skill registry | Supplies capabilities, input requirements, permissions, data destinations, side-effect classification, and user-facing descriptions. | Existing tool registry and user request; partial behavior Confirmed, metadata completeness To verify |
| Local file-search connector | Searches only user-selected locations using a constrained read-only operation and returns matching file metadata. | User example; Proposed |
| ORSR capability | Queries the official Slovak business-register service and returns sourced company matches. | `docs/SLOVAK_COMPANY_CHECKS.md`; Confirmed |
| Human reviewer | Reviews legally significant answers, documents, or proposed external actions before reliance or submission. | `AGENTS.md` and `docs/mobile_voice_compliance.md`; Confirmed |

## Preconditions and Trigger

- Preconditions: The user is authenticated where required; microphone access and the applicable processing notice are available; speech input is enabled; at least one supported language is selected; tool registry metadata is current; each tool has an enforceable permission and side-effect policy.
- Trigger: The user activates the microphone and speaks a question or command.

## Main Success Flow

1. The client shows that listening has started, the active language, how to stop, and whether speech is processed on-device or sent to a named remote provider.
2. The user speaks one question or command and stops listening.
3. JurisDigta discards the transient audio after recognition unless a separately governed audio-storage option has been explicitly enabled.
4. The client displays the recognized transcript in an editable field and marks low-confidence or incomplete recognition when reported.
5. The user reviews or edits the transcript and chooses to continue.
6. JurisDigta classifies the reviewed text as a question, command, ambiguous request, or unsupported request.
7. For a question, JurisDigta submits exactly the reviewed text through the existing question/answer path.
8. For a command, JurisDigta discovers eligible registered tools/skills and validates required inputs, permissions, jurisdiction, and side-effect policy.
9. JurisDigta presents an execution preview naming the selected capability, intended action, minimum data used, data destination, location scope, expected side effects, and whether confirmation is required.
10. The user grants any required connector/location access and explicitly confirms the proposed execution.
11. JurisDigta executes only the confirmed structured action; it does not execute transcript-generated shell or code.
12. JurisDigta presents the result, source/provenance, limitations, and any next human-review step.
13. If other relevant registered capabilities are available, JurisDigta lists them separately with their purpose, needed data, destination, and risk, then asks whether the user wants to review one. None runs automatically.
14. JurisDigta records redacted trace metadata sufficient to reconstruct routing, authorization, capability selection, and outcome without storing raw audio or the full transcript in operational logs.

## Alternate and Failure Flows

| Condition | Expected behavior | Recovery or human escalation |
|---|---|---|
| Speech recognition is unavailable or permission is denied | Listening does not start; no audio is uploaded; the client explains the issue. | Offer typed input and instructions to change microphone permission. |
| Remote STT is selected but valid consent is absent or revoked | Remote audio upload is blocked. | Offer a genuinely local/device mode when available or typed input; do not silently switch to another remote processor. |
| Transcript is empty, incomplete, or low confidence | No request or tool executes. | Keep the draft and ask the user to edit, repeat, or type. |
| Intent is ambiguous between question and command | No tool executes. | Show the proposed interpretations and ask the user to select or clarify. |
| No eligible capability exists | JurisDigta says the request cannot currently be executed and does not improvise shell/code access. | Preserve the transcript for editing and offer supported alternatives. |
| Multiple capabilities can perform the request | JurisDigta compares the candidates by purpose, source, data destination, permissions, and side effects. | Ask the user to choose; apply policy-based default only after the default is documented and visible. |
| Required command input is missing | No tool executes. | Ask a focused clarification question for only the missing field. |
| User declines or cancels confirmation | The pending action is discarded or retained only as an editable draft according to the visible UI choice. | Return to the transcript without execution. |
| File-search command requests an unapproved or overly broad location | The connector refuses the search. | Ask the user to select one or more permitted folders and allow cancellation. |
| File search finds no match | Return zero results without guessing content or expanding scope. | Let the user refine the filename/contract terms or approve another folder. |
| File search finds multiple matches | Return minimal metadata such as filename, approved relative path, type, modified date, and optional redacted snippet. | Ask the user which result to open or use; opening/exporting is a separate action. |
| A symbolic link, junction, archive, hidden location, or permission boundary escapes the approved file-search scope | The connector stops at the boundary and records a policy-denied outcome. | Explain the excluded location; require a new explicit scope grant if supported. |
| ORSR returns no, multiple, stale, or conflicting matches | Present the official source status and do not claim that the company definitively exists or does not exist beyond the returned evidence. | Ask for IČO or another identifier; require user/human resolution before downstream legal work. |
| A related tool would send data to another service or perform a higher-impact action | It is shown as a suggestion only. | Require a new preview and explicit confirmation for that tool. |
| Capability fails or times out | Show that execution failed and avoid presenting partial output as verified. | Permit a safe retry or typed/manual alternative; retain redacted diagnostic identifiers. |
| User requests write, delete, upload, submission, payment, signature, or unrestricted command execution | The action is blocked unless a separately approved capability and high-impact authorization flow exist. | Require explicit confirmation and, where applicable, human review; otherwise explain that it is unsupported. |

## Information and Data

| Data category | Purpose | Source/recipient | Retention/deletion | Classification status |
|---|---|---|---|---|
| Transient microphone audio | Speech recognition for the active turn | User device to device recognizer or disclosed remote STT provider | Discard after recognition or failure by default; storage requires separate opt-in purpose and retention policy | Personal data; may contain special-category or confidential legal data; To classify per deployment |
| Reviewed transcript | Create the question or structured command | User/client to JurisDigta question or command path | Case messages follow case lifecycle; full transcript excluded from operational logs | Personal data possible; To classify per content |
| Structured command slots | Supply the minimum inputs required by the selected capability | Router to confirmed tool/skill | Retain only where needed for the resulting case record/audit; delete with applicable case/tool record | Personal data possible; To classify per tool |
| Voice consent/notice record | Prove authorization for remote voice processing | User/account service | Retain timestamp and notice version under the consent-record policy; support withdrawal without erasing required proof | Personal data; Confirmed category |
| Local search scope and file metadata | Enforce approved folders and show matching contracts | User device/local connector to user | Prefer session-only scope; do not upload file content by default; clear cached results on session end/cancellation | Confidential/personal data possible; To classify |
| Company name or IČO and registry result | Verify a legal entity | User/JurisDigta to official ORSR service and back | Retain sourced result only when needed for the case/audit; apply case deletion and freshness rules | Public business data, potentially personal data for representatives; To classify |
| Tool discovery metadata | Explain eligible capabilities and permission needs | Tool registry to client | Retain as versioned product metadata, not user data | Non-personal unless tool input examples contain data; Confirmed with caveat |
| Audit metadata | Trace routing, consent, confirmation, capability version, result status, and human review | JurisDigta services to authorized audit store | Retention period and access policy To verify; delete/anonymize when no longer necessary | Personal data possible; To classify |

## Requirements and Constraints

### Functional requirements

- `FR-01`: The client shall let the user start and stop speech capture and shall visibly indicate the listening state.
- `FR-02`: The client shall display an editable transcript and shall not submit an ordinary question until the user performs the configured explicit send action.
- `FR-03`: The system shall submit the same normalized text that the user reviewed; normalization shall not materially change names, identifiers, amounts, dates, negation, or legal meaning.
- `FR-04`: The router shall classify reviewed input as question, supported command, ambiguous request, or unsupported request and expose the decision to the user when an action is proposed.
- `FR-05`: A question shall follow the existing question/answer path and remain available in text for human review.
- `FR-06`: A command shall be represented as a structured capability identifier plus validated slots; raw transcript text shall never be executed as shell, PowerShell, Python, SQL, or operating-system code.
- `FR-07`: Every executable capability shall declare required inputs, permissions, data destination, side-effect level, confirmation policy, and user-facing purpose before it is eligible for voice routing.
- `FR-08`: The system shall ask a focused clarification question and shall not execute when required input, intent, target, or scope is ambiguous.
- `FR-09`: The user shall receive an execution preview and explicitly confirm any access to local files, remote external lookup, state change, disclosure, or legal-risk action before execution.
- `FR-10`: A local contract search shall be read-only, restricted to user-approved folders, prevent scope escape, and return minimal metadata before any file is opened or uploaded.
- `FR-11`: Company-existence requests for Slovakia shall use the registered official ORSR capability, identify the source and retrieval time, distinguish zero/one/multiple matches, and request a stronger identifier when needed.
- `FR-12`: The system shall discover other relevant registered capabilities and may suggest them with purpose, required data, destination, and risk; each shall require separate user selection and authorization.
- `FR-13`: The system shall not automatically execute all related capabilities or silently broaden file, entity, jurisdiction, or data scope.
- `FR-14`: The user shall be able to cancel before execution and stop a running capability when the capability supports safe cancellation.
- `FR-15`: Results shall identify the executed capability, completion status, source/provenance, limitations, and any required human-review step.
- `FR-16`: The system shall provide typed input and manual workflow alternatives when speech or a requested capability is unavailable.
- `FR-17`: Remote STT shall be blocked without the applicable explicit consent/authorization and current notice version; local/device processing shall not be described as local when the platform may use a remote service.
- `FR-18`: Raw audio storage shall be disabled by default, and operational logs shall exclude raw audio and full transcripts.
- `FR-19`: The system shall record redacted trace metadata linking transcript review, intent decision, capability version, authorization, execution, and outcome.
- `FR-20`: The user shall receive localized confirmation and clarification prompts in the supported interaction language, while filenames, company names, IČO values, and other exact identifiers remain unaltered.

### Quality attributes

- `QA-01 Privacy`: Given remote STT without valid consent, no raw audio byte shall leave the controlled client pipeline and a typed/local alternative shall be visible.
- `QA-02 Security`: Given a spoken prompt containing shell syntax, path traversal, wildcard roots, or instruction injection, the system shall treat it as data, enforce structured schemas and approved roots, and execute no generated code.
- `QA-03 Safety`: Given a command with external, destructive, or legal effect, the action shall not run until the user has reviewed the transcript and a specific execution preview and has confirmed it.
- `QA-04 Traceability`: An authorized reviewer shall be able to correlate the intent decision, consent/confirmation event, capability and policy version, outcome, and human-review state without access to raw audio or full transcript logs.
- `QA-05 Accessibility`: Speech controls, transcript review, confirmation, cancellation, and errors shall be operable with assistive technologies, and all voice-only information shall also be presented visually.
- `QA-06 Reliability`: Duplicate partial/final STT events or repeated confirmation events shall not execute the same command more than once; an idempotency key shall cover each authorized action.
- `QA-07 Performance`: Target recognition, routing, and tool-response times shall be defined per supported client and capability before approval; progress and cancellation shall be visible for longer operations.
- `QA-08 Interoperability`: Routing shall use a client-independent structured capability contract so the same safety policy applies to mobile, web, desktop, and API clients that support voice.
- `QA-09 Explainability`: When suggesting a capability, the system shall state why it is relevant and what data/access it needs in language understandable to the user.

## Privacy, AI, and Sector Governance Assessment

- Personal/special-category data: Spoken legal questions, transcripts, filenames, contract content, identifiers, addresses, and company representative data may contain personal, confidential, special-category, or legally privileged information. Classification remains content- and deployment-dependent.
- Lawful basis or consent: The lawful basis for processing ordinary account/case content and the distinction between GDPR consent and device permission must be verified. Explicit informed consent is required by current project policy before raw audio is sent to remote STT. Local file access requires a separate, purpose-specific user grant; ORSR execution requires explicit user confirmation under current project policy.
- Data minimization and purpose limitation: Capture only the active utterance; prefer a reviewable transcript; disable raw-audio persistence; extract only required structured slots; restrict local search to approved roots; do not upload matched files by default; do not execute merely related tools.
- Retention, deletion, and subject rights: Raw audio is transient by default. Voice-derived case content follows case retention/deletion controls. Retention for consent and redacted command audit records, connector grants, and ORSR snapshots must be specified before approval. Access, correction, deletion, restriction, portability, and withdrawal paths must be mapped to each controller/processor role.
- AI role and risk classification: STT and any model-assisted routing support interaction and may influence legal workflows, but they shall not make final legal decisions or perform irreversible legal acts. The applicable EU AI Act role, system classification, transparency duties, provider documentation, accuracy expectations, and deployer obligations are To verify with the legal/compliance reviewer.
- Transparency, traceability, and human oversight: Disclose listening state, provider/destination, transcript, proposed tool, data shared, result source, uncertainty, and limitations. Require review and confirmation before capability execution, preserve text results, and require qualified human review before reliance on legal-risk outputs.
- Compliance blockers: Approval is blocked until lawful bases/controller-processor roles, remote STT provider terms and transfers, supported local-search boundaries, capability risk taxonomy, audit retention/access, and EU AI Act classification are documented and reviewed.

## Acceptance Criteria

- [ ] `AC-01` Given an approved synthetic spoken question, when recognition completes, then the visible editable transcript equals the expected normalized text and the exact reviewed normalized text is submitted to the question/answer path.
- [ ] `AC-02` Given low-confidence or incomplete recognition, when the result is shown, then no submission or command occurs and the user can edit, repeat, or type.
- [ ] `AC-03` Given a synthetic voice command to find contract `ACME-2026` in a user-approved test folder, when the user confirms the preview, then only that approved folder is searched read-only and matching metadata is shown without uploading or opening the file.
- [ ] `AC-04` Given the same file-search command without an approved folder, when routing completes, then no filesystem search occurs and JurisDigta asks the user to choose a permitted location.
- [ ] `AC-05` Given a malicious filename or transcript containing PowerShell, Python, traversal, or prompt-injection text, when the command is routed, then the text remains data, approved-root enforcement holds, and no generated command/code executes.
- [ ] `AC-06` Given a synthetic request to check whether company `XY Test s. r. o.` exists in Slovakia, when the user confirms ORSR access, then the registered official ORSR capability executes and the UI shows source, retrieval time, and zero/one/multiple-match status.
- [ ] `AC-07` Given an ambiguous company name with multiple ORSR matches, when results return, then JurisDigta does not choose silently and asks for IČO or another distinguishing value.
- [ ] `AC-08` Given that another registered company-related capability is relevant, when the primary result is shown, then JurisDigta explains the additional capability, data destination, and risk and does not execute it until separately selected and confirmed.
- [ ] `AC-09` Given valid recognition but no eligible capability, when the user continues, then JurisDigta states that the command is unsupported and offers a typed/manual alternative without invoking unrestricted OS commands.
- [ ] `AC-10` Given remote STT mode and absent or revoked consent, when the user starts speech input, then remote audio upload is blocked and an honest local/device or typed alternative is presented.
- [ ] `AC-11` Given duplicate STT final events or repeated confirmation input for one pending action, when processing completes, then the capability executes at most once.
- [ ] `AC-12` Given any write, delete, upload, external submission, signature, payment, or legal-document action inferred from speech, when no specific high-impact confirmation is recorded, then the action does not execute.
- [ ] `AC-13` Given a completed or failed command, when an authorized reviewer examines the audit record, then the reviewer can correlate redacted routing, consent/confirmation, capability/policy version, and outcome without raw audio, credentials, or full transcript content.
- [ ] `AC-14` Given cancellation before confirmation, when the user cancels, then no capability executes and the user can keep or discard the editable transcript.
- [ ] `AC-15` Final user-facing E2E evidence uses approved synthetic audio and synthetic files/entities, verifies transcript-before-submit equality, exercises real local services and PostgreSQL with the configured real model where applicable, and retains a sanitized final-state screenshot and manifest under the ignored evidence path defined by `docs/E2E_TEST_EVIDENCE_RULE.md`.

## Assumptions and Open Questions

| Item | State | Owner/source | Due date |
|---|---|---|---|
| The first release targets mobile and web; desktop/laptop file search requires a separately installed, authenticated local connector. | Assumption | Product and client owners | Unknown |
| Slovak, English, and German are initial voice languages. | Assumption based on current mobile documentation | Product owner | Unknown |
| The default interaction is message mode with visible transcript review; continuous conversation remains opt-in. | Confirmed current baseline | `docs/mobile_voice_flow.md` | N/A |
| Should ordinary questions require an explicit send click, spoken send phrase, or both on each client? | To verify | Product/UX owner | Unknown |
| Which operating systems and locations may the local connector search, and are network/cloud-synced folders excluded initially? | To verify; approval blocker for file search | Security and product owners | Unknown |
| May file search inspect document contents, or only filenames and metadata in the first release? | To verify; this draft recommends metadata/filename first | Product, privacy, and security reviewers | Unknown |
| What capability side-effect levels and confirmation rules apply to read-only local, read-only external, write, disclosure, destructive, and legal-submission actions? | To verify; approval blocker | Security, compliance, and architecture owners | Unknown |
| Should ORSR lookup always require confirmation, or may a user configure a standing preference for public-registry read-only checks? | To verify; current project documentation requires explicit consent | Product and compliance owners | Unknown |
| Which related company tools are registered, and what ranking/relevance threshold avoids noisy or unsafe suggestions? | To verify | Tool owners and product owner | Unknown |
| What are the controller/processor roles, lawful bases, remote STT transfer safeguards, and notice versions for each deployment? | To verify; compliance blocker | DPO/legal reviewer | Unknown |
| What are the retention periods and access roles for consent, connector grant, ORSR result, and command audit records? | To verify; compliance blocker | DPO/security owner | Unknown |
| What accuracy, latency, supported-language, accessibility, and failure-rate targets define release acceptance? | To verify | Product/SRE/accessibility owners | Unknown |
| Is a material business decision needed for local-device access and external capability suggestion policy? | To verify; likely yes | Product/architecture authority | Unknown |

## Evidence

| Claim | Source | Confidence |
|---|---|---|
| Mobile/web message mode already creates a visible transcript and routes explicit action phrases through the intent/action layer. | `docs/mobile_voice_flow.md` | Confirmed repository evidence |
| A client-independent voice intent endpoint and structured action decision already exist for some commands. | `docs/VOICE_INTENT_ROUTER.md` | Confirmed repository evidence |
| Existing policy blocks remote raw-audio upload without consent and disables raw-audio storage by default. | `docs/mobile_voice_compliance.md` | Confirmed repository evidence |
| Existing safeguards require confirmation and human review for legal-risk actions and documents. | `docs/mobile_voice_compliance.md` and `AGENTS.md` | Confirmed repository evidence |
| Official ORSR lookup capability and company-verification workflow exist. | `docs/SLOVAK_COMPANY_CHECKS.md` and `docs/LEGAL_WORKFLOW_ROUTING.md` | Confirmed repository evidence |
| Voice E2E evidence must use synthetic audio, verify transcript-before-submit equality, and retain sanitized visual/machine evidence. | `docs/E2E_TEST_EVIDENCE_RULE.md` | Confirmed repository evidence |
| A constrained laptop contract-search connector exists. | Repository search found no such general connector | Not found; proposed capability |
| Users want speech to create questions/commands, local contract search, ORSR company checks, and optional discovery of other related tools. | User request dated 2026-08-28 | Confirmed stakeholder input |

## Stakeholder Feedback Log

| Date | Source/reviewer role | Change or outcome |
|---|---|---|
| 2026-08-28 | Requesting stakeholder | Requested speech input for questions and commands, local contract search, ORSR company existence lookup, and optional discovery of related tools. |
| 2026-08-28 | Codex architecture draft | Reframed the feature as an extension of existing STT/voice routing, introduced structured execution and risk-tiered confirmation, and marked local device search and generalized related-tool discovery as proposed. |
