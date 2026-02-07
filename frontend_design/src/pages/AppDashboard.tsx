import React from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "../components/LanguageProvider";

const AppDashboard: React.FC = () => {
  const { t } = useLanguage();

  return (
    <div className="page">
      <section className="section-head">
        <h1>{t("appDashboardTitle")}</h1>
        <p>{t("appDashboardSubtitle")}</p>
      </section>
      <section className="card-grid">
        <article className="card">
          <h3>{t("caseTitle")}</h3>
          <p>{t("caseSubtitle")}</p>
          <Link className="button ghost" to="/app/case">
            {t("caseTitle")}
          </Link>
        </article>
        <article className="card">
          <h3>{t("workspaceTitle")}</h3>
          <p>{t("workspaceSubtitle")}</p>
          <Link className="button ghost" to="/app/workspace">
            {t("workspaceTitle")}
          </Link>
        </article>
        <article className="card">
          <h3>{t("adviceTitle")}</h3>
          <p>{t("adviceSubtitle")}</p>
          <Link className="button ghost" to="/app/advice">
            {t("adviceTitle")}
          </Link>
        </article>
        <article className="card">
          <h3>{t("commsTitle")}</h3>
          <p>{t("commsSubtitle")}</p>
          <Link className="button ghost" to="/app/communications">
            {t("commsTitle")}
          </Link>
        </article>
        <article className="card">
          <h3>{t("validationTitle")}</h3>
          <p>{t("validationSubtitle")}</p>
          <Link className="button ghost" to="/app/law-validation">
            {t("validationTitle")}
          </Link>
        </article>
        <article className="card">
          <h3>{t("recommendationTitle")}</h3>
          <p>{t("recommendationSubtitle")}</p>
          <Link className="button ghost" to="/app/law-recommendation">
            {t("recommendationTitle")}
          </Link>
        </article>
        <article className="card">
          <h3>{t("profileTitle")}</h3>
          <p>{t("profileSubtitle")}</p>
          <Link className="button ghost" to="/app/profile">
            {t("profileTitle")}
          </Link>
        </article>
      </section>
    </div>
  );
};

export default AppDashboard;
