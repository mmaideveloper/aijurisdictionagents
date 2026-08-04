import React from "react";
import { useNavigate } from "react-router-dom";
import { useCases, type CaseDocumentRecord } from "../state/CaseProvider";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "./LanguageProvider";
import { BsBoxArrowLeft, BsChevronDown, BsChevronRight } from "react-icons/bs";
import { FaDownload } from "react-icons/fa";
import { caseStatusTranslationKeys } from "../state/caseStatus";
import { fetchCaseExportBlob } from "../api/caseClient";

const statusClass = (status: string) => status.toLowerCase().replace(/\s+/g, "-");

type SidebarProps = {
  onClose?: () => void;
};

export const Sidebar: React.FC<SidebarProps> = ({ onClose }) => {
  const navigate = useNavigate();
  const { cases, activeCase, selectCase, isLoadingCases, caseLoadError } = useCases();
  const { user } = useAuth();
  const { t } = useLanguage();
  const [isSelectedCaseExpanded, setIsSelectedCaseExpanded] = React.useState(false);
  const [exportingCaseId, setExportingCaseId] = React.useState<string | null>(null);
  const exportInFlightCaseId = React.useRef<string | null>(null);
  const [caseExportMessage, setCaseExportMessage] = React.useState<string | null>(null);
  const [caseExportError, setCaseExportError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setIsSelectedCaseExpanded(false);
  }, [activeCase?.id]);

  const openDocument = (document: CaseDocumentRecord) => {
    if (!activeCase) {
      return;
    }
    const params = new URLSearchParams({
      caseId: activeCase.id,
      docId: document.id,
      kind: document.kind,
      filename: document.originalFilename,
      caseTitle: activeCase.title,
      userId: user?.userId ?? ""
    });
    window.open(`/app/documents/view?${params.toString()}`, "_blank", "noopener,noreferrer");
  };

  const exportActiveCase = async (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!activeCase || !user?.userId || exportInFlightCaseId.current !== null) {
      return;
    }

    exportInFlightCaseId.current = activeCase.id;
    setExportingCaseId(activeCase.id);
    setCaseExportError(null);
    setCaseExportMessage(null);
    try {
      const exported = await fetchCaseExportBlob({
        userId: user.userId,
        caseId: activeCase.id
      });
      const objectUrl = URL.createObjectURL(exported.blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = exported.filename;
      anchor.rel = "noopener";
      document.body.appendChild(anchor);
      anchor.click();
      window.setTimeout(() => {
        anchor.remove();
        URL.revokeObjectURL(objectUrl);
      }, 1_000);
      setCaseExportMessage(t("profileCaseExportStarted"));
    } catch (error) {
      setCaseExportError(error instanceof Error ? error.message : t("profileCaseExportFailed"));
    } finally {
      exportInFlightCaseId.current = null;
      setExportingCaseId(null);
    }
  };

  return (
    <aside className="workspace-panel workspace-panel--left">
      <div className="sidebar">
        <div className="sidebar-inner">
          <div className="sidebar-brand">
            <img className="brand-mark" src="/login-shield.png" alt="" aria-hidden="true" />
            <div>
              <strong>{t("appName")}</strong>
              <span>{t("tagline")}</span>
            </div>
            {onClose ? (
              <button
                type="button"
                className="sidebar-close-btn"
                onClick={onClose}
                aria-label={t("sidebarClose")}
              >
                <BsBoxArrowLeft className="sidebar-icon" />
              </button>
            ) : null}
          </div>

          <div className="sidebar-section sidebar-section--cases">
            <div className="sidebar-section__header">
              <h3>{t("sidebarCasesTitle")}</h3>
              <span>{cases.length}</span>
            </div>
            <button
              type="button"
              className="button ghost full sidebar-action"
              onClick={() => navigate("/app/case")}
            >
              {t("sidebarNewCase")}
            </button>
            <div className="case-list-scroll">
              {isLoadingCases ? <p className="hint">{t("sidebarCasesLoading")}</p> : null}
              {caseLoadError ? <p className="form-error">{caseLoadError}</p> : null}
              {!isLoadingCases && cases.length === 0 ? (
                <p className="hint">{t("sidebarCasesEmpty")}</p>
              ) : null}
              <ul className="case-list">
                {cases.map((caseItem) => {
                  const isActive = caseItem.id === activeCase?.id;
                  return (
                    <li key={caseItem.id} className="case-item-container">
                      <button
                        type="button"
                        className={`case-item${isActive ? " active" : ""}`}
                        onClick={() => selectCase(caseItem.id)}
                      >
                        <div className="case-title">
                          <span
                            className={`case-status-dot ${statusClass(caseItem.status)}`}
                            aria-hidden="true"
                          />
                          <div>
                            <strong>{caseItem.title}</strong>
                            <span className="case-meta">{caseItem.workspace.meta}</span>
                          </div>
                        </div>
                        <span className="case-status-label">{t(caseStatusTranslationKeys[caseItem.status])}</span>
                      </button>
                      {isActive ? (
                        <button
                          type="button"
                          className="button ghost icon-button profile-case-export-button case-export-button"
                          onClick={(event) => void exportActiveCase(event)}
                          disabled={exportingCaseId === caseItem.id}
                          aria-busy={exportingCaseId === caseItem.id}
                          aria-label={t("profileCaseExport")}
                          title={t("profileCaseExport")}
                        >
                          <FaDownload aria-hidden="true" />
                        </button>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              {caseExportError ? <p className="form-error" role="alert">{caseExportError}</p> : null}
              {caseExportMessage ? <p className="hint" role="status">{caseExportMessage}</p> : null}
            </div>
          </div>

          {activeCase ? (
            <div className="sidebar-section sidebar-section--selected-case">
              <div className="sidebar-section__header">
                <button
                  type="button"
                  className="sidebar-section__toggle"
                  onClick={() => setIsSelectedCaseExpanded((current) => !current)}
                  aria-expanded={isSelectedCaseExpanded}
                >
                  {isSelectedCaseExpanded ? <BsChevronDown aria-hidden="true" /> : <BsChevronRight aria-hidden="true" />}
                  <h3>{t("sidebarSelectedCaseTitle")}</h3>
                </button>
                <span>{t(caseStatusTranslationKeys[activeCase.status])}</span>
              </div>
              <div className="sidebar-selected-case" hidden={!isSelectedCaseExpanded}>
                <strong>{activeCase.title}</strong>
                <p className="hint">{activeCase.description}</p>
                <dl className="sidebar-case-data">
                  <div>
                    <dt>{t("sidebarSelectedCaseId")}</dt>
                    <dd>{activeCase.id}</dd>
                  </div>
                  <div>
                    <dt>{t("sidebarSelectedCaseCreated")}</dt>
                    <dd>{new Date(activeCase.createdAt).toLocaleString()}</dd>
                  </div>
                  <div>
                    <dt>{t("sidebarSelectedCaseJurisdiction")}</dt>
                    <dd>{activeCase.workspace.jurisdiction}</dd>
                  </div>
                  <div>
                    <dt>{t("sidebarSelectedCaseOutput")}</dt>
                    <dd>{activeCase.workspace.output}</dd>
                  </div>
                </dl>
              </div>
            </div>
          ) : null}

          {activeCase ? (
            <div className="sidebar-section sidebar-section--documents">
              <div className="sidebar-section__header">
                <h3>{t("sidebarSelectedDocuments")}</h3>
                <span>{activeCase.documents.length}</span>
              </div>
              <div className="sidebar-selected-block">
                {activeCase.documents.length > 0 ? (
                  <ul>
                    {activeCase.documents.map((document) => (
                      <li key={document.id}>
                        <button
                          type="button"
                          className="sidebar-document-link"
                          onClick={() => openDocument(document)}
                        >
                          <span title={document.originalFilename}>{document.originalFilename}</span>
                          <small>{document.sizeLabel}</small>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="hint">{t("sidebarSelectedDocumentsEmpty")}</p>
                )}
              </div>
            </div>
          ) : null}

          <div className="sidebar-section">
            <div className="sidebar-section__header">
              <h3>{t("sidebarNavigationTitle")}</h3>
              <span>{t("sidebarComingSoon")}</span>
            </div>
            <div className="sidebar-placeholder">
              {t("sidebarPlaceholder")}
            </div>
          </div>

          <div className="sidebar-footer">
            <span>{t("sidebarFooter")}</span>
          </div>
        </div>
      </div>
    </aside>
  );
};
