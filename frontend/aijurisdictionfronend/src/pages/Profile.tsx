import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLanguage } from "../components/LanguageProvider";
import { useAuth } from "../auth/webAuth";
import { BillingCadence, plans } from "../data/plans";
import { useCases } from "../state/CaseProvider";
import { caseStatusTranslationKeys } from "../state/caseStatus";

interface ProfileField {
  label: string;
  value: string;
}

const Profile: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const { user } = useAuth();
  const { cases, documents, selectCase } = useCases();
  const [cadence, setCadence] = useState<BillingCadence>("monthly");
  const [plan, setPlan] = useState(plans[0]?.id ?? "free");
  const selectedPlan = plans.find((option) => option.id === plan) ?? plans[0];
  const openedCases = cases.filter((caseItem) => caseItem.status !== "Completed");

  const firstNameCandidate = user?.firstName ?? user?.name?.split(" ")[0];
  const parsedLastName = user?.name?.split(" ").slice(1).join(" ");
  const lastNameCandidate = user?.lastName ?? parsedLastName;
  const firstName =
    firstNameCandidate && firstNameCandidate.trim().length > 0
      ? firstNameCandidate
      : t("profileNotAvailable");
  const lastName =
    lastNameCandidate && lastNameCandidate.trim().length > 0
      ? lastNameCandidate
      : t("profileNotAvailable");
  const email = user?.email ?? t("profileNotAvailable");
  const role = user?.role ?? t("profileOptionalPending");
  const accountCreatedAt = user?.accountCreatedAt ?? t("profileOptionalPending");

  const fields: ProfileField[] = [
    { label: t("profileFieldFirstName"), value: firstName },
    { label: t("profileFieldLastName"), value: lastName },
    { label: t("profileFieldEmail"), value: email },
    { label: t("profileFieldRole"), value: role },
    { label: t("profileFieldAccountCreated"), value: accountCreatedAt }
  ];

  return (
    <div className="page profile-page">
      <section className="section-head">
        <h1>{t("profileTitle")}</h1>
        <p>{t("profileSubtitle")}</p>
      </section>
      <section className="profile-shell">
        <aside className="profile-side-panels">
          <article className="card">
            <h2>{t("profileBilling")}</h2>
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
          </article>
          <article className="card">
            <h2>{t("profileOpenedCasesTitle")}</h2>
            <p className="hint">{t("profileOpenedCasesSubtitle")}</p>
            {openedCases.length > 0 ? (
              <ul className="profile-case-list">
                {openedCases.map((caseItem) => (
                  <li key={caseItem.id} className="profile-case-item">
                    <button
                      type="button"
                      className="profile-case-button"
                      onClick={() => {
                        selectCase(caseItem.id);
                        navigate("/");
                      }}
                    >
                      <span>{caseItem.title}</span>
                      <small>{t(caseStatusTranslationKeys[caseItem.status])}</small>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="hint">{t("profileOpenedCasesEmpty")}</p>
            )}
          </article>
          <article className="card">
            <h2>{t("profileDocumentsTitle")}</h2>
            <p className="hint">{t("profileDocumentsSubtitle")}</p>
            {documents.length > 0 ? (
              <ul className="profile-document-list">
                {documents.map((document) => (
                  <li key={document.id} className="profile-document-item">
                    <div>
                      <strong>{document.originalFilename}</strong>
                      <small>
                        {t("profileDocumentCaseLabel")}: {document.caseTitle}
                      </small>
                    </div>
                    <small className="profile-document-meta">
                      {document.sizeLabel}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="hint">{t("profileDocumentsEmpty")}</p>
            )}
          </article>
        </aside>
        <article className="profile-details card">
          <h2>{t("profileDetailsTitle")}</h2>
          <p className="hint">{t("profileOverviewBody")}</p>
          <dl className="profile-field-list">
            {fields.map((field) => (
              <div key={field.label} className="profile-field">
                <dt>{field.label}</dt>
                <dd>{field.value}</dd>
              </div>
            ))}
          </dl>
        </article>
      </section>
    </div>
  );
};

export default Profile;
