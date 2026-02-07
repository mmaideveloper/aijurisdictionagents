import React from "react";
import { useLanguage } from "../components/LanguageProvider";

const Auth: React.FC = () => {
  const { t } = useLanguage();

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
            <input type="email" placeholder="name@firm.com" />
          </label>
          <label>
            <span>{t("authPassword")}</span>
            <input type="password" placeholder="••••••••" />
          </label>
          <button type="button" className="button primary full">
            {t("authSignIn")}
          </button>
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
