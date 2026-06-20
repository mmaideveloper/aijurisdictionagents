import React from "react";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useLocalRuntime,
  type ChatModelAdapter,
  type ThreadMessageLike
} from "@assistant-ui/react";
import { BsArrowUpCircle, BsLockFill, BsShieldCheck } from "react-icons/bs";
import {
  AssistantResponse,
  CaseMode as GatewayCaseMode,
  submitAssistantQuestion
} from "../assistantGateway";
import { ApiRequestError, createChatSession, replyToSession } from "../api/chatClient";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";
import { useCases } from "../state/CaseProvider";

type AdapterRunOptions = Parameters<ChatModelAdapter["run"]>[0];

const extractTextContent = (content: AdapterRunOptions["messages"][number]["content"]): string => {
  return content
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("\n")
    .trim();
};

const latestUserText = (messages: AdapterRunOptions["messages"]): string => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message?.role === "user") {
      return extractTextContent(message.content);
    }
  }
  return "";
};

const AssistantThread: React.FC = () => {
  const { language, t } = useLanguage();
  const { user } = useAuth();
  const sessionRef = React.useRef<{ language: string; userId?: string; sessionId: string } | null>(null);

  const assistantMessages = React.useMemo<ThreadMessageLike[]>(
    () => [
      {
        role: "assistant",
        content: t("assistantInitialMessage"),
        status: { type: "complete", reason: "stop" }
      }
    ],
    [t]
  );

  const assistantAdapter = React.useMemo<ChatModelAdapter>(
    () => ({
      async run(options) {
        const content = latestUserText(options.messages);
        if (!content) {
          return {
            content: [{ type: "text", text: t("assistantEmptyMessageResponse") }],
            status: { type: "complete", reason: "stop" }
          };
        }

        try {
          const userId = user?.userId;
          const existingSession = sessionRef.current;
          const session =
            existingSession?.language === language && existingSession.userId === userId
              ? existingSession
              : {
                  language,
                  userId,
                  sessionId: (await createChatSession({ language, userId })).id
                };
          sessionRef.current = session;

          const assistantMessage = await replyToSession({
            sessionId: session.sessionId,
            content
          });

          return {
            content: [{ type: "text", text: assistantMessage.content }],
            status: { type: "complete", reason: "stop" }
          };
        } catch (error) {
          const status = error instanceof ApiRequestError && error.status ? String(error.status) : "network";
          const detail = error instanceof Error ? error.message : "Unknown error";
          return {
            content: [{ type: "text", text: t("assistantApiErrorResponse", { status, detail }) }],
            status: { type: "complete", reason: "stop" }
          };
        }
      }
    }),
    [language, t, user?.userId]
  );

  const runtime = useLocalRuntime(assistantAdapter, {
    initialMessages: assistantMessages
  });

  const Message: React.FC = () => (
    <MessagePrimitive.Root className="assistant-message">
      <MessagePrimitive.If user>
        <div className="assistant-message__role">{t("assistantUserRole")}</div>
      </MessagePrimitive.If>
      <MessagePrimitive.If assistant>
        <div className="assistant-message__role">{t("assistantRole")}</div>
      </MessagePrimitive.If>
      <div className="assistant-message__body">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="assistant-thread">
        <ThreadPrimitive.Viewport className="assistant-thread__viewport">
          <ThreadPrimitive.Messages components={{ Message }} />
        </ThreadPrimitive.Viewport>
        <ComposerPrimitive.Root className="assistant-composer">
          <ComposerPrimitive.Input
            className="assistant-composer__input"
            placeholder={t("assistantComposerPlaceholder")}
            aria-label={t("assistantComposerLabel")}
          />
          <ComposerPrimitive.Send className="assistant-composer__send" aria-label={t("assistantSend")}>
            <BsArrowUpCircle aria-hidden="true" />
          </ComposerPrimitive.Send>
        </ComposerPrimitive.Root>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
};

const AssistantWorkspace: React.FC = () => {
  const { t } = useLanguage();
  const { activeCase, cases, addInteraction } = useCases();
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const [caseMode, setCaseMode] = React.useState<GatewayCaseMode>(activeCase ? "existing" : "new");
  const [caseId, setCaseId] = React.useState(activeCase?.id ?? "");
  const [question, setQuestion] = React.useState("");
  const [files, setFiles] = React.useState<File[]>([]);
  const [answer, setAnswer] = React.useState<AssistantResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [formError, setFormError] = React.useState("");

  React.useEffect(() => {
    if (activeCase && caseMode === "existing") {
      setCaseId(activeCase.id);
    }
  }, [activeCase, caseMode]);

  const modes = [
    t("assistantModeLegalSearch"),
    t("assistantModePrepareDocument"),
    t("assistantModeDraftDocument"),
    t("assistantModeVerifyPerson"),
    t("assistantModeVerifyCompany"),
    t("assistantModeScreenPerson"),
    t("assistantModeScreenCompany"),
    t("assistantModeVerifyCar"),
    t("assistantModeVerifyLocation")
  ];

  const capabilities = [
    t("assistantCapabilityLawSearch"),
    t("assistantCapabilityOrsr"),
    t("assistantCapabilityPerson"),
    t("assistantCapabilityScreening"),
    t("assistantCapabilityCar"),
    t("assistantCapabilityLocation")
  ];

  const canSubmit =
    question.trim().length > 0 &&
    (caseMode === "new" || caseId.trim().length > 0) &&
    !isSubmitting;

  const handleFilesSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextFiles = Array.from(event.target.files ?? []);
    if (nextFiles.length === 0) {
      return;
    }
    setFiles((current) => [...current, ...nextFiles]);
    event.target.value = "";
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) {
      setFormError("Enter a question and select a case target before sending.");
      return;
    }

    setIsSubmitting(true);
    setFormError("");

    const response = await submitAssistantQuestion({
      question,
      caseMode,
      caseId: caseId.trim(),
      country: "SK",
      language: "sk",
      consentGateway: true,
      consentDocuments: true,
      consentThirdParty: false,
      files
    });

    setAnswer(response);
    setCaseId(response.caseId);

    if (caseMode === "existing" && cases.some((caseItem) => caseItem.id === response.caseId)) {
      addInteraction(response.caseId, "User", question);
      addInteraction(response.caseId, "AI Assistant", response.answer);
    }

    setIsSubmitting(false);
  };

  return (
    <div className="page assistant-workspace-page">
      <section className="assistant-workspace">
        <aside className="assistant-rail" aria-label={t("assistantThreadsTitle")}>
          <div>
            <p className="eyebrow">{t("assistantThreadsTitle")}</p>
            <h2>{t("assistantThreadCurrent")}</h2>
          </div>
          <div className="assistant-thread-list">
            <button type="button" className="assistant-thread-item active">
              {t("assistantThreadCurrent")}
            </button>
            <button type="button" className="assistant-thread-item">
              {t("assistantThreadDocument")}
            </button>
          </div>
        </aside>

        <main className="assistant-main" aria-labelledby="assistant-title">
          <section className="assistant-main__header">
            <div>
              <p className="eyebrow">{t("assistantEyebrow")}</p>
              <h1 id="assistant-title">{t("assistantTitle")}</h1>
              <p>{t("assistantSubtitle")}</p>
            </div>
            <div className="assistant-access">
              <BsShieldCheck aria-hidden="true" />
              <span>{t("assistantApiAuthAccess")}</span>
            </div>
          </section>

          <section className="assistant-mode-strip" aria-label={t("assistantModesTitle")}>
            {modes.map((mode, index) => (
              <button key={mode} type="button" className={index === 0 ? "active" : ""}>
                {mode}
              </button>
            ))}
          </section>

          <section className="assistant-gateway-card" aria-labelledby="assistant-gateway-title">
            <div className="assistant-gateway-card__header">
              <div>
                <p className="eyebrow">Assistant Gateway</p>
                <h2 id="assistant-gateway-title">Ask with case documents</h2>
              </div>
              <span>{answer?.caseId ?? "No answer yet"}</span>
            </div>
            <form className="assistant-gateway-form" onSubmit={handleSubmit}>
              <div className="assistant-gateway-form__row">
                <label>
                  <span>Case target</span>
                  <select
                    value={caseMode}
                    onChange={(event) => setCaseMode(event.target.value as GatewayCaseMode)}
                  >
                    <option value="new">Create new case</option>
                    <option value="existing">Use existing case</option>
                  </select>
                </label>
                <label>
                  <span>Case ID</span>
                  <input
                    type="text"
                    value={caseId}
                    disabled={caseMode === "new"}
                    list="assistant-case-options"
                    placeholder={caseMode === "new" ? "Generated after answer" : "Select or enter case ID"}
                    onChange={(event) => setCaseId(event.target.value)}
                  />
                  <datalist id="assistant-case-options">
                    {cases.map((caseItem) => (
                      <option key={caseItem.id} value={caseItem.id}>
                        {caseItem.title}
                      </option>
                    ))}
                  </datalist>
                </label>
              </div>

              <label>
                <span>Question</span>
                <textarea
                  rows={4}
                  value={question}
                  placeholder="Write the legal question and facts to answer."
                  onChange={(event) => setQuestion(event.target.value)}
                />
              </label>

              <div className="assistant-gateway-upload">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.txt,.md,.doc,.docx,.png,.jpg,.jpeg"
                  hidden
                  onChange={handleFilesSelected}
                />
                <button
                  type="button"
                  className="button ghost"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Upload documents
                </button>
                <span>{files.length} document{files.length === 1 ? "" : "s"} selected</span>
              </div>

              {files.length > 0 ? (
                <ul className="assistant-gateway-files">
                  {files.map((file) => (
                    <li key={`${file.name}-${file.size}-${file.lastModified}`}>
                      <span>{file.name}</span>
                      <button
                        type="button"
                        className="button ghost small"
                        onClick={() =>
                          setFiles((current) =>
                            current.filter(
                              (currentFile) =>
                                `${currentFile.name}-${currentFile.size}-${currentFile.lastModified}` !==
                                `${file.name}-${file.size}-${file.lastModified}`
                            )
                          )
                        }
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}

              {formError ? <p className="form-error">{formError}</p> : null}

              <button type="submit" className="button primary" disabled={!canSubmit}>
                {isSubmitting ? "Sending..." : "Send question"}
              </button>
            </form>

            {answer ? (
              <div className="assistant-gateway-answer">
                {answer.usedFallback ? (
                  <p className="assistant-gateway-warning">
                    Local demo fallback is shown because Assistant Gateway is not reachable.
                  </p>
                ) : null}
                <pre>{answer.answer}</pre>
                <dl>
                  <div>
                    <dt>Status</dt>
                    <dd>{answer.status}</dd>
                  </div>
                  <div>
                    <dt>Case</dt>
                    <dd>{answer.caseId}</dd>
                  </div>
                  <div>
                    <dt>Documents</dt>
                    <dd>{answer.storedDocuments.length}</dd>
                  </div>
                </dl>
                {answer.nextActions.length > 0 ? (
                  <ul>
                    {answer.nextActions.map((action) => (
                      <li key={action}>{action}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </section>

          <AssistantThread />
        </main>

        <aside className="assistant-tool-panel" aria-label={t("assistantToolsTitle")}>
          <section>
            <div className="assistant-panel-title">
              <BsLockFill aria-hidden="true" />
              <h2>{t("assistantMandatoryMcpTitle")}</h2>
            </div>
            <p>{t("assistantMandatoryMcpBody")}</p>
            <span className="assistant-status">{t("assistantMcpLocked")}</span>
          </section>

          <section>
            <h2>{t("assistantToolsTitle")}</h2>
            <ul className="assistant-capability-list">
              {capabilities.map((capability) => (
                <li key={capability}>{capability}</li>
              ))}
            </ul>
          </section>

          <section>
            <h2>{t("assistantApprovalTitle")}</h2>
            <p>{t("assistantApprovalBody")}</p>
          </section>

          <section>
            <h2>{t("assistantMetadataTitle")}</h2>
            <dl className="assistant-metadata">
              <div>
                <dt>{t("assistantMetadataGenerated")}</dt>
                <dd>{t("assistantMetadataAiDraft")}</dd>
              </div>
              <div>
                <dt>{t("assistantMetadataRisk")}</dt>
                <dd>{t("assistantMetadataRiskValue")}</dd>
              </div>
              <div>
                <dt>{t("assistantMetadataReview")}</dt>
                <dd>{t("assistantMetadataReviewValue")}</dd>
              </div>
            </dl>
          </section>
        </aside>
      </section>
    </div>
  );
};

export default AssistantWorkspace;
