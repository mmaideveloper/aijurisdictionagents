import React, { useState } from "react";
import { useLanguage } from "../components/LanguageProvider";
import { BillingCadence, plans } from "../data/plans";

const Profile: React.FC = () => {
  const { t } = useLanguage();
  const [cadence, setCadence] = useState<BillingCadence>("monthly");
  const [plan, setPlan] = useState(plans[0]?.id ?? "free");
  const selectedPlan = plans.find((option) => option.id === plan) ?? plans[0];

  return (
    <div className="page">
      <section className="section-head">
        <h1>{t("profileTitle")}</h1>
        <p>{t("profileSubtitle")}</p>
      </section>
      <section className="card-grid two">
        <div className="card">
          <h3>{t("profileBilling")}</h3>
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
          <p className="hint">
            {t("profileCadenceCurrent")}: {cadence === "monthly" ? t("pricingMonthly") : t("pricingYearly")}
          </p>
        </div>
        <div className="card">
          <h3>{t("profilePlan")}</h3>
          <div className="plan-selector">
            {plans.map((option) => (
              <button
                key={option.id}
                type="button"
                className={`pill ${plan === option.id ? "active" : ""}`}
                onClick={() => setPlan(option.id)}
              >
                {t(option.nameKey)}
              </button>
            ))}
          </div>
          <p className="hint">
            {t("profilePlanSelected")}: {selectedPlan ? t(selectedPlan.nameKey) : t("planFreeName")}
          </p>
        </div>
      </section>
      <button type="button" className="button primary">
        {t("profileSave")}
      </button>
    </div>
  );
};

export default Profile;
