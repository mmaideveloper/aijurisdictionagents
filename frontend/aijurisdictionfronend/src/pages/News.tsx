import React from "react";
import { BsLockFill } from "react-icons/bs";
import { useLanguage } from "../components/LanguageProvider";

type NewsPost = {
  date: string;
  title: string;
  body: string;
  kind: "mcp" | "plain";
};

const News: React.FC = () => {
  const { t } = useLanguage();
  const capabilities = [
    t("assistantCapabilityLawSearch"),
    t("assistantCapabilityOrsr"),
    t("assistantCapabilityPerson"),
    t("assistantCapabilityScreening"),
    t("assistantCapabilityCar"),
    t("assistantCapabilityLocation")
  ];

  const posts: NewsPost[] = [
    {
      date: t("newsAudioModelsDate"),
      title: t("newsAudioModelsTitle"),
      body: t("newsAudioModelsBody"),
      kind: "plain"
    },
    {
      date: t("newsLocalModelsDate"),
      title: t("newsLocalModelsTitle"),
      body: t("newsLocalModelsBody"),
      kind: "plain"
    },
    {
      date: t("newsMcpDate"),
      title: t("assistantMandatoryMcpTitle"),
      body: t("assistantMandatoryMcpBody"),
      kind: "mcp"
    },
    {
      date: t("newsApprovalDate"),
      title: t("assistantApprovalTitle"),
      body: t("assistantApprovalBody"),
      kind: "plain"
    },
    {
      date: t("newsMetadataDate"),
      title: t("assistantMetadataTitle"),
      body: t("newsMetadataBody"),
      kind: "plain"
    }
  ];

  return (
    <div className="page news-page">
      <section className="news-shell" aria-labelledby="news-title">
        <header className="news-header">
          <p className="eyebrow">{t("newsEyebrow")}</p>
          <h1 id="news-title">{t("navNews")}</h1>
          <p>{t("newsSubtitle")}</p>
        </header>

        <div className="news-post-list">
          {posts.map((post) => (
            <article className="news-post-card" key={`${post.date}-${post.title}`}>
              <time>{post.date}</time>
              <h2>
                {post.kind === "mcp" ? <BsLockFill aria-hidden="true" /> : null}
                {post.title}
              </h2>
              <p>{post.body}</p>
              {post.kind === "mcp" ? (
                <>
                  <span className="assistant-status">{t("assistantMcpLocked")}</span>
                  <h3>{t("assistantToolsTitle")}</h3>
                  <ul className="assistant-capability-list">
                    {capabilities.map((capability) => (
                      <li key={capability}>{capability}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
};

export default News;
