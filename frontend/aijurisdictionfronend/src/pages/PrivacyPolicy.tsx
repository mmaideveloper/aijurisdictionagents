import React from "react";
import { useLanguage } from "../components/LanguageProvider";
import { legalContent } from "../content/legal";

const PrivacyPolicy: React.FC = () => {
  const { language } = useLanguage();
  const content = legalContent[language].privacy;

  return (
    <div className="page legal-page">
      <article className="legal-shell">
        <header className="legal-header">
          <h1>{content.title}</h1>
          <p>{content.summary}</p>
        </header>
        <div className="legal-sections">
          {content.sections.map((section) => (
            <section key={section.heading} className="legal-section-card">
              <h2>{section.heading}</h2>
              <p>{section.body}</p>
              {section.links?.map((link) => (
                <p key={link.href}>
                  <a href={link.href}>{link.label}</a>
                </p>
              ))}
            </section>
          ))}
        </div>
        <footer className="legal-last-updated">
          <strong>{content.lastUpdatedLabel}:</strong> {content.lastUpdated}
        </footer>
      </article>
    </div>
  );
};

export default PrivacyPolicy;
