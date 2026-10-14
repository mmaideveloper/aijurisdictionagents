import React from "react";
import { useLanguage } from "./LanguageProvider";

export const AITransparencyNotice: React.FC<{ metadata?: unknown }> = ({ metadata }) => {
  const { language } = useLanguage();
  const text = {
    en: "AI-generated draft. It may be inaccurate, incomplete or outdated. Verify sources and obtain human legal review before legally consequential actions.",
    sk: "Návrh vytvorený AI môže byť nepresný, neúplný alebo neaktuálny. Overte zdroje a pred právne významnými krokmi zabezpečte ľudské právne posúdenie.",
    de: "KI-generierter Entwurf. Er kann ungenau, unvollständig oder veraltet sein. Prüfen Sie Quellen und lassen Sie rechtlich bedeutsame Schritte durch einen Menschen prüfen."
  };
  const data = metadata && typeof metadata === "object" ? metadata as Record<string, unknown> : {};
  const provider = typeof data.model_provider === "string" ? data.model_provider : "";
  const model = typeof data.model_name === "string" ? data.model_name : "";
  return <small className="ai-transparency-notice" style={{ display: "block", marginTop: "0.75rem" }}>
    {text[language as keyof typeof text] ?? text.en}
    {provider && model ? <> {provider} / {model}</> : null}
  </small>;
};
