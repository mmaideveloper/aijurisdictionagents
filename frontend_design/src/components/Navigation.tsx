import React from "react";
import { NavLink } from "react-router-dom";
import { useLanguage } from "./LanguageProvider";
import { LanguageSwitcher } from "./LanguageSwitcher";

export const Navigation: React.FC = () => {
  const { t } = useLanguage();

  return (
    <header className="site-header">
      <nav className="nav">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            AJ
          </div>
          <div>
            <strong>{t("appName")}</strong>
            <span>{t("tagline")}</span>
          </div>
        </div>
        <div className="nav-links">
          <NavLink to="/">{t("navHome")}</NavLink>
          <NavLink to="/pricing">{t("navPricing")}</NavLink>
          <NavLink to="/auth">{t("navAuth")}</NavLink>
          <NavLink to="/app">{t("navApp")}</NavLink>
        </div>
        <LanguageSwitcher />
      </nav>
    </header>
  );
};
