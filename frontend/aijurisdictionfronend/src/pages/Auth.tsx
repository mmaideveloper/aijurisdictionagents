import React from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";

const Auth: React.FC = () => {
  const { t } = useLanguage();
  const { isAuthenticated, user, signIn, signOut } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const handleSignIn = async () => {
    const normalizedEmail = email.trim();
    setIsSubmitting(true);
    try {
      const ok = await signIn(normalizedEmail, password);
      if (!ok) {
        setError(t("authInvalidCredentials"));
        setMessage(null);
        return;
      }
      setError(null);
      setMessage(t("authSignedIn"));
      navigate("/");
    } catch (signInError) {
      setError(signInError instanceof Error ? signInError.message : t("authSignInFailed"));
      setMessage(null);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSignOut = () => {
    signOut();
    setMessage("Signed out.");
    setError(null);
    setPassword("");
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
              onChange={(event) => setEmail(event.target.value)}
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
        <button type="button" className="button ghost">
          {t("authRegister")}
        </button>
      </section>
    </div>
  );
};

export default Auth;
