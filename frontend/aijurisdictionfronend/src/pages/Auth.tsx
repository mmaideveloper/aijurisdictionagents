import React from "react";
import { useLanguage } from "../components/LanguageProvider";
import { MOCK_USER, useAuth } from "../auth/mockAuth";

const Auth: React.FC = () => {
  const { t } = useLanguage();
  const { isAuthenticated, user, signIn, signOut } = useAuth();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const handleSignIn = () => {
    const normalizedEmail = email.trim();
    const ok = signIn(normalizedEmail, password);
    if (!ok) {
      setError("Invalid credentials. Use admin@admin.com / admin123.");
      setMessage(null);
      return;
    }
    setError(null);
    setMessage(`Signed in as ${MOCK_USER.email}.`);
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
              placeholder="••••••••"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button
            type="button"
            className="button primary full"
            onClick={handleSignIn}
          >
            {t("authSignIn")}
          </button>
          <p className="hint">
            Simulated login only. Use <strong>{MOCK_USER.email}</strong> /{" "}
            <strong>{MOCK_USER.password}</strong>.
          </p>
          {error ? (
            <p className="hint" role="alert">
              {error}
            </p>
          ) : null}
          {message ? <p className="hint">{message}</p> : null}
          {isAuthenticated ? (
            <div className="hint">
              Signed in as <strong>{user?.name ?? MOCK_USER.name}</strong>.{" "}
              <button type="button" className="button ghost" onClick={handleSignOut}>
                Reset session
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
