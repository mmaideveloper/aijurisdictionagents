import React from "react";
import { useLanguage } from "../components/LanguageProvider";
import { plans } from "../data/plans";

const Pricing: React.FC = () => {
  const { t } = useLanguage();
  const activePlans = plans.filter((plan) => !plan.disabled);

  return (
    <div className="page">
      <section className="section-head pricing-head">
        <h1>{t("pricingTitle")}</h1>
        <p>{t("pricingSubtitle")}</p>
        <span className="hint">{t("pricingNote")}</span>
      </section>

      <section className="card-grid pricing-grid">
        {activePlans.map((plan) => {
          const planName = t(plan.nameKey);
          return (
            <article
              key={plan.id}
              className={`card pricing-card ${plan.highlight ? "highlight" : ""} ${plan.disabled ? "disabled" : ""}`}
            >
              <div>
                <h3>{planName}</h3>
                <p className="price">{t(plan.priceLabelKey)}</p>
                <p>{t(plan.descriptionKey)}</p>
              </div>
              <ul>
                {plan.featureKeys.map((featureKey) => (
                  <li key={featureKey}>{t(featureKey)}</li>
                ))}
              </ul>
              <button type="button" className="button ghost" disabled={plan.disabled}>
                {plan.disabled ? t("pricingComingSoon") : t("pricingChoose").replace("{plan}", planName)}
              </button>
            </article>
          );
        })}
      </section>
    </div>
  );
};

export default Pricing;
