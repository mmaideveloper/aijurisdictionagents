import React from "react";
import type { CaseCitation } from "../state/CaseProvider";

const citationHref = (citation: CaseCitation): string | null => {
  if (citation.sourceType === "law") {
    return citation.sourceId && citation.effectiveFrom
      ? `/sources/${encodeURIComponent(citation.caseId)}/${encodeURIComponent(citation.id)}` : null;
  }
  try {
    const url = new URL(citation.sourceUrl ?? "");
    return url.protocol === "https:" ? url.href : null;
  } catch { return null; }
};

export const CitationLink: React.FC<{ citation: CaseCitation }> = ({ citation }) => {
  const href = citationHref(citation);
  const label = citation.citationLabel || citation.lawNumber || citation.title;
  return href ? <a href={href} target="_blank" rel="noopener noreferrer" onClick={event => {
    if (!href.startsWith("/sources/")) return;
    // Authentication is tab-scoped. A same-origin blank tab inherits sessionStorage;
    // remove its opener before navigating, without persisting credentials in URLs/storage.
    event.preventDefault();
    const tab = window.open("about:blank", "_blank");
    if (tab) { tab.opener = null; tab.location.replace(href); }
  }}>{label}</a> : <strong>{label}</strong>;
};
