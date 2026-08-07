import React from "react";

type LegalDocumentPreviewProps = {
  title: string;
  body: string;
  previewLabel: string;
  pageLabel: string;
  className?: string;
};

const headingPattern = /^\s*(?:#{1,6}\s+|\*\*|__)?(\d+[.)]?\s+.+?)(?:\*\*|__)?\s*$/;
const emphasizedHeadingPattern = /^\s*(?:#{1,6}\s+(.+)|\*\*(.+)\*\*|__(.+)__)\s*$/;
const separatorPattern = /^\s*(?:---+|___+|\*\*\*+)\s*$/;
const tableDividerPattern = /^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$/;

export const stripDocumentMarkdown = (value: string): string =>
  value
    .trim()
    .replace(/^#{1,6}\s+/, "")
    .replace(/^\*\*(.+)\*\*$/, "$1")
    .replace(/^__(.+)__$/, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .trim();

export const splitLegalDocumentSource = (source: string, fallbackTitle: string): { title: string; body: string } => {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const titleIndex = lines.findIndex((line) => line.trim());
  if (titleIndex < 0) {
    return { title: fallbackTitle, body: "" };
  }
  const firstLine = lines[titleIndex]?.trim() ?? "";
  const isHeading = emphasizedHeadingPattern.test(firstLine) || /^\s*#{1,6}\s+/.test(firstLine);
  return {
    title: isHeading ? stripDocumentMarkdown(firstLine) : fallbackTitle,
    body: lines.slice(isHeading ? titleIndex + 1 : titleIndex).join("\n").trim()
  };
};

const inlineText = (value: string): React.ReactNode[] =>
  value.split(/(\*\*[^*]+\*\*|__[^_]+__)/g).filter(Boolean).map((part, index) => {
    const bold = /^(?:\*\*|__)(.+)(?:\*\*|__)$/.exec(part);
    return bold ? <strong key={`${part}-${index}`}>{bold[1]}</strong> : <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>;
  });

const tableCells = (line: string): string[] =>
  line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(stripDocumentMarkdown);

export const LegalDocumentBody: React.FC<{ body: string }> = ({ body }) => {
  const lines = body.replace(/\r\n/g, "\n").split("\n");
  const nodes: React.ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const rawLine = lines[index] ?? "";
    const line = rawLine.trim();
    if (!line || separatorPattern.test(line)) {
      index += 1;
      continue;
    }

    if (line.startsWith("|") && (lines[index + 1]?.includes("|") ?? false)) {
      const rows: string[][] = [];
      while (index < lines.length && (lines[index]?.trim().startsWith("|") ?? false)) {
        const tableLine = lines[index]?.trim() ?? "";
        if (!tableDividerPattern.test(tableLine)) {
          rows.push(tableCells(tableLine));
        }
        index += 1;
      }
      if (rows.length > 0) {
        const [header, ...dataRows] = rows;
        nodes.push(
          <div className="legal-document-table-wrap" key={`table-${nodes.length}`}>
            <table className="legal-document-table">
              <thead><tr>{header?.map((cell, cellIndex) => <th key={`${cell}-${cellIndex}`}>{cell}</th>)}</tr></thead>
              <tbody>{dataRows.map((row, rowIndex) => <tr key={`row-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`${cell}-${cellIndex}`}>{cell}</td>)}</tr>)}</tbody>
            </table>
          </div>
        );
      }
      continue;
    }

    const emphasized = emphasizedHeadingPattern.exec(line);
    const numbered = headingPattern.exec(line);
    if (emphasized || numbered) {
      const heading = stripDocumentMarkdown(emphasized?.[1] ?? emphasized?.[2] ?? emphasized?.[3] ?? numbered?.[1] ?? line);
      nodes.push(<h4 key={`heading-${nodes.length}`}>{heading}</h4>);
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index]?.trim() ?? "")) {
        items.push((lines[index]?.trim() ?? "").replace(/^[-*]\s+/, ""));
        index += 1;
      }
      nodes.push(<ul key={`list-${nodes.length}`}>{items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{inlineText(item)}</li>)}</ul>);
      continue;
    }

    if (/^\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+[.)]\s+/.test(lines[index]?.trim() ?? "")) {
        items.push((lines[index]?.trim() ?? "").replace(/^\d+[.)]\s+/, ""));
        index += 1;
      }
      nodes.push(<ol key={`ordered-${nodes.length}`}>{items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{inlineText(item)}</li>)}</ol>);
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length) {
      const candidate = lines[index]?.trim() ?? "";
      if (!candidate || separatorPattern.test(candidate) || candidate.startsWith("|") || /^[-*]\s+/.test(candidate) || /^\d+[.)]\s+/.test(candidate) || emphasizedHeadingPattern.test(candidate)) {
        break;
      }
      paragraph.push(candidate.replace(/^>\s?/, ""));
      index += 1;
    }
    if (paragraph.length > 0) {
      nodes.push(<p key={`paragraph-${nodes.length}`}>{inlineText(paragraph.join(" "))}</p>);
    } else {
      index += 1;
    }
  }

  return <>{nodes}</>;
};

export const LegalDocumentPreview: React.FC<LegalDocumentPreviewProps> = ({
  title,
  body,
  previewLabel,
  pageLabel,
  className = ""
}) => (
  <article className={`assistant-document-preview ${className}`.trim()} aria-label={`${title} – ${previewLabel}`}>
    <div className="assistant-document-preview__sheet">
      <header className="assistant-document-preview__letterhead">
        <span>JurisDigta</span>
        <small>{previewLabel}</small>
      </header>
      <div className="assistant-document-preview__page-marker">{pageLabel}</div>
      <h3>{stripDocumentMarkdown(title)}</h3>
      <div className="assistant-document-preview__content"><LegalDocumentBody body={body} /></div>
    </div>
  </article>
);
