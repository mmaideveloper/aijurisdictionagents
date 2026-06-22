import React from "react";
import { useLanguage } from "../components/LanguageProvider";

const News: React.FC = () => {
  const { t } = useLanguage();

  return (
    <div className="page news-page">
      <section className="news-shell" aria-labelledby="news-title">
        <header className="news-header">
          <p className="eyebrow">{t("assistantThreadsTitle")}</p>
          <h1 id="news-title">{t("navNews")}</h1>
          <p>{t("newsSubtitle")}</p>
        </header>

        <div className="news-thread-list">
          <button type="button" className="assistant-thread-item active">
            {t("assistantThreadCurrent")}
          </button>
          <button type="button" className="assistant-thread-item">
            {t("assistantThreadDocument")}
          </button>
        </div>
      </section>
    </div>
  );
};

export default News;
