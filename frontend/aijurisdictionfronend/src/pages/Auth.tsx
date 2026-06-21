import React from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";

const Auth: React.FC = () => {
  const { t } = useLanguage();
  const { isAuthenticated, user, signIn, sendSignUpCode, signUp, signOut } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loginOtpCode, setLoginOtpCode] = React.useState("");
  const [registrationOtpCode, setRegistrationOtpCode] = React.useState("");
  const [phoneNumber, setPhoneNumber] = React.useState("");
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [isSendingRegistrationOtp, setIsSendingRegistrationOtp] = React.useState(false);
  const [isRegistering, setIsRegistering] = React.useState(false);
  const [loginOtpRequired, setLoginOtpRequired] = React.useState(false);
  const [registrationOtpSentFor, setRegistrationOtpSentFor] = React.useState<string | null>(null);

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
      setError(null);
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
    if (!normalizedEmail) {
      setError(t("authEmailRequired"));
      setMessage(null);
      return;
    }

    setIsSendingRegistrationOtp(true);
    try {
      await sendSignUpCode(normalizedEmail);
      setRegistrationOtpSentFor(normalizedEmail.toLowerCase());
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

  const handleSignOut = () => {
    signOut();
    setMessage("Signed out.");
    setError(null);
    setPassword("");
    setLoginOtpCode("");
    setRegistrationOtpCode("");
    setLoginOtpRequired(false);
    setRegistrationOtpSentFor(null);
  };

  return (
    <div className="page auth-page">
      <section className="auth-card">
        <div>
          <h1>{t("authTitle")}</h1>
          <p>{t("authSubtitle")}</p>
        </div>
        <form className="form">
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
            disabled={isSubmitting}
          >
            {isSubmitting ? t("authSigningIn") : t("authSignIn")}
          </button>
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
      <section className="auth-aside">
        <h2>{t("authCreateTitle")}</h2>
        <p>{t("authCreateBody")}</p>
        <label className="form">
          <span>{t("authPhone")}</span>
          <input
            type="tel"
            placeholder="+421900123456"
            value={phoneNumber}
            onChange={(event) => setPhoneNumber(event.target.value)}
          />
        </label>
        <label className="form">
          <span>{t("authOtpCode")}</span>
          <input
            inputMode="numeric"
            value={registrationOtpCode}
            onChange={(event) => setRegistrationOtpCode(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="button ghost"
          onClick={handleSendRegistrationOtp}
          disabled={isSendingRegistrationOtp}
        >
          {isSendingRegistrationOtp ? t("authOtpSending") : t("authRegisterSendOtp")}
        </button>
        <button type="button" className="button ghost" onClick={handleSignUp} disabled={isRegistering}>
          {isRegistering ? t("authRegistering") : t("authRegister")}
        </button>
      </section>
    </div>
  );
};

export default Auth;
