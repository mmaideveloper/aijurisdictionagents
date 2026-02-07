import React from "react";
import { useLanguage } from "./LanguageProvider";

export const Footer: React.FC = () => {
  const { t } = useLanguage();

  return (
    <footer className="site-footer">
      <div>
        <strong>{t("appName")}</strong>
        <p>{t("footerCopy")}</p>
      </div>
      <div className="footer-meta">
        <span>© 2026 AIJurisdiction</span>
        <span>contact@aijurisdiction.eu</span>
      </div>
    </footer>
  );
};
