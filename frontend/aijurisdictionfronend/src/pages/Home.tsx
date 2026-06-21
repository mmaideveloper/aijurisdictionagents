import React from "react";
import { Link } from "react-router-dom";
import { FiMessageSquare, FiMic, FiVolume2, FiVolumeX, FiVideo } from "react-icons/fi";
import { ApiRequestError } from "../api/chatClient";
import type { BrowserSpeechSession } from "../audio/speechToText";
import {
  isBrowserSpeechAvailable,
  languageToSpeechLocale,
  startBrowserSpeechSession,
  SpeechToTextError
} from "../audio/speechToText";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";
import WorkspaceWelcome from "../components/WorkspaceWelcome";
import {
  buildLocalizedInteractionMessage,
  CaseCommunicationMode,
  CaseRole,
  useCases
} from "../state/CaseProvider";
import { caseStatusTranslationKeys } from "../state/caseStatus";

type ApiErrorState =
  | {
      key: "workspaceApiUnavailablePrefix" | "workspaceApiRequestFailedPrefix";
      detail: string;
    }
  | null;

type WorkspaceVoiceConfirmation = "yes" | "no" | null;
type SpeechType = "message" | "conversation";

const configuredSpeechType = (import.meta.env.VITE_AIJ_SPEECHTYPE ?? "message")
  .trim()
  .toLowerCase() as SpeechType;
const defaultSpeechType: SpeechType =
  configuredSpeechType === "conversation" ? "conversation" : "message";

const parseWorkspaceVoiceConfirmation = (transcript: string): WorkspaceVoiceConfirmation => {
  const normalized = transcript
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-z0-9\s]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return null;
  const tokens = normalized.split(" ");
  if (tokens.some((token) => ["ano", "yes", "ja"].includes(token))) return "yes";
  if (tokens.some((token) => ["nie", "no", "nein"].includes(token))) return "no";
  return null;
};

const stripDiacritics = (value: string): string =>
  value.normalize("NFD").replace(/\p{Diacritic}/gu, "");

const normalizeSpokenCommandText = (value: string): string =>
  stripDiacritics(value)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\s]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const sendCommandPhrases = [
  "send",
  "send message",
  "i am done",
  "that is all",
  "posli",
  "odosli",
  "odosli spravu",
  "to je vsetko",
  "senden",
  "nachricht senden"
];

const stripTrailingSendCommand = (transcript: string): { message: string; shouldSend: boolean } => {
  const normalized = normalizeSpokenCommandText(transcript);
  if (!normalized) return { message: "", shouldSend: false };
  if (sendCommandPhrases.includes(normalized)) {
    return { message: "", shouldSend: true };
  }
  const matchedPhrase = sendCommandPhrases.find((phrase) => normalized.endsWith(` ${phrase}`));
  if (!matchedPhrase) {
    return { message: transcript.trim(), shouldSend: false };
  }
  return {
    message: transcript.trim().slice(0, Math.max(0, transcript.trim().length - matchedPhrase.length)).trim(),
    shouldSend: true
  };
};

const isWorkspaceUserActor = (actor: string, t: ReturnType<typeof useLanguage>["t"]): boolean => {
  return (
    actor === t("workspaceUserLabel") ||
    actor === t("workspaceUserVoiceLabel") ||
    actor === t("workspaceUserVideoLabel")
  );
};

