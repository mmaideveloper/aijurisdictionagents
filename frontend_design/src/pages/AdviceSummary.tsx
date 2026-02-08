import React from "react";
import { useLanguage } from "../components/LanguageProvider";

const AdviceSummary: React.FC = () => {
  const { t } = useLanguage();

  return (
    <div className="page">
      <section className="section-head">
        <h1>{t("adviceTitle")}</h1>
        <p>{t("adviceSubtitle")}</p>
      </section>
      <section className="summary">
        <div className="summary-header">
          <div>
            <h3>{t("summaryTitle")}</h3>
            <p>{t("summarySubtitle")}</p>
          </div>
          <button type="button" className="button ghost">
            {t("advicePrint")}
          </button>
        </div>
        <div className="summary-grid">
          <article>
            <h4>{t("summaryFindingsTitle")}</h4>
            <ul>
              <li>{t("summaryFinding1")}</li>
              <li>{t("summaryFinding2")}</li>
              <li>{t("summaryFinding3")}</li>
            </ul>
          </article>
          <article>
            <h4>{t("summaryRisksTitle")}</h4>
            <ul>
              <li>{t("summaryRisk1")}</li>
              <li>{t("summaryRisk2")}</li>
              <li>{t("summaryRisk3")}</li>
            </ul>
          </article>
          <article>
            <h4>{t("summaryNextTitle")}</h4>
            <ul>
              <li>{t("summaryNext1")}</li>
              <li>{t("summaryNext2")}</li>
              <li>{t("summaryNext3")}</li>
            </ul>
          </article>
        </div>
      </section>
    </div>
  );
};

export default AdviceSummary;
