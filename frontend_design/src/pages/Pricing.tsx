import React, { useState } from "react";
import { useLanguage } from "../components/LanguageProvider";
import { BillingCadence, plans } from "../data/plans";

const Pricing: React.FC = () => {
  const { t } = useLanguage();
  const [cadence, setCadence] = useState<BillingCadence>("monthly");

  return (
    <div className="page">
      <section className="section-head pricing-head">
        <h1>{t("pricingTitle")}</h1>
        <p>{t("pricingSubtitle")}</p>
        <div className="toggle">
          <button
            type="button"
            className={cadence === "monthly" ? "active" : ""}
            onClick={() => setCadence("monthly")}
          >
            {t("pricingMonthly")}
          </button>
          <button
            type="button"
            className={cadence === "yearly" ? "active" : ""}
            onClick={() => setCadence("yearly")}
          >
            {t("pricingYearly")}
          </button>
        </div>
        <span className="hint">{t("pricingNote")}</span>
      </section>

      <section className="card-grid pricing-grid">
        {plans.map((plan) => {
          const price = cadence === "monthly" ? plan.priceMonthly : plan.priceYearly;
          const planName = t(plan.nameKey);
          return (
            <article key={plan.id} className={`card pricing-card ${plan.highlight ? "highlight" : ""}`}>
              <div>
                <h3>{planName}</h3>
                <p className="price">
                  €{price}
                  <span>/{cadence === "monthly" ? t("pricingPerMonth") : t("pricingPerYear")}</span>
                </p>
                <p>{t(plan.descriptionKey)}</p>
              </div>
              <ul>
                {plan.featureKeys.map((featureKey) => (
                  <li key={featureKey}>{t(featureKey)}</li>
                ))}
              </ul>
              <button type="button" className="button ghost">
                {t("pricingChoose").replace("{plan}", planName)}
              </button>
            </article>
          );
        })}
      </section>
    </div>
  );
};

export default Pricing;
