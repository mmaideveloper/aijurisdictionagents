import React from "react";
import { useNavigate } from "react-router-dom";
import { MfaChallenge, useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";

const Auth: React.FC = () => {
  const { t } = useLanguage();
  const { isAuthenticated, user, signIn, sendSignUpCode, signUp, signOut, sendMfaEmailCode, verifyMfa } = useAuth();
  const navigate = useNavigate();
  const [authMode, setAuthMode] = React.useState<"signIn" | "signUp">("signIn");
  const [registrationStep, setRegistrationStep] = React.useState<"details" | "verify">("details");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loginOtpCode, setLoginOtpCode] = React.useState("");
  const [registrationOtpCode, setRegistrationOtpCode] = React.useState("");
  const [phoneNumber, setPhoneNumber] = React.useState("");
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [mfaChallenge, setMfaChallenge] = React.useState<MfaChallenge | null>(null);
  const [mfaMethod, setMfaMethod] = React.useState("totp");
  const [mfaCode, setMfaCode] = React.useState("");
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [isSendingRegistrationOtp, setIsSendingRegistrationOtp] = React.useState(false);
  const [isRegistering, setIsRegistering] = React.useState(false);
  const [loginOtpRequired, setLoginOtpRequired] = React.useState(false);
  const [registrationOtpSentFor, setRegistrationOtpSentFor] = React.useState<string | null>(null);

  const resetFeedback = () => {
    setError(null);
    setMessage(null);
  };

  const showSignIn = () => {
    setAuthMode("signIn");
    setRegistrationStep("details");
    setRegistrationOtpCode("");
    setRegistrationOtpSentFor(null);
    resetFeedback();
  };

  const showSignUp = () => {
    setAuthMode("signUp");
    setLoginOtpCode("");
    setLoginOtpRequired(false);
    setMfaChallenge(null);
    setMfaCode("");
    setRegistrationStep("details");
    setRegistrationOtpCode("");
    setRegistrationOtpSentFor(null);
    resetFeedback();
  };

  const handleSignIn = async () => {
    const normalizedEmail = email.trim();
    setIsSubmitting(true);
    try {
      const result = await signIn(normalizedEmail, password, loginOtpCode);
      if (result === "invalid_credentials") {
        setError(t("authInvalidCredentials"));
        setMessage(null);
        return;
      }
      if (result === "otp_required") {
        setLoginOtpRequired(true);
        setError(null);
        setMessage(t("authLoginOtpSent"));
        return;
      }
      if (typeof result !== "string" && result.status === "mfa_required") {
        const preferredMethod = result.challenge.methods.includes("totp") ? "totp" : "email";
        setMfaChallenge(result.challenge);
        setMfaMethod(preferredMethod);
        if (preferredMethod === "email") {
          await sendMfaEmailCode(result.challenge.mfaToken);
        }
        setError(null);
        setMessage(t("authMfaRequired"));
        return;
      }
      setError(null);
      setMfaChallenge(null);
      setMessage(t("authSignedIn"));
      navigate("/app/assistant");
    } catch (signInError) {
      setError(signInError instanceof Error ? signInError.message : t("authSignInFailed"));
      setMessage(null);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSendRegistrationOtp = async () => {
    const normalizedEmail = email.trim();
    const normalizedPhone = phoneNumber.trim();
    if (!normalizedEmail || !password || !normalizedPhone) {
      setError(t("authRegisterMissingFields"));
      setMessage(null);
      return;
    }

    setIsSendingRegistrationOtp(true);
    try {
      await sendSignUpCode(normalizedEmail);
      setRegistrationOtpSentFor(normalizedEmail.toLowerCase());
      setRegistrationStep("verify");
      setError(null);
      setMessage(t("authRegisterOtpSent"));
    } catch (otpError) {
      setError(otpError instanceof Error ? otpError.message : t("authRegisterOtpFailed"));
      setMessage(null);
    } finally {
      setIsSendingRegistrationOtp(false);
    }
  };

  const handleSignUp = async () => {
    const normalizedEmail = email.trim();
    const normalizedPhone = phoneNumber.trim();
    if (!normalizedEmail || !password || !normalizedPhone) {
      setError(t("authRegisterMissingFields"));
      setMessage(null);
      return;
    }
    if (!registrationOtpCode.trim() || registrationOtpSentFor !== normalizedEmail.toLowerCase()) {
      setError(t("authRegisterOtpRequired"));
      setMessage(null);
      return;
    }

    setIsRegistering(true);
    try {
      await signUp({
        phoneNumber: normalizedPhone,
        email: normalizedEmail,
        password,
        verificationCode: registrationOtpCode.trim()
      });
      setError(null);
      setMessage(t("authRegistered"));
      navigate("/app/assistant");
    } catch (signUpError) {
      setError(signUpError instanceof Error ? signUpError.message : t("authRegisterFailed"));
      setMessage(null);
    } finally {
      setIsRegistering(false);
    }
  };

  const handleMfaMethodChange = async (nextMethod: string) => {
    setMfaMethod(nextMethod);
    setMfaCode("");
    setError(null);
    if (nextMethod === "email" && mfaChallenge) {
      try {
        await sendMfaEmailCode(mfaChallenge.mfaToken);
        setMessage(t("authMfaEmailSent"));
      } catch (sendError) {
        setError(sendError instanceof Error ? sendError.message : t("authSignInFailed"));
      }
    }
  };

  const handleVerifyMfa = async () => {
    if (!mfaChallenge) {
      return;
    }
    setIsSubmitting(true);
    try {
      const ok = await verifyMfa(mfaChallenge.mfaToken, mfaMethod, mfaCode.trim());
      if (!ok) {
        setError(t("authMfaInvalid"));
        return;
      }
      setError(null);
      setMfaChallenge(null);
      setMessage(t("authSignedIn"));
      navigate("/app/assistant");
    } catch (verifyError) {
      setError(verifyError instanceof Error ? verifyError.message : t("authSignInFailed"));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSignOut = () => {
    signOut();
    setMessage("Signed out.");
    setError(null);
    setPassword("");
    setLoginOtpCode("");
    setRegistrationOtpCode("");
    setLoginOtpRequired(false);
    setRegistrationOtpSentFor(null);
    setAuthMode("signIn");
    setRegistrationStep("details");
  };

  return (
    <div className="page auth-page">
      <section className="auth-card">
        <div>
          <h1>{authMode === "signIn" ? t("authTitle") : t("authCreateTitle")}</h1>
          <p>{authMode === "signIn" ? t("authSubtitle") : t("authCreateBody")}</p>
        </div>
        <form className="form">
          {authMode === "signIn" ? (
            <>
              <label>
                <span>{t("authEmail")}</span>
                <input
                  type="email"
                  placeholder="name@firm.com"
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    setLoginOtpRequired(false);
                    setRegistrationOtpSentFor(null);
                  }}
                />
              </label>
              <label>
                <span>{t("authPassword")}</span>
                <input
                  type="password"
                  placeholder="********"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </label>
              {loginOtpRequired ? (
                <label>
                  <span>{t("authOtpCode")}</span>
                  <input
                    inputMode="numeric"
                    value={loginOtpCode}
                    onChange={(event) => setLoginOtpCode(event.target.value)}
                  />
                </label>
              ) : null}
              <button
                type="button"
                className="button primary full"
                onClick={handleSignIn}
                disabled={isSubmitting || Boolean(mfaChallenge)}
              >
                {isSubmitting ? t("authSigningIn") : t("authSignIn")}
              </button>
              <button type="button" className="button ghost full" onClick={showSignUp}>
                {t("authSignUp")}
              </button>
              {mfaChallenge ? (
                <div className="mfa-panel">
                  <label>
                    <span>{t("authMfaMethod")}</span>
                    <select value={mfaMethod} onChange={(event) => void handleMfaMethodChange(event.target.value)}>
                      {mfaChallenge.methods.includes("email") ? (
                        <option value="email">{t("authMfaEmail")}</option>
                      ) : null}
                      {mfaChallenge.methods.includes("totp") ? (
                        <option value="totp">{t("authMfaTotp")}</option>
                      ) : null}
                    </select>
                  </label>
                  <label>
                    <span>{mfaMethod === "totp" ? t("authMfaTotpCode") : t("authMfaEmailCode")}</span>
                    <input
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      value={mfaCode}
                      onChange={(event) => setMfaCode(event.target.value)}
                    />
                  </label>
                  <button
                    type="button"
                    className="button primary full"
                    onClick={handleVerifyMfa}
                    disabled={isSubmitting || mfaCode.trim().length === 0}
                  >
                    {t("authMfaVerify")}
                  </button>
                </div>
              ) : null}
            </>
          ) : (
            <>
              {registrationStep === "details" ? (
                <>
                  <label>
                    <span>{t("authPhone")}</span>
                    <input
                      type="tel"
                      placeholder="+421900123456"
                      value={phoneNumber}
                      onChange={(event) => setPhoneNumber(event.target.value)}
                    />
                  </label>
                  <label>
                    <span>{t("authEmail")}</span>
                    <input
                      type="email"
                      placeholder="name@firm.com"
                      value={email}
                      onChange={(event) => {
                        setEmail(event.target.value);
                        setRegistrationOtpSentFor(null);
                      }}
                    />
                  </label>
                  <label>
                    <span>{t("authPassword")}</span>
                    <input
                      type="password"
                      placeholder="********"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                    />
                  </label>
                  <button
                    type="button"
                    className="button primary full"
                    onClick={handleSendRegistrationOtp}
                    disabled={isSendingRegistrationOtp}
                  >
                    {isSendingRegistrationOtp ? t("authOtpSending") : t("authContinueToVerification")}
                  </button>
                </>
              ) : (
                <>
                  <p className="hint">{t("authRegistrationVerificationBody")}</p>
                  <label>
                    <span>{t("authOtpCode")}</span>
                    <input
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      value={registrationOtpCode}
                      onChange={(event) => setRegistrationOtpCode(event.target.value)}
                    />
                  </label>
                  <button type="button" className="button primary full" onClick={handleSignUp} disabled={isRegistering}>
                    {isRegistering ? t("authRegistering") : t("authRegister")}
                  </button>
                  <button
                    type="button"
                    className="button ghost full"
                    onClick={handleSendRegistrationOtp}
                    disabled={isSendingRegistrationOtp}
                  >
                    {isSendingRegistrationOtp ? t("authOtpSending") : t("authRegisterSendOtp")}
                  </button>
                  <button
                    type="button"
                    className="button ghost full"
                    onClick={() => {
                      setRegistrationStep("details");
                      setRegistrationOtpCode("");
                      setRegistrationOtpSentFor(null);
                      resetFeedback();
                    }}
                  >
                    {t("authEditRegistrationDetails")}
                  </button>
                </>
              )}
              <button type="button" className="button ghost full" onClick={showSignIn}>
                {t("authBackToSignIn")}
              </button>
            </>
          )}
          <p className="hint">{t("authApiLoginHint")}</p>
          {error ? (
            <p className="hint" role="alert">
              {error}
            </p>
          ) : null}
          {message ? <p className="hint">{message}</p> : null}
          {isAuthenticated ? (
            <div className="hint">
              {t("authSignedInAs")} <strong>{user?.name ?? t("commonUser")}</strong>.{" "}
              <button type="button" className="button ghost" onClick={handleSignOut}>
                {t("authResetSession")}
              </button>
            </div>
          ) : null}
        </form>
      </section>
    </div>
  );
};

export default Auth;
