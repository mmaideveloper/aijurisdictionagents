import React from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { normalizeAssistantPresentationText } from "../utils/assistantPresentation";

// Do not load model-authored images (tracking pixels) or execute raw HTML.
// Links are explicit user actions, restricted to web URLs and local app paths.
const safeHref = (url: string): string => {
  const allowed = /^https?:\/\//i.test(url) || (url.startsWith("/") && !url.startsWith("//")) || url.startsWith("#");
  const unsafe = url.includes("\\") || Array.from(url).some((character) => character.charCodeAt(0) <= 32);
  return allowed && !unsafe ? url : "";
};

export const AssistantMarkdown: React.FC<{ text: string }> = ({ text }) => (
  <div className="assistant-markdown">
    <Markdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      disallowedElements={["img", "input"]}
      urlTransform={safeHref}
      components={{
        a: ({ href, children }) => href
          ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
          : <span>{children}</span>,
        table: ({ children }) => <div className="assistant-presentation__table-scroll"><table>{children}</table></div>
      }}
    >
      {normalizeAssistantPresentationText(text)}
    </Markdown>
  </div>
);
