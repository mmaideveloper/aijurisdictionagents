import React from "react";
import { LegalDocumentPreview } from "./LegalDocumentPreview";
import { useLanguage } from "./LanguageProvider";
import { displayValue, type PresentationBlock } from "../presentation";

const text = (value: unknown, fallback = ""): string =>
  typeof value === "string" ? value : fallback;

const KeyValueTable: React.FC<{ items: Record<string, unknown> }> = ({ items }) => (
  <div className="assistant-presentation__table-scroll">
    <table className="assistant-presentation__table">
      <tbody>
        {Object.entries(items).map(([key, value]) => (
          <tr key={key}>
            <th scope="row">{key}</th>
            <td>{displayValue(value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const DataTable: React.FC<{ data: Record<string, unknown> }> = ({ data }) => {
  const columns = Array.isArray(data.columns)
    ? data.columns.filter((item): item is string => typeof item === "string").slice(0, 12)
    : [];
  const rows = Array.isArray(data.rows)
    ? data.rows.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null && !Array.isArray(item)).slice(0, 100)
    : [];
  if (columns.length === 0 || rows.length === 0) {
    return null;
  }
  return (
    <div className="assistant-presentation__table-scroll">
      <table className="assistant-presentation__table">
        <thead>
          <tr>{columns.map((column) => <th key={column} scope="col">{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>{columns.map((column) => <td key={column}>{displayValue(row[column])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export const AssistantPresentationBlock: React.FC<{ block: PresentationBlock }> = ({ block }) => {
  const { t } = useLanguage();
  const data = block.data;
  let body: React.ReactNode;

  switch (block.renderer_id) {
    case "document_preview":
      body = (
        <LegalDocumentPreview
          title={text(data.title, "Document")}
          body={text(data.body, block.fallback_text)}
          previewLabel={t("assistantDocumentPreviewLabel")}
          pageLabel={t("assistantDocumentPreviewPage", { number: 1 })}
        />
      );
      break;
    case "key_value_table":
      body = <KeyValueTable items={typeof data.items === "object" && data.items !== null && !Array.isArray(data.items) ? data.items as Record<string, unknown> : {}} />;
      break;
    case "data_table":
      body = <DataTable data={data} />;
      break;
    case "sanitized_json":
      body = <pre className="assistant-presentation__json"><code>{JSON.stringify(data, null, 2)}</code></pre>;
      break;
    case "notice":
      body = (
        <section className="assistant-presentation__notice" role="status">
          <h3>{text(data.title, "Notice")}</h3>
          <p>{text(data.body, block.fallback_text)}</p>
        </section>
      );
      break;
    case "action_link": {
      const href = text(data.href);
      body = href.startsWith("/app/") ? <a href={href}>{text(data.label, "Open")}</a> : <p>{block.fallback_text}</p>;
      break;
    }
    case "result_card":
      body = (
        <section className="assistant-presentation__card">
          <h3>{text(data.title, "Result")}</h3>
          <p>{text(data.summary, block.fallback_text)}</p>
          {Array.isArray(data.items) && data.items.length > 0 ? (
            <ul>{data.items.slice(0, 100).map((item, index) => <li key={index}>{displayValue(item)}</li>)}</ul>
          ) : null}
        </section>
      );
      break;
    case "text":
    default:
      body = <p className="assistant-message__text">{text(data.text, block.fallback_text)}</p>;
  }

  return (
    <div className="assistant-presentation" data-renderer={block.renderer_id}>
      {body}
      {block.notices.length > 0 ? (
        <aside className="assistant-presentation__notices" aria-label={t("assistantPresentationNoticesLabel")}>
          {block.notices.map((notice) => <p key={notice}>{notice}</p>)}
        </aside>
      ) : null}
      {block.citations.length > 0 ? (
        <section className="assistant-presentation__citations" aria-label={t("workspaceCitationsTitle")}>
          <h4>{t("workspaceCitationsTitle")}</h4>
          <ul>{block.citations.map((citation) => <li key={citation}><code>{citation}</code></li>)}</ul>
        </section>
      ) : null}
    </div>
  );
};
