import React from "react";
import { useLanguage } from "../components/LanguageProvider";

const CaseIntake: React.FC = () => {
  const { t } = useLanguage();

  return (
    <div className="page">
      <section className="section-head">
        <h1>{t("caseTitle")}</h1>
        <p>{t("caseSubtitle")}</p>
      </section>
      <section className="case-grid">
        <div className="card">
          <h3>{t("caseDetailsTitle")}</h3>
          <form className="form">
            <label>
              <span>{t("caseNameLabel")}</span>
              <input type="text" placeholder={t("caseNamePlaceholder")} />
            </label>
            <label>
              <span>{t("caseJurisdiction")}</span>
              <input type="text" placeholder={t("caseJurisdictionPlaceholder")} />
            </label>
            <label>
              <span>{t("caseOpposingLabel")}</span>
              <input type="text" placeholder={t("caseOpposingPlaceholder")} />
            </label>
          </form>
        </div>
        <div className="card">
          <h3>{t("caseUpload")}</h3>
          <div className="upload">
            <p>{t("caseUploadBody")}</p>
            <button type="button" className="button ghost">
              {t("caseUploadButton")}
            </button>
          </div>
          <button type="button" className="button primary full">
            {t("caseStartChat")}
          </button>
        </div>
      </section>
    </div>
  );
};

export default CaseIntake;
