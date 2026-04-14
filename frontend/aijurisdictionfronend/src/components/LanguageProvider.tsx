import React, { createContext, useContext, useMemo, useState } from "react";
import { Language, translations, translate, TranslationValues } from "../data/translations";

interface LanguageContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: keyof typeof translations.en, values?: TranslationValues) => string;
}

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined);

const storageKey = "aj_frontend_lang";

const getInitialLanguage = (): Language => {
  const stored = localStorage.getItem(storageKey) as Language | null;
  if (stored && translations[stored]) {
    return stored;
  }
  return "en";
};

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<Language>(getInitialLanguage);

  const setLanguage = (next: Language) => {
    setLanguageState(next);
    localStorage.setItem(storageKey, next);
  };

  const t = useMemo(() => {
    return (key: keyof typeof translations.en, values?: TranslationValues) =>
      translate(language, key, values);
  }, [language]);

  const value = useMemo(() => ({ language, setLanguage, t }), [language, t]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
};

export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return context;
};
