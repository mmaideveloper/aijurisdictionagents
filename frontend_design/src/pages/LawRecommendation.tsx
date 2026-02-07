import React from "react";
import { useLanguage } from "../components/LanguageProvider";

const LawRecommendation: React.FC = () => {
  const { t } = useLanguage();

  return (
    <div className="page">
      <section className="section-head">
        <h1>{t("recommendationTitle")}</h1>
        <p>{t("recommendationSubtitle")}</p>
      </section>
      <section className="card-grid two">
        <div className="card">
          <h3>{t("recommendationProblemTitle")}</h3>
          <textarea rows={8} placeholder={t("recommendationProblemPlaceholder")} />
          <button type="button" className="button primary">
            {t("recommendationGenerateButton")}
          </button>
        </div>
        <div className="card">
          <h3>{t("recommendationSuggestedTitle")}</h3>
          <div className="recommendation-list">
            <div>
              <strong>{t("recommendationItem1Title")}</strong>
              <p>{t("recommendationItem1Body")}</p>
            </div>
            <div>
              <strong>{t("recommendationItem2Title")}</strong>
              <p>{t("recommendationItem2Body")}</p>
            </div>
            <div>
              <strong>{t("recommendationItem3Title")}</strong>
              <p>{t("recommendationItem3Body")}</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default LawRecommendation;
