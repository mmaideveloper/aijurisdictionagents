import React from "react";
import { useSearchParams } from "react-router-dom";
import { buildCaseDocumentUrl, sendCaseDocumentEmail } from "../api/caseClient";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";

const DocumentViewer: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [params] = useSearchParams();
  const iframeRef = React.useRef<HTMLIFrameElement>(null);
  const [recipient, setRecipient] = React.useState(user?.email ?? "");
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [isSending, setIsSending] = React.useState(false);

  const caseId = params.get("caseId") ?? "";
  const docId = params.get("docId") ?? "";
  const documentKind = params.get("kind") ?? "";
  const filename = params.get("filename") ?? t("documentViewerUntitled");
  const caseTitle = params.get("caseTitle") ?? "";
  const userId = user?.userId ?? "";
  const canLoadDocument = Boolean(userId && caseId && docId);
  const documentFormat = ["session_history", "chat_attachment"].includes(documentKind) ? "pdf" : "source";
  const previewUrl = canLoadDocument
    ? buildCaseDocumentUrl({ userId, caseId, docId, disposition: "inline", format: documentFormat })
    : "";
  const downloadUrl = canLoadDocument
    ? buildCaseDocumentUrl({ userId, caseId, docId, disposition: "attachment", format: documentFormat })
    : "";

  const handlePrint = () => {
    iframeRef.current?.contentWindow?.focus();
    iframeRef.current?.contentWindow?.print();
  };

  const handleSendEmail = async () => {
    if (!recipient.trim()) {
      setError(t("documentViewerEmailRequired"));
      setMessage(null);
      return;
    }
    setIsSending(true);
    try {
      const result = await sendCaseDocumentEmail({
        userId,
        caseId,
        docIds: [docId],
        recipient: recipient.trim(),
        caseSubject: caseTitle || filename
      });
      setError(null);
      setMessage(t("documentViewerEmailSent", { count: result.attachment_count }));
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : t("documentViewerEmailFailed"));
      setMessage(null);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="page document-viewer-page">
      <section className="document-viewer-shell">
        <header className="document-viewer-toolbar">
          <div className="document-viewer-title">
            <span>{t("documentViewerTitle")}</span>
            <strong title={filename}>{filename}</strong>
            {caseTitle ? <small>{caseTitle}</small> : null}
          </div>
          <div className="document-viewer-actions">
            <a className="button ghost" href={downloadUrl}>
              {t("documentViewerSave")}
            </a>
            <button type="button" className="button ghost" onClick={handlePrint} disabled={!previewUrl}>
              {t("documentViewerPrint")}
            </button>
          </div>
        </header>
        <div className="document-viewer-email">
          <label>
            <span>{t("documentViewerRecipient")}</span>
            <input value={recipient} onChange={(event) => setRecipient(event.target.value)} />
          </label>
          <button type="button" className="button primary" onClick={handleSendEmail} disabled={isSending || !canLoadDocument}>
            {isSending ? t("documentViewerSendingEmail") : t("documentViewerSendEmail")}
          </button>
        </div>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        {message ? <p className="hint">{message}</p> : null}
        {canLoadDocument ? (
          <iframe
            ref={iframeRef}
            className="document-viewer-frame"
            src={previewUrl}
            title={filename}
          />
        ) : (
          <p className="hint">{t("documentViewerMissingDocument")}</p>
        )}
      </section>
    </div>
  );
};

export default DocumentViewer;
