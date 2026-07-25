import React from "react";
import { useSearchParams } from "react-router-dom";
import { fetchCaseDocumentBlob, sendCaseDocumentEmail } from "../api/caseClient";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";

const DocumentViewer: React.FC = () => {
  const { t, language } = useLanguage();
  const { user } = useAuth();
  const [params] = useSearchParams();
  const iframeRef = React.useRef<HTMLIFrameElement>(null);
  const [recipient, setRecipient] = React.useState(user?.email ?? "");
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState("");
  const [previewText, setPreviewText] = React.useState("");
  const [isLoadingDocument, setIsLoadingDocument] = React.useState(false);
  const [isDownloading, setIsDownloading] = React.useState(false);
  const [isSending, setIsSending] = React.useState(false);

  const caseId = params.get("caseId") ?? "";
  const docId = params.get("docId") ?? "";
  const documentKind = params.get("kind") ?? "";
  const filename = params.get("filename") ?? t("documentViewerUntitled");
  const caseTitle = params.get("caseTitle") ?? "";
  const userId = user?.userId ?? params.get("userId") ?? "";
  const canLoadDocument = Boolean(userId && caseId && docId);
  const documentFormat = ["session_history", "chat_attachment", "generated_document"].includes(documentKind) ? "pdf" : "source";

  React.useEffect(() => {
    if (!canLoadDocument) {
      setPreviewUrl("");
      setPreviewText("");
      setIsLoadingDocument(false);
      return;
    }

    const controller = new AbortController();
    let objectUrl = "";
    setIsLoadingDocument(true);
    setError(null);
    setPreviewUrl("");
    setPreviewText("");

    fetchCaseDocumentBlob({
      userId,
      caseId,
      docId,
      disposition: "inline",
      format: documentFormat,
      signal: controller.signal
    })
      .then((document) => {
        objectUrl = URL.createObjectURL(document.blob);
        setPreviewUrl(objectUrl);
        if (documentKind === "generated_document") {
          return fetchCaseDocumentBlob({
            userId,
            caseId,
            docId,
            disposition: "inline",
            format: "source",
            signal: controller.signal
          })
            .then((sourceDocument) => sourceDocument.blob.text())
            .then((text) => {
              if (!controller.signal.aborted) {
                setPreviewText(text.trim());
              }
            });
        }
        return undefined;
      })
      .catch((loadError) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : t("documentViewerLoadFailed"));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoadingDocument(false);
        }
      });

    return () => {
      controller.abort();
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [canLoadDocument, caseId, docId, documentFormat, documentKind, t, userId]);

  const handlePrint = () => {
    iframeRef.current?.contentWindow?.focus();
    iframeRef.current?.contentWindow?.print();
  };

  const handleSave = async () => {
    if (!canLoadDocument) {
      return;
    }

    setIsDownloading(true);
    try {
      const document = await fetchCaseDocumentBlob({
        userId,
        caseId,
        docId,
        disposition: "attachment",
        format: documentFormat
      });
      const objectUrl = URL.createObjectURL(document.blob);
      const anchor = window.document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = document.filename || filename;
      window.document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
      setError(null);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : t("documentViewerDownloadFailed"));
      setMessage(null);
    } finally {
      setIsDownloading(false);
    }
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
        caseSubject: caseTitle || filename,
        locale: language
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
            <button type="button" className="button ghost" onClick={handleSave} disabled={!canLoadDocument || isDownloading}>
              {isDownloading ? t("documentViewerDownloading") : t("documentViewerSave")}
            </button>
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
          isLoadingDocument ? (
            <p className="hint">{t("documentViewerLoading")}</p>
          ) : previewUrl ? (
            <>
              {previewText ? (
                <article className="document-viewer-text-preview" aria-label={filename}>
                  <pre>{previewText}</pre>
                </article>
              ) : null}
              <iframe
                ref={iframeRef}
                className="document-viewer-frame"
                src={previewUrl}
                title={filename}
              />
            </>
          ) : null
        ) : (
          <p className="hint">{t("documentViewerMissingDocument")}</p>
        )}
      </section>
    </div>
  );
};

export default DocumentViewer;
