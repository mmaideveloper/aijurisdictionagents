import React from "react";
import { useLanguage } from "./LanguageProvider";
import { Language } from "../data/translations";

const labels: Record<Language, string> = {
  en: "EN",
  sk: "SK",
  de: "DE"
};

export const LanguageSwitcher: React.FC = () => {
  const { language, setLanguage } = useLanguage();

  return (
    <div className="lang-switch" role="group" aria-label="Language switch">
      {(Object.keys(labels) as Language[]).map((lang) => (
        <button
          key={lang}
          type="button"
          onClick={() => setLanguage(lang)}
          className={`lang-btn ${language === lang ? "active" : ""}`}
          aria-pressed={language === lang}
        >
          {labels[lang]}
        </button>
      ))}
    </div>
  );
};
