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
import { ApiRequestError, createChatSession, replyToSession } from "../api/chatClient";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";

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
