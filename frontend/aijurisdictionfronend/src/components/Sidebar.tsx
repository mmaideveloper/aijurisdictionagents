import React from "react";
import { useCases } from "../state/CaseProvider";
import { useLanguage } from "./LanguageProvider";

const statusClass = (status: string) => status.toLowerCase().replace(/\s+/g, "-");

const BookOpenIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      d="M3.5 4h7c1.66 0 3 1.34 3 3v12c0-1.1-.9-2-2-2h-8V4z"
      fill="currentColor"
      opacity="0.2"
    />
    <path
      d="M20.5 4h-7c-1.66 0-3 1.34-3 3v12c0-1.1.9-2 2-2h8V4z"
      fill="currentColor"
      opacity="0.2"
    />
    <path
      d="M10.5 6c0-1.1-.9-2-2-2H3.5v14h8c.55 0 1 .45 1 1V6zm-7 10.5V5.5h5c.28 0 .5.22.5.5v10.5H3.5zm17-12V18h-8c-.55 0-1 .45-1 1V7c0-1.1.9-2 2-2h7zm-1.5 12.5V5.5h-5c-.28 0-.5.22-.5.5v10.5h5.5z"
      fill="currentColor"
    />
  </svg>
);

type SidebarProps = {
  onClose?: () => void;
  open?: boolean;
};

export const Sidebar: React.FC<SidebarProps> = ({ onClose, open = true }) => {
  const { cases, activeCase, createCase, setActiveCase } = useCases();
  const { t } = useLanguage();

  return (
    <aside
      className={`workspace-panel workspace-panel--left${open ? "" : " is-collapsed"}`}
      aria-hidden={!open}
    >
      <div className={`sidebar${open ? "" : " sidebar--collapsed"}`}>
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
                className="sidebar-bubble sidebar-bubble--close"
                onClick={onClose}
                aria-label="Close sidebar"
              >
                <BookOpenIcon />
              </button>
            ) : null}
          </div>

          <div className="sidebar-section sidebar-section--cases">
            <div className="sidebar-section__header">
              <h3>Cases</h3>
              <span>{cases.length}</span>
            </div>
            <button type="button" className="button ghost full sidebar-action" onClick={createCase}>
              + New case
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
                        onClick={() => setActiveCase(caseItem.id)}
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
                        <span className="case-status-label">{caseItem.status}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-section__header">
              <h3>Navigation</h3>
              <span>Coming soon</span>
            </div>
            <div className="sidebar-placeholder">
              Add shortcuts to case tools, reports, and settings here.
            </div>
          </div>

          <div className="sidebar-footer">
            <span>Workspace controls</span>
          </div>
        </div>
      </div>
    </aside>
  );
};
