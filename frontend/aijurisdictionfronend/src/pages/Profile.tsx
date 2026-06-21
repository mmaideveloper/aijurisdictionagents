import React, { useEffect, useState } from "react";
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
  const { user, updateProfile, sendEmailChangeCode, completeEmailChange } = useAuth();
  const { cases, documents, selectCase } = useCases();
  const [cadence, setCadence] = useState<BillingCadence>("monthly");
  const [plan, setPlan] = useState(plans[0]?.id ?? "free");
  const [form, setForm] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phoneNumber: "",
    address: "",
    city: "",
    country: "",
    zipCode: "",
    taxNumber: "",
    identityCardNumber: "",
    dateOfBirth: "",
    socialSecurityNumber: "",
    password: ""
  });
  const [emailOtpCode, setEmailOtpCode] = useState("");
  const [emailOtpSentFor, setEmailOtpSentFor] = useState<string | null>(null);
  const [isSendingEmailOtp, setIsSendingEmailOtp] = useState(false);
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const selectedPlan = plans.find((option) => option.id === plan) ?? plans[0];
  const openedCases = cases.filter((caseItem) => caseItem.status !== "Completed");

  useEffect(() => {
    setForm({
      firstName: user?.firstName ?? "",
      lastName: user?.lastName ?? "",
      email: user?.email ?? "",
      phoneNumber: user?.phoneNumber ?? "",
      address: user?.address ?? "",
      city: user?.city ?? "",
      country: user?.country ?? "",
      zipCode: user?.zipCode ?? "",
      taxNumber: user?.taxNumber ?? "",
      identityCardNumber: user?.identityCardNumber ?? "",
      dateOfBirth: user?.dateOfBirth ?? "",
      socialSecurityNumber: user?.socialSecurityNumber ?? "",
      password: ""
    });
    setEmailOtpCode("");
    setEmailOtpSentFor(null);
  }, [user]);

  const fullName = user?.name ?? t("profileNotAvailable");
  const dataProcessingConsentAt = user?.dataProcessingConsentAt ?? t("profileOptionalPending");
  const dataProcessingConsentVersion = user?.dataProcessingConsentVersion ?? t("profileOptionalPending");
  const mcpApiKeyExpiresAt = user?.mcpApiKeyExpiresAt ?? t("profileOptionalPending");
  const role = user?.role ?? t("profileOptionalPending");
  const accountCreatedAt = user?.accountCreatedAt ?? t("profileOptionalPending");

  const fields: ProfileField[] = [
    { label: t("profileFieldUserId"), value: user?.userId ?? t("profileNotAvailable") },
    { label: t("profileFieldFullName"), value: fullName },
    { label: t("profileFieldDataProcessingConsentAt"), value: dataProcessingConsentAt },
    { label: t("profileFieldDataProcessingConsentVersion"), value: dataProcessingConsentVersion },
    { label: t("profileFieldMcpApiKeyExpiresAt"), value: mcpApiKeyExpiresAt },
    { label: t("profileFieldRole"), value: role },
    { label: t("profileFieldAccountCreated"), value: accountCreatedAt }
  ];
  const normalizedEmail = form.email.trim().toLowerCase();
  const currentEmail = (user?.email ?? "").trim().toLowerCase();
  const isEmailChanged = Boolean(normalizedEmail) && normalizedEmail !== currentEmail;

  const updateField = (field: keyof typeof form, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setProfileError(null);
    setProfileMessage(null);
  };

  const handleEditProfile = () => {
    setIsEditingProfile(true);
    setProfileError(null);
    setProfileMessage(null);
  };

  const handleSendEmailCode = async () => {
    if (!normalizedEmail) {
      setProfileError(t("profileEmailRequired"));
      setProfileMessage(null);
      return;
    }
    setIsSendingEmailOtp(true);
    try {
      await sendEmailChangeCode(normalizedEmail);
      setEmailOtpSentFor(normalizedEmail);
      setProfileError(null);
      setProfileMessage(t("profileEmailCodeSent"));
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : t("profileEmailCodeSendFailed"));
      setProfileMessage(null);
    } finally {
      setIsSendingEmailOtp(false);
    }
  };

  const handleSaveProfile = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedPhone = form.phoneNumber.trim();
    if (!normalizedPhone) {
      setProfileError(t("profilePhoneRequired"));
      setProfileMessage(null);
      return;
    }
    if (isEmailChanged && (!emailOtpCode.trim() || emailOtpSentFor !== normalizedEmail)) {
      setProfileError(t("profileEmailChangeRequiresCode"));
      setProfileMessage(null);
      return;
    }

    setIsSavingProfile(true);
    try {
      await updateProfile({
        phoneNumber: normalizedPhone,
        firstName: form.firstName.trim(),
        lastName: form.lastName.trim(),
        address: form.address.trim(),
        city: form.city.trim(),
        country: form.country.trim(),
        zipCode: form.zipCode.trim(),
        taxNumber: form.taxNumber.trim(),
        identityCardNumber: form.identityCardNumber.trim(),
        dateOfBirth: form.dateOfBirth.trim(),
        socialSecurityNumber: form.socialSecurityNumber.trim(),
        password: form.password.trim()
      });
      if (isEmailChanged) {
        await completeEmailChange(normalizedEmail, emailOtpCode.trim());
      }
      setProfileError(null);
      setProfileMessage(t("profileSaveSuccess"));
      setForm((current) => ({ ...current, password: "" }));
      setEmailOtpCode("");
      setEmailOtpSentFor(null);
      setIsEditingProfile(false);
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : t("profileSaveFailed"));
      setProfileMessage(null);
    } finally {
      setIsSavingProfile(false);
    }
  };

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
          <div className="profile-details__header">
            <h2>{t("profileDetailsTitle")}</h2>
            {!isEditingProfile ? (
              <button type="button" className="button ghost" onClick={handleEditProfile}>
                {t("profileEdit")}
              </button>
            ) : null}
          </div>
          <p className="hint">{t("profileOverviewBody")}</p>
          <p className="hint">{t("profileDocumentDataReuseNotice")}</p>
          <form className="form profile-edit-form" onSubmit={handleSaveProfile}>
            <label>
              <span>{t("profileFieldFirstName")}</span>
              <input
                disabled={!isEditingProfile}
                value={form.firstName}
                onChange={(event) => updateField("firstName", event.target.value)}
              />
            </label>
            <label>
              <span>{t("profileFieldLastName")}</span>
              <input
                disabled={!isEditingProfile}
                value={form.lastName}
                onChange={(event) => updateField("lastName", event.target.value)}
              />
            </label>
            <label>
              <span>{t("profileFieldEmail")}</span>
              <input
                disabled={!isEditingProfile}
                type="email"
                value={form.email}
                onChange={(event) => updateField("email", event.target.value)}
              />
            </label>
            {isEditingProfile && isEmailChanged ? (
              <div className="profile-email-otp">
                <button
                  type="button"
                  className="button ghost"
                  onClick={handleSendEmailCode}
                  disabled={isSendingEmailOtp}
                >
                  {isSendingEmailOtp ? t("profileEmailSendingCode") : t("profileEmailSendCode")}
                </button>
                <label>
                  <span>{t("profileEmailOtpCode")}</span>
                  <input value={emailOtpCode} onChange={(event) => setEmailOtpCode(event.target.value)} />
                </label>
              </div>
            ) : null}
            <label>
              <span>{t("profileFieldPhoneRequired")}</span>
              <input
                required
                disabled={!isEditingProfile}
                type="tel"
                value={form.phoneNumber}
                onChange={(event) => updateField("phoneNumber", event.target.value)}
              />
            </label>
            <label>
              <span>{t("profileFieldAddress")}</span>
              <input
                disabled={!isEditingProfile}
                value={form.address}
                onChange={(event) => updateField("address", event.target.value)}
              />
            </label>
            <label>
              <span>{t("profileFieldCity")}</span>
              <input
                disabled={!isEditingProfile}
                value={form.city}
                onChange={(event) => updateField("city", event.target.value)}
              />
            </label>
            <label>
              <span>{t("profileFieldCountry")}</span>
              <input
                disabled={!isEditingProfile}
                value={form.country}
                onChange={(event) => updateField("country", event.target.value)}
              />
            </label>
            <label>
              <span>{t("profileFieldZipCode")}</span>
              <input
                disabled={!isEditingProfile}
                value={form.zipCode}
                onChange={(event) => updateField("zipCode", event.target.value)}
              />
            </label>
            <label>
              <span>{t("profileFieldTaxNumber")}</span>
              <input
                disabled={!isEditingProfile}
                value={form.taxNumber}
                onChange={(event) => updateField("taxNumber", event.target.value)}
              />
            </label>
            <label>
              <span>{t("profileFieldIdentityCardNumber")}</span>
              <input
                disabled={!isEditingProfile}
                value={form.identityCardNumber}
                onChange={(event) => updateField("identityCardNumber", event.target.value)}
              />
            </label>
            <label>
              <span>{t("profileFieldDateOfBirth")}</span>
              <input
                disabled={!isEditingProfile}
                type="date"
                value={form.dateOfBirth}
                onChange={(event) => updateField("dateOfBirth", event.target.value)}
              />
            </label>
            <label>
              <span>{t("profileFieldSocialSecurityNumber")}</span>
              <input
                disabled={!isEditingProfile}
                value={form.socialSecurityNumber}
                onChange={(event) => updateField("socialSecurityNumber", event.target.value)}
              />
            </label>
            <label>
              <span>{t("profilePasswordOptional")}</span>
              <input
                disabled={!isEditingProfile}
                type="password"
                value={form.password}
                onChange={(event) => updateField("password", event.target.value)}
              />
            </label>
            {profileError ? (
              <p className="form-error" role="alert">
                {profileError}
              </p>
            ) : null}
            {profileMessage ? <p className="hint">{profileMessage}</p> : null}
            {isEditingProfile ? (
              <button type="submit" className="button primary full" disabled={isSavingProfile}>
                {isSavingProfile ? t("profileSaving") : t("profileSave")}
              </button>
            ) : null}
          </form>
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
