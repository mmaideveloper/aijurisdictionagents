import React from "react";
import { useNavigate } from "react-router-dom";
import { useCases } from "../state/CaseProvider";
import { useLanguage } from "./LanguageProvider";
import { BsBoxArrowLeft } from "react-icons/bs";
import { caseStatusTranslationKeys } from "../state/caseStatus";

const statusClass = (status: string) => status.toLowerCase().replace(/\s+/g, "-");

type SidebarProps = {
  onClose?: () => void;
};

export const Sidebar: React.FC<SidebarProps> = ({ onClose }) => {
  const navigate = useNavigate();
  const { cases, activeCase, selectCase } = useCases();
  const { t } = useLanguage();

  return (
    <aside className="workspace-panel workspace-panel--left">
      <div className="sidebar">
        <div className="sidebar-inner">
          <div className="sidebar-brand">
            <div className="brand-mark" aria-hidden="true">
              AJ
            </div>
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
              <ul className="case-list">
                {cases.map((caseItem) => {
                  const isActive = caseItem.id === activeCase?.id;
                  return (
                    <li key={caseItem.id}>
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
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>

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
