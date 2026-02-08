import React from "react";
import { useLanguage } from "../components/LanguageProvider";

const LawyerWorkspace: React.FC = () => {
  const { t } = useLanguage();

  return (
    <div className="page">
      <section className="section-head">
        <h1>{t("workspaceTitle")}</h1>
        <p>{t("workspaceSubtitle")}</p>
      </section>
      <section className="workspace-grid">
        <div className="card">
          <h3>{t("workspaceLawyerTitle")}</h3>
          <div className="chat">
            <p><strong>{t("workspaceLawyerTitle")}:</strong> {t("workspaceLawyerMsg1")}</p>
            <p><strong>{t("workspaceUserLabel")}:</strong> {t("workspaceLawyerMsg2")}</p>
            <p><strong>{t("workspaceLawyerTitle")}:</strong> {t("workspaceLawyerMsg3")}</p>
          </div>
          <input type="text" placeholder={t("workspaceLawyerPlaceholder")} />
        </div>
        <div className="card">
          <h3>{t("workspaceJudgeTitle")}</h3>
          <div className="chat">
            <p><strong>{t("workspaceJudgeTitle")}:</strong> {t("workspaceJudgeMsg1")}</p>
            <p><strong>{t("workspaceUserLabel")}:</strong> {t("workspaceJudgeMsg2")}</p>
            <p><strong>{t("workspaceJudgeTitle")}:</strong> {t("workspaceJudgeMsg3")}</p>
          </div>
          <input type="text" placeholder={t("workspaceJudgePlaceholder")} />
        </div>
        <div className="card">
          <h3>{t("workspaceOpposingTitle")}</h3>
          <div className="chat">
            <p><strong>{t("workspaceOpposingTitle")}:</strong> {t("workspaceOpposingMsg1")}</p>
            <p><strong>{t("workspaceUserLabel")}:</strong> {t("workspaceOpposingMsg2")}</p>
            <p><strong>{t("workspaceOpposingTitle")}:</strong> {t("workspaceOpposingMsg3")}</p>
          </div>
          <input type="text" placeholder={t("workspaceOpposingPlaceholder")} />
        </div>
      </section>
    </div>
  );
};

export default LawyerWorkspace;
