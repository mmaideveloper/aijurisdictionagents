import React from "react";
import { useNavigate } from "react-router-dom";
import { useLanguage } from "../components/LanguageProvider";
import { useCases } from "../state/CaseProvider";

type IntakeErrors = {
  title: boolean;
  jurisdiction: boolean;
  opposingParty: boolean;
};

const CaseIntake: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const { createCase } = useCases();
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const [title, setTitle] = React.useState("");
  const [jurisdiction, setJurisdiction] = React.useState("");
  const [opposingParty, setOpposingParty] = React.useState("");
  const [files, setFiles] = React.useState<File[]>([]);
  const [showErrors, setShowErrors] = React.useState(false);

  const errors: IntakeErrors = {
    title: title.trim().length === 0,
    jurisdiction: jurisdiction.trim().length === 0,
    opposingParty: opposingParty.trim().length === 0
  };
  const hasErrors = Object.values(errors).some(Boolean);

  const handleFilesSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextFiles = Array.from(event.target.files ?? []);
    if (nextFiles.length === 0) {
      return;
    }

    setFiles((current) => {
      const seen = new Set(current.map((file) => `${file.name}-${file.size}-${file.type}`));
      const deduped = nextFiles.filter((file) => {
        const key = `${file.name}-${file.size}-${file.type}`;
        if (seen.has(key)) {
          return false;
        }
        seen.add(key);
        return true;
      });
      return [...current, ...deduped];
    });
    event.target.value = "";
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setShowErrors(true);
    if (hasErrors) {
      return;
    }

    createCase({
      title,
      jurisdiction,
      opposingParty,
      documents: files.map((file) => ({
        originalFilename: file.name,
        mimeType: file.type || "application/octet-stream",
        size: file.size
      }))
    });
    navigate("/", { replace: true });
  };

  return (
    <div className="page">
      <section className="section-head">
        <h1>{t("caseTitle")}</h1>
        <p>{t("caseSubtitle")}</p>
      </section>
      <section className="case-grid">
        <div className="card">
          <h3>{t("caseDetailsTitle")}</h3>
          <form className="form" onSubmit={handleSubmit}>
            <label>
              <span>{t("caseNameLabel")}</span>
              <input
                type="text"
                placeholder={t("caseNamePlaceholder")}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                aria-invalid={showErrors && errors.title}
              />
              {showErrors && errors.title ? (
                <small className="form-error">{t("caseFieldRequired")}</small>
              ) : null}
            </label>
            <label>
              <span>{t("caseJurisdiction")}</span>
              <input
                type="text"
                placeholder={t("caseJurisdictionPlaceholder")}
                value={jurisdiction}
                onChange={(event) => setJurisdiction(event.target.value)}
                aria-invalid={showErrors && errors.jurisdiction}
              />
              {showErrors && errors.jurisdiction ? (
                <small className="form-error">{t("caseFieldRequired")}</small>
              ) : null}
            </label>
            <label>
              <span>{t("caseOpposingLabel")}</span>
              <input
                type="text"
                placeholder={t("caseOpposingPlaceholder")}
                value={opposingParty}
                onChange={(event) => setOpposingParty(event.target.value)}
                aria-invalid={showErrors && errors.opposingParty}
              />
              {showErrors && errors.opposingParty ? (
                <small className="form-error">{t("caseFieldRequired")}</small>
              ) : null}
            </label>

            <div className="upload upload--intake">
              <div>
                <h3>{t("caseUpload")}</h3>
                <p>{t("caseUploadBody")}</p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                hidden
                onChange={handleFilesSelected}
              />
              <div className="upload-actions">
                <button
                  type="button"
                  className="button ghost"
                  onClick={() => fileInputRef.current?.click()}
                >
                  {t("caseUploadButton")}
                </button>
                <small className="hint">{t("caseUploadOptional")}</small>
              </div>
              <div className="selected-files" aria-live="polite">
                <strong>{t("caseSelectedFilesTitle")}</strong>
                {files.length > 0 ? (
                  <ul className="selected-files__list">
                    {files.map((file) => (
                      <li key={`${file.name}-${file.size}-${file.type}`} className="selected-files__item">
                        <div>
                          <span>{file.name}</span>
                          <small>{Math.max(1, Math.round(file.size / 1024))} KB</small>
                        </div>
                        <button
                          type="button"
                          className="button ghost small"
                          onClick={() =>
                            setFiles((current) =>
                              current.filter(
                                (currentFile) =>
                                  `${currentFile.name}-${currentFile.size}-${currentFile.type}` !==
                                  `${file.name}-${file.size}-${file.type}`
                              )
                            )
                          }
                        >
                          {t("caseRemoveFile")}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="hint">{t("caseNoFilesSelected")}</p>
                )}
              </div>
              <small className="hint">{t("caseStorageMode")}</small>
            </div>

            {showErrors && hasErrors ? (
              <p className="form-error">{t("caseFormValidationMessage")}</p>
            ) : null}

            <button type="submit" className="button primary full">
              {t("caseStartChat")}
            </button>
          </form>
        </div>
      </section>
    </div>
  );
};

export default CaseIntake;
