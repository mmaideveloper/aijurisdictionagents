import React from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { normalizeAssistantPresentationText } from "../utils/assistantPresentation";

type DocumentLinkPolicy = {
  isAllowed: (href: string) => boolean;
  unavailableLabel: string;
  retryLabel: string;
  retryDisabled: boolean;
  onRetry: () => void;
};

export const AssistantDocumentLinkContext = React.createContext<DocumentLinkPolicy | null>(null);

const linkText = (children: React.ReactNode): string => React.Children.toArray(children).map((child) =>
  typeof child === "string" || typeof child === "number" ? String(child)
    : React.isValidElement<{ children?: React.ReactNode }>(child) ? linkText(child.props.children) : ""
).join("");

const isDocumentAction = (href: string, label: string): boolean => {
  const normalized = label.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const downloadLabel = /stiahn|stahn|download|herunterlad/.test(normalized);
  // Model-authored navigation links are not document downloads. Leave ordinary
  // external source citations and non-download section anchors intact.
  if (downloadLabel && (!href || href.startsWith("#") || href.startsWith("/"))) return true;
  try {
    const url = new URL(href, window.location.origin);
    return url.pathname === "/app/documents/view" || /^\/v1\/cases\/[^/]+\/documents\//.test(url.pathname) ||
      (downloadLabel && (url.origin === window.location.origin ||
        /^\/(?:app(?:\/assistant|\/chat)?|auth)?\/?$/.test(url.pathname)));
  } catch {
    return downloadLabel;
  }
};

// Do not load model-authored images (tracking pixels) or execute raw HTML.
// Links are explicit user actions, restricted to web URLs and local app paths.
const safeHref = (url: string): string => {
  const allowed = /^https?:\/\//i.test(url) || (url.startsWith("/") && !url.startsWith("//")) || url.startsWith("#");
  const unsafe = url.includes("\\") || Array.from(url).some((character) => character.charCodeAt(0) <= 32);
  return allowed && !unsafe ? url : "";
};

export const AssistantMarkdown: React.FC<{ text: string }> = ({ text }) => {
  const policy = React.useContext(AssistantDocumentLinkContext);
  return (
  <div className="assistant-markdown">
    <Markdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      disallowedElements={["img", "input"]}
      urlTransform={safeHref}
      components={{
        a: ({ href, children }) => {
          if (isDocumentAction(href ?? "", linkText(children)) && !policy?.isAllowed(href ?? "")) {
            return policy ? <span role="status">
              {policy.unavailableLabel}{" "}
              <button type="button" className="button ghost" disabled={policy.retryDisabled} onClick={policy.onRetry}>
                {policy.retryLabel}
              </button>
            </span> : <span>{children}</span>;
          }
          return href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>;
        },
        table: ({ children }) => <div className="assistant-presentation__table-scroll"><table>{children}</table></div>
      }}
    >
      {normalizeAssistantPresentationText(text)}
    </Markdown>
  </div>
  );
};
