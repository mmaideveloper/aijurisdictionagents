import React from "react";
import { useLanguage } from "../components/LanguageProvider";

const LawValidation: React.FC = () => {
  const { t } = useLanguage();

  return (
    <div className="page">
      <section className="section-head">
        <h1>{t("validationTitle")}</h1>
        <p>{t("validationSubtitle")}</p>
      </section>
      <section className="case-grid">
        <div className="card">
          <h3>{t("validationDetailsTitle")}</h3>
          <form className="form">
            <label>
              <span>{t("validationLawTitleLabel")}</span>
              <input type="text" placeholder={t("validationLawTitlePlaceholder")} />
            </label>
            <label>
              <span>{t("validationRegionLabel")}</span>
              <input type="text" placeholder={t("validationRegionPlaceholder")} />
            </label>
            <label>
              <span>{t("validationSummaryLabel")}</span>
              <textarea rows={4} placeholder={t("validationSummaryPlaceholder")} />
            </label>
          </form>
        </div>
        <div className="card">
          <h3>{t("validationUploadTitle")}</h3>
          <div className="upload">
            <p>{t("validationUploadBody")}</p>
            <button type="button" className="button ghost">{t("validationUploadButton")}</button>
          </div>
          <button type="button" className="button primary full">{t("validationRunButton")}</button>
        </div>
      </section>
    </div>
  );
};

export default LawValidation;