const Home: React.FC = () => {
  const { t, language } = useLanguage();
  const { isAuthenticated, user } = useAuth();
  const {
    cases,
    activeCase,
    hasSelectedCase,
    continueRequested,
    setContinueRequested,
    addInteraction,
    sendCaseMessage,
    setCaseRole,
    setCaseCommunicationMode
  } = useCases();
  const [draftMessage, setDraftMessage] = React.useState("");
  const [modeDraftMessage, setModeDraftMessage] = React.useState("");
  const [isSendingMessage, setIsSendingMessage] = React.useState(false);
  const [apiError, setApiError] = React.useState<ApiErrorState>(null);
  const [isRecording, setIsRecording] = React.useState(false);
  const [isMessageAudioEnabled, setIsMessageAudioEnabled] = React.useState(false);
  const [chatSpeechStatus, setChatSpeechStatus] = React.useState<string | null>(null);
  const [isAwaitingVoiceConfirmation, setIsAwaitingVoiceConfirmation] = React.useState(false);
  const [speechStatus, setSpeechStatus] = React.useState<string | null>(null);
  const speechSessionRef = React.useRef<BrowserSpeechSession | null>(null);
  const silenceTimerRef = React.useRef<number | null>(null);
  const draftMessageRef = React.useRef("");
  const modeDraftMessageRef = React.useRef("");
  const awaitingVoiceConfirmationRef = React.useRef(false);
  const chatHistoryEndRef = React.useRef<HTMLDivElement | null>(null);
  const roleOptions = React.useMemo(
    () => [
      {
        role: "AI Lawyer" as CaseRole,
        label: t("workspaceLawyerTitle"),
        intent: t("roleIntentLawyer")
      },
      {
        role: "AI Judge" as CaseRole,
        label: t("workspaceJudgeTitle"),
        intent: t("roleIntentJudge")
      },
      {
        role: "Opposing Counsel" as CaseRole,
        label: t("workspaceOpposingTitle"),
        intent: t("roleIntentOpposing")
      }
    ],
    [t]
  );
  const communicationModeOptions = React.useMemo(
    () => [
      {
        mode: "Chat" as CaseCommunicationMode,
        label: t("commsChat"),
        icon: <FiMessageSquare aria-hidden="true" />
      },
      {
        mode: "Voice" as CaseCommunicationMode,
        label: t("commsVoice"),
        icon: <FiMic aria-hidden="true" />
      },
      {
        mode: "Video" as CaseCommunicationMode,
        label: t("commsVideo"),
        icon: <FiVideo aria-hidden="true" />
      }
    ],
    [t]
  );

  React.useEffect(() => {
    draftMessageRef.current = draftMessage;
  }, [draftMessage]);

  React.useEffect(() => {
    modeDraftMessageRef.current = modeDraftMessage;
  }, [modeDraftMessage]);

  React.useEffect(() => {
    awaitingVoiceConfirmationRef.current = isAwaitingVoiceConfirmation;
  }, [isAwaitingVoiceConfirmation]);

  React.useEffect(() => {
    const latestInteraction = activeCase?.interactionHistory.at(-1);
    if (!latestInteraction || isWorkspaceUserActor(latestInteraction.actor, t)) {
      return;
    }
    chatHistoryEndRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [activeCase?.id, activeCase?.interactionHistory, t]);

  React.useEffect(() => {
    return () => {
      speechSessionRef.current?.stop();
      if (silenceTimerRef.current != null) {
        window.clearTimeout(silenceTimerRef.current);
      }
    };
  }, []);

  if (isAuthenticated) {
    const activeMatterCount = cases.filter((caseItem) => caseItem.status !== "Completed").length;

    const showWelcome = !hasSelectedCase;

    const submitMessageToApi = async (
      communicationMode: CaseCommunicationMode,
      content: string
    ): Promise<boolean> => {
      if (!activeCase) {
        return false;
      }

      const normalized = content.trim();
      if (!normalized) {
        return false;
      }

      const userActor = communicationMode === "Chat" ? "You" : `You (${communicationMode})`;
      addInteraction(activeCase.id, userActor, normalized);
      setApiError(null);
      setIsSendingMessage(true);

      try {
        const response = await sendCaseMessage({
          caseId: activeCase.id,
          content: normalized,
          communicationMode
        });
        addInteraction(activeCase.id, response.assistantActor, response.assistantMessage);
        return true;
      } catch (error) {
        const fallbackMessage = "Unknown API error.";
        const apiErrorMessage = error instanceof Error ? error.message : fallbackMessage;

        if (error instanceof ApiRequestError && error.kind === "network") {
          setApiError({
            key: "workspaceApiUnavailablePrefix",
            detail: apiErrorMessage
          });
          addInteraction(
            activeCase.id,
            "System",
            buildLocalizedInteractionMessage("workspaceApiUnavailablePrefix", {
              detail: apiErrorMessage
            })
          );
          return false;
        }

        setApiError({
          key: "workspaceApiRequestFailedPrefix",
          detail: apiErrorMessage
        });
        addInteraction(
          activeCase.id,
          "System",
          buildLocalizedInteractionMessage("workspaceApiRequestFailedPrefix", {
            detail: apiErrorMessage
          })
        );
        return false;
      } finally {
        setIsSendingMessage(false);
      }
    };

    const handleSendMessage = async (event: React.FormEvent) => {
      event.preventDefault();
      speechSessionRef.current?.stop();
      speechSessionRef.current = null;
      setIsRecording(false);
      const sent = await submitMessageToApi("Chat", draftMessage);
      if (sent) {
        setDraftMessage("");
        draftMessageRef.current = "";
      }
    };

    const speakBrowserMessage = (message: string) => {
      if (typeof window === "undefined" || !("speechSynthesis" in window)) {
        return;
      }
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(message);
      utterance.lang = languageToSpeechLocale(language);
      window.speechSynthesis.speak(utterance);
    };

    const handleMessageAudioToggle = () => {
      const nextValue = !isMessageAudioEnabled;
      setIsMessageAudioEnabled(nextValue);
      if (!nextValue) {
        speechSessionRef.current?.stop();
        speechSessionRef.current = null;
        setIsRecording(false);
        setChatSpeechStatus(null);
        return;
      }
      const guidance = t("workspaceSpeechMessageModeReady");
      setChatSpeechStatus(guidance);
      speakBrowserMessage(guidance);
    };

    const submitChatDraftFromSpeech = async (messageOverride?: string) => {
      speechSessionRef.current?.stop();
      speechSessionRef.current = null;
      setIsRecording(false);
      const message = (messageOverride ?? draftMessageRef.current).trim();
      if (!message) {
        return;
      }
      const sent = await submitMessageToApi("Chat", message);
      if (sent) {
        setDraftMessage("");
        draftMessageRef.current = "";
      }
    };

    const handleChatVoiceCapture = () => {
      if (!isMessageAudioEnabled) {
        handleMessageAudioToggle();
        return;
      }
      if (isRecording) {
        speechSessionRef.current?.stop();
        speechSessionRef.current = null;
        setIsRecording(false);
        setChatSpeechStatus(t("workspaceSpeechReviewBeforeSend", { runtime: "browser-native" }));
        return;
      }
      if (!isBrowserSpeechAvailable()) {
        setChatSpeechStatus(t("workspaceSpeechUnavailable"));
        return;
      }
      const speechLocale = languageToSpeechLocale(language);
      setIsRecording(true);
      setChatSpeechStatus(`${t("workspaceSpeechListening")} ${t("workspaceSpeechRuntimeBrowser")} (${speechLocale}).`);
      try {
        speechSessionRef.current = startBrowserSpeechSession({
          lang: speechLocale,
          onTranscript: (result) => {
            const stripped = stripTrailingSendCommand(result.transcript);
            const nextMessage = [draftMessageRef.current.trim(), stripped.message]
              .filter(Boolean)
              .join(" ")
              .trim();
            if (nextMessage) {
              draftMessageRef.current = nextMessage;
              setDraftMessage(nextMessage);
            }
            if (stripped.shouldSend) {
              void submitChatDraftFromSpeech(nextMessage);
              return;
            }
            setChatSpeechStatus(t("workspaceSpeechReviewBeforeSend", { runtime: result.runtime }));
          },
          onError: (error) => {
            if (error.code === "no-speech") {
              setChatSpeechStatus(t("workspaceSpeechNoInput"));
              return;
            }
            setChatSpeechStatus(t("workspaceSpeechError", { code: error.code }));
          },
          onEnd: () => {
            speechSessionRef.current = null;
            setIsRecording(false);
          }
        });
      } catch (error) {
        setIsRecording(false);
        if (error instanceof SpeechToTextError) {
          setChatSpeechStatus(t("workspaceSpeechError", { code: error.code }));
          return;
        }
        setChatSpeechStatus(t("workspaceSpeechError", { code: "unknown" }));
      }
    };

    const clearVoiceSilenceTimer = () => {
      if (silenceTimerRef.current != null) {
        window.clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
    };

    const scheduleVoiceSilencePrompt = () => {
      clearVoiceSilenceTimer();
      if (!modeDraftMessageRef.current.trim()) {
        return;
      }
      silenceTimerRef.current = window.setTimeout(() => {
        setIsAwaitingVoiceConfirmation(true);
        setSpeechStatus(t("workspaceSpeechAnswerConfirmationPrompt"));
      }, 10_000);
    };

    const stopVoiceCapture = () => {
      clearVoiceSilenceTimer();
      speechSessionRef.current?.stop();
      speechSessionRef.current = null;
      setIsRecording(false);
      setIsAwaitingVoiceConfirmation(false);
    };

    const appendVoiceTranscript = (transcript: string) => {
      setModeDraftMessage((current) => {
        const next = [current.trim(), transcript.trim()].filter(Boolean).join(" ").trim();
        modeDraftMessageRef.current = next;
        return next;
      });
    };

    const handleModeMessageSend = async () => {
      if (!activeCase) {
        return;
      }
      stopVoiceCapture();
      const sent = await submitMessageToApi(
        activeCase.selectedCommunicationMode,
        modeDraftMessageRef.current
      );
      if (sent) {
        modeDraftMessageRef.current = "";
        setModeDraftMessage("");
      }
    };

    const handleVoiceConfirmationTranscript = async (transcript: string) => {
      const confirmation = parseWorkspaceVoiceConfirmation(transcript);
      if (confirmation === "yes") {
        stopVoiceCapture();
        await handleModeMessageSend();
        return;
      }
      if (confirmation === "no") {
        setIsAwaitingVoiceConfirmation(false);
        setSpeechStatus(t("workspaceSpeechContinueDraft"));
        scheduleVoiceSilencePrompt();
        return;
      }
      setSpeechStatus(t("workspaceSpeechAnswerConfirmationPrompt"));
    };

    const handleVoiceCapture = async () => {
      if (isRecording) {
        stopVoiceCapture();
        setSpeechStatus(t("workspaceSpeechReviewBeforeSend", { runtime: "browser-native" }));
        return;
      }
      if (!isBrowserSpeechAvailable()) {
        setSpeechStatus(t("workspaceSpeechUnavailable"));
        return;
      }
      setIsRecording(true);
      setIsAwaitingVoiceConfirmation(false);
      const speechLocale = languageToSpeechLocale(language);
      setSpeechStatus(
        `${t("workspaceSpeechListening")} ${t("workspaceSpeechRuntimeBrowser")} (${speechLocale}).`
      );
      try {
        speechSessionRef.current = startBrowserSpeechSession({
          lang: speechLocale,
          onTranscript: (result) => {
            if (awaitingVoiceConfirmationRef.current) {
              void handleVoiceConfirmationTranscript(result.transcript);
              return;
            }
            appendVoiceTranscript(result.transcript);
            setSpeechStatus(t("workspaceSpeechReviewBeforeSend", { runtime: result.runtime }));
            scheduleVoiceSilencePrompt();
          },
          onError: (error) => {
            if (error.code === "no-speech") {
              scheduleVoiceSilencePrompt();
              return;
            }
            setSpeechStatus(t("workspaceSpeechError", { code: error.code }));
          },
          onEnd: () => {
            speechSessionRef.current = null;
            setIsRecording(false);
          }
        });
      } catch (error) {
        if (error instanceof SpeechToTextError) {
          setSpeechStatus(t("workspaceSpeechError", { code: error.code }));
        } else {
          setSpeechStatus(t("workspaceSpeechError", { code: "unknown" }));
        }
        setIsRecording(false);
      }
    };

    return (
      <div className="page workspace-page">
        <section className="workspace-shell">
          <header className="workspace-header">
            <div>
              <h1>{t("workspaceHeaderTitle")}</h1>
              <p className="hint">
                {t("workspaceWelcomeBack", { name: user?.name ?? t("commonUser") })}
              </p>
            </div>
            <div className="workspace-meta">
              <span className="pill active">{t("workspaceSignedIn")}</span>
              <span className="pill">{t("workspaceActiveMatters", { count: activeMatterCount })}</span>
            </div>
          </header>

          <div className="workspace-grid">

            <section className="workspace-center">
              <div className="panel-card">
                {showWelcome ? (
                  <WorkspaceWelcome
                    onContinue={() => setContinueRequested(true)}
                    showHint={continueRequested}
                  />
                ) : (
                  <>
                    <div className="panel-card__header">
                      <div className="workspace-case-header">
                        <h2>{activeCase?.title ?? t("workspaceDefaultActiveCase")}</h2>
                        <p className="hint">{activeCase?.description}</p>
                      </div>
                      <div className="workspace-case-meta">
                        <span className="pill">
                          {activeCase ? t(caseStatusTranslationKeys[activeCase.status]) : t("workspaceStatusInProgress")}
                        </span>
                        <span className="pill">{activeCase?.workspace.meta ?? t("workspaceDefaultActiveCase")}</span>
                      </div>
                    </div>
                    <div className="workspace-stream">
                      {activeCase?.selectedCommunicationMode === "Chat" ? (
                        <div className="workspace-chat">
                          <div className="workspace-chat__history">
                            {activeCase?.interactionHistory.map((item) => {
                              const isUser = isWorkspaceUserActor(item.actor, t);
                              return (
                                <article
                                  key={item.id}
                                  className={`chat-message${isUser ? " chat-message--user" : ""}`}
                                >
                                  <div className="chat-message__meta">
                                    <strong>{item.actor}</strong>
                                    <span>{new Date(item.createdAt).toLocaleString()}</span>
                                  </div>
                                  <p>{item.message}</p>
                                </article>
                              );
                            })}
                            <div ref={chatHistoryEndRef} aria-hidden="true" />
                          </div>
                          <form className="workspace-chat__composer" onSubmit={handleSendMessage}>
                            <input
                              type="text"
                              value={draftMessage}
                              onChange={(event) => {
                                setDraftMessage(event.target.value);
                                draftMessageRef.current = event.target.value;
                              }}
                              placeholder={t("workspaceChatPlaceholder")}
                              disabled={isSendingMessage}
                            />
                            {defaultSpeechType === "message" ? (
                              <>
                                <button
                                  type="button"
                                  className="button secondary icon-button"
                                  onClick={handleMessageAudioToggle}
                                  disabled={isSendingMessage}
                                  aria-label={
                                    isMessageAudioEnabled
                                      ? t("workspaceSpeechDisableAudio")
                                      : t("workspaceSpeechEnableAudio")
                                  }
                                  title={
                                    isMessageAudioEnabled
                                      ? t("workspaceSpeechDisableAudio")
                                      : t("workspaceSpeechEnableAudio")
                                  }
                                >
                                  {isMessageAudioEnabled ? <FiVolume2 aria-hidden="true" /> : <FiVolumeX aria-hidden="true" />}
                                </button>
                                <button
                                  type="button"
                                  className="button secondary icon-button"
                                  onClick={handleChatVoiceCapture}
                                  disabled={isSendingMessage || !isMessageAudioEnabled}
                                  aria-label={
                                    isRecording
                                      ? t("workspaceSpeechStopCapture")
                                      : t("workspaceSpeechCapture")
                                  }
                                  title={
                                    isRecording
                                      ? t("workspaceSpeechStopCapture")
                                      : t("workspaceSpeechCapture")
                                  }
                                >
                                  <FiMic aria-hidden="true" />
                                </button>
                              </>
                            ) : null}
                            <button
                              type="submit"
                              className="button primary"
                              disabled={isSendingMessage || !draftMessage.trim()}
                            >
                              {isSendingMessage ? t("workspaceSending") : t("workspaceChatSend")}
                            </button>
                          </form>
                          <p className="workspace-chat__status">
                            {isSendingMessage ? t("workspaceWaitingForApi") : t("workspaceConnectedApi")}
                          </p>
                          {chatSpeechStatus ? <p className="hint">{chatSpeechStatus}</p> : null}
                          {apiError ? (
                            <p className="workspace-chat__status workspace-chat__status--error">
                              {t("workspaceApiErrorLabel")}: {t(apiError.key, { detail: apiError.detail })}
                            </p>
                          ) : null}
                        </div>
                      ) : (
                        <article className="workspace-mode-card">
                          <h3>
                            {activeCase?.selectedCommunicationMode === "Voice"
                              ? t("commsVoice")
                              : t("commsVideo")}
                          </h3>
                          <p>
                            {activeCase?.selectedCommunicationMode === "Voice"
                              ? t("commsVoiceBody")
                              : t("commsVideoBody")}
                          </p>
                          <label className="workspace-mode-card__input-label" htmlFor="mode-transcript">
                            {t("workspaceTranscriptLabel")}
                          </label>
                          <textarea
                            id="mode-transcript"
                            className="workspace-mode-card__textarea"
                            value={modeDraftMessage}
                            onChange={(event) => setModeDraftMessage(event.target.value)}
                            placeholder={
                              activeCase?.selectedCommunicationMode === "Voice"
                                ? t("workspaceVoiceTranscriptPlaceholder")
                                : t("workspaceVideoTranscriptPlaceholder")
                            }
                            disabled={isSendingMessage}
                          />
                          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                            <button
                              type="button"
                              className="button secondary"
                              onClick={handleVoiceCapture}
                              disabled={isSendingMessage}
                            >
                              {isRecording ? t("workspaceSpeechStopCapture") : t("workspaceSpeechCapture")}
                            </button>
                            <button
                              type="button"
                              className="button primary"
                              onClick={handleModeMessageSend}
                              disabled={isSendingMessage || !modeDraftMessage.trim()}
                            >
                              {isSendingMessage
                                ? t("workspaceSending")
                                : activeCase?.selectedCommunicationMode === "Voice"
                                  ? t("workspaceSendVoiceTranscript")
                                  : t("workspaceSendVideoTranscript")}
                            </button>
                          </div>
                          {speechStatus ? <p className="hint">{speechStatus}</p> : null}
                          {apiError ? (
                            <p className="workspace-chat__status workspace-chat__status--error">
                              {t("workspaceApiErrorLabel")}: {t(apiError.key, { detail: apiError.detail })}
                            </p>
                          ) : null}
                        </article>
                      )}
                    </div>
                  </>
                )}
              </div>
            </section>

            <aside className="workspace-panel workspace-panel--right">
              <div className="panel-card">
                <div className="panel-card__header">
                  <h2>{t("workspaceConfigurations")}</h2>
                </div>
                <div className="config-list">
                  <fieldset className="role-selector" disabled={!activeCase}>
                    <legend>{t("commsTitle")}</legend>
                    <p className="hint">{t("commsSubtitle")}</p>
                    <div className="segment-control" role="radiogroup">
                      {communicationModeOptions.map((option) => {
                        const isActive = activeCase?.selectedCommunicationMode === option.mode;
                        return (
                          <button
                            key={option.mode}
                            type="button"
                            className={`segment-control__option${isActive ? " is-active" : ""}`}
                            aria-pressed={isActive}
                            aria-label={option.label}
                            title={option.label}
                            onClick={() => {
                              if (activeCase) {
                                setCaseCommunicationMode(activeCase.id, option.mode);
                              }
                            }}
                          >
                            <span className="segment-control__icon">{option.icon}</span>
                          </button>
                        );
                      })}
                    </div>
                  </fieldset>
                  <fieldset className="role-selector" disabled={!activeCase}>
                    <legend>{t("roleSelectorTitle")}</legend>
                    <p className="hint">{t("roleSelectorHint")}</p>
                    <div className="role-options" role="radiogroup">
                      {roleOptions.map((option) => {
                        const isActive = activeCase?.selectedRole === option.role;
                        return (
                          <label
                            key={option.role}
                            className={`role-option${isActive ? " is-active" : ""}`}
                          >
                            <input
                              type="radio"
                              name={`case-role-${activeCase?.id ?? "current"}`}
                              value={option.role}
                              checked={isActive}
                              onChange={() => {
                                if (activeCase) {
                                  setCaseRole(activeCase.id, option.role);
                                }
                              }}
                            />
                            <span className="role-option__label">{option.label}</span>
                            <span className="role-option__intent">{option.intent}</span>
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                </div>
              </div>
            </aside>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-text">
          <span className="pill reveal" style={{ "--delay": "0ms" } as React.CSSProperties}>
            {t("heroEyebrow")}
          </span>
          <h1 className="reveal" style={{ "--delay": "120ms" } as React.CSSProperties}>
            {t("heroTitle")}
          </h1>
          <p className="lede reveal" style={{ "--delay": "220ms" } as React.CSSProperties}>
            {t("heroSubtitle")}
          </p>
          <div className="hero-actions reveal" style={{ "--delay": "320ms" } as React.CSSProperties}>
            <Link to="/app" className="button primary">
              {t("heroPrimary")}
            </Link>
            <Link to="/pricing" className="button ghost">
              {t("heroSecondary")}
            </Link>
          </div>
          <div className="metric-grid reveal" style={{ "--delay": "420ms" } as React.CSSProperties}>
            <div>
              <strong>4</strong>
              <span>{t("metricAgentRoles")}</span>
            </div>
            <div>
              <strong>12</strong>
              <span>{t("metricWorkflowNodes")}</span>
            </div>
            <div>
              <strong>24/7</strong>
              <span>{t("metricAvailability")}</span>
            </div>
          </div>
        </div>
        <div className="hero-panel reveal" style={{ "--delay": "200ms" } as React.CSSProperties}>
          <div className="panel-header">
            <span>{t("heroPanelTitle")}</span>
            <span className="status">{t("heroPanelStatus")}</span>
          </div>
          <div className="panel-body">
            <div className="panel-item">
              <strong>{t("featureCase")}</strong>
              <p>{t("featureCaseBody")}</p>
            </div>
            <div className="panel-item">
              <strong>{t("featureWorkspace")}</strong>
              <p>{t("featureWorkspaceBody")}</p>
            </div>
            <div className="panel-item">
              <strong>{t("featureAdvice")}</strong>
              <p>{t("featureAdviceBody")}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>{t("sectionCapabilities")}</h2>
          <p>{t("sectionPricingLead")}</p>
        </div>
        <div className="card-grid">
          <article className="card">
            <h3>{t("featureCase")}</h3>
            <p>{t("featureCaseBody")}</p>
          </article>
          <article className="card">
            <h3>{t("featureWorkspace")}</h3>
            <p>{t("featureWorkspaceBody")}</p>
          </article>
          <article className="card">
            <h3>{t("featureAdvice")}</h3>
            <p>{t("featureAdviceBody")}</p>
          </article>
          <article className="card">
            <h3>{t("featureComms")}</h3>
            <p>{t("featureCommsBody")}</p>
          </article>
          <article className="card">
            <h3>{t("featureSubscriptions")}</h3>
            <p>{t("featureSubscriptionsBody")}</p>
          </article>
          <article className="card">
            <h3>{t("featureLawValidation")}</h3>
            <p>{t("featureLawValidationBody")}</p>
          </article>
        </div>
      </section>

      <section className="section alt">
        <div className="section-head">
          <h2>{t("sectionWorkflow")}</h2>
          <p>{t("workflowStep2Body")}</p>
        </div>
        <div className="timeline">
          <div className="timeline-step">
            <span>01</span>
            <div>
              <h3>{t("workflowStep1Title")}</h3>
              <p>{t("workflowStep1Body")}</p>
            </div>
          </div>
          <div className="timeline-step">
            <span>02</span>
            <div>
              <h3>{t("workflowStep2Title")}</h3>
              <p>{t("workflowStep2Body")}</p>
            </div>
          </div>
          <div className="timeline-step">
            <span>03</span>
            <div>
              <h3>{t("workflowStep3Title")}</h3>
              <p>{t("workflowStep3Body")}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>{t("sectionCommunications")}</h2>
          <p>{t("commsSubtitle")}</p>
        </div>
        <div className="card-grid three">
          <article className="card">
            <h3>{t("commsChat")}</h3>
            <p>{t("commsChatBody")}</p>
          </article>
          <article className="card">
            <h3>{t("commsVoice")}</h3>
            <p>{t("commsVoiceBody")}</p>
          </article>
          <article className="card">
            <h3>{t("commsVideo")}</h3>
            <p>{t("commsVideoBody")}</p>
          </article>
        </div>
      </section>

      <section className="section alt">
        <div className="section-head">
          <h2>{t("sectionLawOps")}</h2>
          <p>{t("featureLawRecommendationBody")}</p>
        </div>
        <div className="card-grid two">
          <article className="card">
            <h3>{t("lawOpsValidationTitle")}</h3>
            <p>{t("lawOpsValidationBody")}</p>
            <Link to="/app/law-validation" className="button ghost">
              {t("navLawValidation")}
            </Link>
          </article>
          <article className="card">
            <h3>{t("lawOpsRecommendationTitle")}</h3>
            <p>{t("lawOpsRecommendationBody")}</p>
            <Link to="/app/law-recommendation" className="button ghost">
              {t("navLawRecommendation")}
            </Link>
          </article>
        </div>
      </section>

      <section className="section cta">
        <div className="cta-card">
          <div>
            <h2>{t("sectionCTA")}</h2>
            <p>{t("appDashboardSubtitle")}</p>
          </div>
          <div className="cta-actions">
            <Link to="/auth" className="button primary">
              {t("navAuth")}
            </Link>
            <Link to="/pricing" className="button ghost">
              {t("navPricing")}
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
};

export default Home;
