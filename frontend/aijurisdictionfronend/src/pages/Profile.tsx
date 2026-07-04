import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FaDownload } from "react-icons/fa";
import { fetchCaseExportBlob } from "../api/caseClient";
import { chatApiRuntimeConfig } from "../api/chatClient";
import { useLanguage } from "../components/LanguageProvider";
import { useAuth } from "../auth/webAuth";
import { plans } from "../data/plans";
import { useCases } from "../state/CaseProvider";
import { caseStatusTranslationKeys } from "../state/caseStatus";

interface ProfileField {
  label: string;
  value: string;
}

const Profile: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const { user, updateProfile, sendEmailChangeCode, completeEmailChange, refreshUser } = useAuth();
  const { cases, documents, selectCase } = useCases();
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
  const [exportingCaseId, setExportingCaseId] = useState<string | null>(null);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [totpSetup, setTotpSetup] = useState<{
    manualSetupKey: string;
    qrCodeUri: string;
  } | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [mfaMessage, setMfaMessage] = useState<string | null>(null);
  const [mfaError, setMfaError] = useState<string | null>(null);
  const [isMfaSubmitting, setIsMfaSubmitting] = useState(false);
  const selectedPlan = plans.find((option) => !option.disabled) ?? plans[0];
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

  const handleOpenDocument = (document: (typeof documents)[number]) => {
    selectCase(document.caseId);
    const params = new URLSearchParams({
      caseId: document.caseId,
      docId: document.id,
      kind: document.kind,
      filename: document.originalFilename,
      caseTitle: document.caseTitle,
      userId: user?.userId ?? ""
    });
    navigate(`/app/documents/view?${params.toString()}`);
  };

  const handleExportCase = async (
    event: React.MouseEvent<HTMLButtonElement>,
    caseItem: (typeof cases)[number]
  ) => {
    event.stopPropagation();
    if (!user?.userId) {
      return;
    }
    setExportingCaseId(caseItem.id);
    setProfileError(null);
    setProfileMessage(null);
    try {
      const exported = await fetchCaseExportBlob({
        userId: user.userId,
        caseId: caseItem.id
      });
      const objectUrl = URL.createObjectURL(exported.blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = exported.filename;
      anchor.rel = "noopener";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : t("profileCaseExportFailed"));
    } finally {
      setExportingCaseId(null);
    }
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

  const startTotpEnrollment = async () => {
    if (!user) {
      return;
    }
    setIsMfaSubmitting(true);
    try {
      const config = chatApiRuntimeConfig();
      const response = await fetch(`${config.baseUrl}/v1/users/${user.userId}/mfa/totp/start`, {
        method: "POST",
        headers: { "x-api-key": config.apiKey }
      });
      if (!response.ok) {
        throw new Error(t("profileMfaStartFailed"));
      }
      const payload = (await response.json()) as {
        manual_setup_key: string;
        qr_code_uri: string;
      };
      setTotpSetup({
        manualSetupKey: payload.manual_setup_key,
        qrCodeUri: payload.qr_code_uri
      });
      setTotpCode("");
      setMfaMessage(t("profileMfaScanPrompt"));
      setMfaError(null);
    } catch (error) {
      setMfaError(error instanceof Error ? error.message : t("profileMfaStartFailed"));
    } finally {
      setIsMfaSubmitting(false);
    }
  };

  const disableTotpEnrollment = async () => {
    if (!user) {
      return;
    }
    if (!totpCode.trim()) {
      setMfaError(t("profileMfaDisableCodeRequired"));
      setMfaMessage(null);
      return;
    }
    setIsMfaSubmitting(true);
    try {
      const config = chatApiRuntimeConfig();
      const response = await fetch(`${config.baseUrl}/v1/users/${user.userId}/mfa/totp`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", "x-api-key": config.apiKey },
        body: JSON.stringify({ verification_code: totpCode.trim() })
      });
      if (!response.ok) {
        throw new Error(t("profileMfaInvalidCode"));
      }
      await refreshUser(user.userId);
      setTotpSetup(null);
      setTotpCode("");
      setMfaMessage(t("profileMfaDisabled"));
      setMfaError(null);
    } catch (error) {
      setMfaError(error instanceof Error ? error.message : t("profileMfaInvalidCode"));
      setMfaMessage(null);
    } finally {
      setIsMfaSubmitting(false);
    }
  };

  const confirmTotpEnrollment = async () => {
    if (!user) {
      return;
    }
    setIsMfaSubmitting(true);
    try {
      const config = chatApiRuntimeConfig();
      const response = await fetch(`${config.baseUrl}/v1/users/${user.userId}/mfa/totp/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-api-key": config.apiKey },
        body: JSON.stringify({ verification_code: totpCode.trim() })
      });
      if (!response.ok) {
        throw new Error(t("profileMfaInvalidCode"));
      }
      await refreshUser(user.userId);
      setTotpSetup(null);
      setTotpCode("");
      setMfaMessage(t("profileMfaEnabled"));
      setMfaError(null);
    } catch (error) {
      setMfaError(error instanceof Error ? error.message : t("profileMfaInvalidCode"));
    } finally {
      setIsMfaSubmitting(false);
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
            <h3>{t("profilePlan")}</h3>
            <div className="plan-selector">
              {plans.filter((option) => !option.disabled).map((option) => (
                <button
                  key={option.id}
                  type="button"
                  className="pill active"
                  disabled
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
                      <span title={caseItem.title}>{caseItem.title}</span>
                      <small title={t(caseStatusTranslationKeys[caseItem.status])}>
                        {t(caseStatusTranslationKeys[caseItem.status])}
                      </small>
                    </button>
                    <button
                      type="button"
                      className="button ghost icon-button profile-case-export-button"
                      onClick={(event) => void handleExportCase(event, caseItem)}
                      disabled={exportingCaseId === caseItem.id}
                      title={t("profileCaseExport")}
                      aria-label={t("profileCaseExport")}
                    >
                      <FaDownload aria-hidden="true" />
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
                    <button
                      type="button"
                      className="profile-document-button"
                      onClick={() => handleOpenDocument(document)}
                    >
                      <strong title={document.originalFilename}>{document.originalFilename}</strong>
                      <small title={document.caseTitle}>
                        {t("profileDocumentCaseLabel")}: {document.caseTitle}
                      </small>
                    </button>
                    <small className="profile-document-meta" title={document.sizeLabel}>
                      {document.sizeLabel}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="hint">{t("profileDocumentsEmpty")}</p>
            )}
          </article>
          <article className="card">
            <h2>{t("profileMfaTitle")}</h2>
            <p className="hint">
              {user?.mfaTotpEnabled ? t("profileMfaTotpEnabled") : t("profileMfaTotpDisabled")}
            </p>
            <p className="hint">{t("profileMfaEmailFallback")}</p>
            <div className="mfa-actions">
              <button
                type="button"
                className="button primary"
                onClick={startTotpEnrollment}
                disabled={isMfaSubmitting}
              >
                {user?.mfaTotpEnabled ? t("profileMfaUpdateTotp") : t("profileMfaStartTotp")}
              </button>
              {user?.mfaTotpEnabled ? (
                <button
                  type="button"
                  className="button ghost"
                  onClick={disableTotpEnrollment}
                  disabled={isMfaSubmitting || totpCode.trim().length === 0}
                >
                  {t("profileMfaDisableTotp")}
                </button>
              ) : null}
            </div>
            {user?.mfaTotpEnabled && !totpSetup ? (
              <label className="mfa-code-field">
                <span>{t("profileMfaCurrentCode")}</span>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={totpCode}
                  onChange={(event) => setTotpCode(event.target.value)}
                />
              </label>
            ) : null}
            {totpSetup ? (
              <div className="mfa-setup">
                {totpSetup.qrCodeUri ? (
                  <img src={totpSetup.qrCodeUri} alt={t("profileMfaQrAlt")} />
                ) : null}
                <label>
                  <span>{t("profileMfaManualKey")}</span>
                  <input readOnly value={totpSetup.manualSetupKey} />
                </label>
                <label>
                  <span>{t("profileMfaConfirmCode")}</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    value={totpCode}
                    onChange={(event) => setTotpCode(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="button primary"
                  onClick={confirmTotpEnrollment}
                  disabled={isMfaSubmitting || totpCode.trim().length === 0}
                >
                  {t("profileMfaConfirm")}
                </button>
              </div>
            ) : null}
            {mfaError ? (
              <p className="hint" role="alert">
                {mfaError}
              </p>
            ) : null}
            {mfaMessage ? <p className="hint">{mfaMessage}</p> : null}
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
                <dd title={field.value}>{field.value}</dd>
              </div>
            ))}
          </dl>
        </article>
      </section>
    </div>
  );
};

export default Profile;
