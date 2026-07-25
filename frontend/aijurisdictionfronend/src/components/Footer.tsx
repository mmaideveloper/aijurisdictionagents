import React from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "./LanguageProvider";
import { legalContent } from "../content/legal";

export const Footer: React.FC = () => {
  const { t, language } = useLanguage();
  const links = legalContent[language].footerLinks;

  return (
    <footer className="site-footer">
      <div>
        <strong>{t("appName")}</strong>
        <p>{t("footerCopy")}</p>
      </div>
      <nav className="footer-links" aria-label="Legal links">
        <Link to="/privacy">{links.privacy}</Link>
        <Link to="/disclaimer">{links.disclaimer}</Link>
        <Link to="/terms">{links.terms}</Link>
      </nav>
      <div className="footer-meta">
        <span>© 2026 {t("appName")}</span>
        <span>info@jurisdigta.eu</span>
      </div>
    </footer>
  );
};
