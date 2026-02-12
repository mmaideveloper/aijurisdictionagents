import React from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/mockAuth";
import { useLanguage } from "../components/LanguageProvider";
import WorkspaceWelcome from "../components/WorkspaceWelcome";
import { CaseRole, useCases } from "../state/CaseProvider";

const Home: React.FC = () => {
  const { t } = useLanguage();
  const { isAuthenticated, user } = useAuth();
  const {
    cases,
    activeCase,
    hasSelectedCase,
    continueRequested,
    setContinueRequested,
    addInteraction,
    setCaseRole
  } = useCases();
  const [draftMessage, setDraftMessage] = React.useState("");
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

  if (isAuthenticated) {
    const activeMatterCount = cases.filter((caseItem) => caseItem.status !== "Completed").length;

    const showWelcome = !hasSelectedCase;

    const handleSendMessage = (event: React.FormEvent) => {
      event.preventDefault();
      if (!activeCase || !draftMessage.trim()) {
        return;
      }
      addInteraction(activeCase.id, "You", draftMessage.trim());
      setDraftMessage("");
    };

    return (
      <div className="page workspace-page">
        <section className="workspace-shell">
          <header className="workspace-header">
            <div>
              <h1>Workspace</h1>
              <p className="hint">
                Welcome back, {user?.name ?? "Admin"}. Pick a case to continue your work.
              </p>
            </div>
            <div className="workspace-meta">
              <span className="pill active">Signed in</span>
              <span className="pill">{activeMatterCount} active matters</span>
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
                        <h2>{activeCase?.title ?? "Active Case"}</h2>
                        <p className="hint">{activeCase?.description}</p>
                      </div>
                      <div className="workspace-case-meta">
                        <span className="pill">{activeCase?.status ?? "In progress"}</span>
                        <span className="pill">{activeCase?.workspace.meta ?? "Case"}</span>
                      </div>
                    </div>
                    <div className="workspace-stream">
                      <div className="workspace-chat">
                        <div className="workspace-chat__history">
                          {activeCase?.interactionHistory.map((item) => {
                            const isUser = item.actor === "You";
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
                        </div>
                        <form className="workspace-chat__composer" onSubmit={handleSendMessage}>
                          <input
                            type="text"
                            value={draftMessage}
                            onChange={(event) => setDraftMessage(event.target.value)}
                            placeholder="Type your message..."
                          />
                          <button type="submit" className="button primary">
                            Send
                          </button>
                        </form>
                      </div>
                      <article className="workspace-callout">
                        <h3>Next recommended action</h3>
                        <p>{activeCase?.workspace.nextAction}</p>
                        <button type="button" className="button primary">Start voice session</button>
                      </article>
                    </div>
                  </>
                )}
              </div>
            </section>

            <aside className="workspace-panel workspace-panel--right">
              <div className="panel-card">
                <div className="panel-card__header">
                  <h2>Configurations</h2>
                </div>
                <div className="config-list">
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
                  <div className="config-actions">
                    <button type="button" className="button ghost full">Edit settings</button>
                    <button type="button" className="button primary full">Run evaluation</button>
                  </div>
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
