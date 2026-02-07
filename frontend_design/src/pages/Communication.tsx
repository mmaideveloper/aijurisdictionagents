import React from "react";
import { useLanguage } from "../components/LanguageProvider";

const Communication: React.FC = () => {
  const { t } = useLanguage();

  return (
    <div className="page">
      <section className="section-head">
        <h1>{t("commsTitle")}</h1>
        <p>{t("commsSubtitle")}</p>
      </section>
      <section className="card-grid three">
          <article className="card">
            <h3>{t("commsChat")}</h3>
            <p>{t("commsChatBody")}</p>
            <button type="button" className="button ghost">{t("commsChatAction")}</button>
          </article>
          <article className="card">
            <h3>{t("commsVoice")}</h3>
            <p>{t("commsVoiceBody")}</p>
            <button type="button" className="button ghost">{t("commsVoiceAction")}</button>
          </article>
          <article className="card">
            <h3>{t("commsVideo")}</h3>
            <p>{t("commsVideoBody")}</p>
            <button type="button" className="button ghost">{t("commsVideoAction")}</button>
          </article>
      </section>
    </div>
  );
};

export default Communication;
