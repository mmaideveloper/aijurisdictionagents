import React from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "./LanguageProvider";

type WorkspaceWelcomeProps = {
  onContinue: () => void;
  showHint: boolean;
};

const WorkspaceWelcome: React.FC<WorkspaceWelcomeProps> = ({ onContinue, showHint }) => {
  const { t } = useLanguage();

  return (
    <div className="workspace-welcome">
      <p className="workspace-welcome__eyebrow">{t("workspaceWelcomeEyebrow")}</p>
      <div className="workspace-welcome__actions">
        <Link to="/app/case" className="button primary">
          {t("workspaceWelcomeStartCase")}
        </Link>
        <button type="button" className="button ghost" onClick={onContinue}>
          {t("workspaceWelcomeContinueCase")}
        </button>
      </div>
      {showHint ? (
        <p className="workspace-welcome__hint">{t("workspaceWelcomeHint")}</p>
      ) : null}
    </div>
  );
};

export default WorkspaceWelcome;
