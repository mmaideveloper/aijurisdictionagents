import React from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  DocumentTemplateCatalogItem,
  fetchAdminCaseCatalogDocumentTemplate,
  fetchAdminCaseCatalogDocumentTemplatePreviewBlob,
  fetchAdminCaseCatalogDocumentTemplateVersions
} from "../api/adminModelClient";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";

const AdminCaseCatalogTemplatePage: React.FC = () => {
  const { templateKey = "" } = useParams<{ templateKey: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { t } = useLanguage();
  const { user } = useAuth();
  const jurisdiction = searchParams.get("jurisdiction") ?? "";
  const selectedVersion = Number(searchParams.get("version") ?? "0") || undefined;
  const adminAuth = React.useMemo(
    () => ({
      userId: user?.userId ?? "",
      deviceId: user?.deviceId,
      deviceAuthToken: user?.deviceAuthToken
    }),
    [user?.deviceAuthToken, user?.deviceId, user?.userId]
  );
  const [template, setTemplate] = React.useState<DocumentTemplateCatalogItem | null>(null);
  const [versions, setVersions] = React.useState<DocumentTemplateCatalogItem[]>([]);
  const [previewUrl, setPreviewUrl] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let previewObjectUrl = "";
    if (!templateKey || !jurisdiction || !adminAuth.userId) {
      setError(t("adminCaseCatalogTemplateMissingContext"));
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError("");
    setPreviewUrl("");

    Promise.all([
      fetchAdminCaseCatalogDocumentTemplate(adminAuth, templateKey, jurisdiction, selectedVersion),
      fetchAdminCaseCatalogDocumentTemplateVersions(adminAuth, templateKey, jurisdiction)
    ])
      .then(async ([detail, history]) => {
        setTemplate(detail);
        setVersions(history.items);
        const preview = await fetchAdminCaseCatalogDocumentTemplatePreviewBlob(
          adminAuth,
          templateKey,
          jurisdiction,
          detail.version
        );
        previewObjectUrl = URL.createObjectURL(preview.blob);
        setPreviewUrl(previewObjectUrl);
        if (!selectedVersion || selectedVersion !== detail.version) {
          setSearchParams({ jurisdiction, version: String(detail.version) }, { replace: true });
        }
      })
      .catch((loadError) => {
        setError(loadError instanceof Error ? loadError.message : t("adminCaseCatalogTemplateLoadFailed"));
      })
      .finally(() => {
        setIsLoading(false);
      });

    return () => {
      if (previewObjectUrl) {
        URL.revokeObjectURL(previewObjectUrl);
      }
    };
  }, [adminAuth, jurisdiction, selectedVersion, setSearchParams, t, templateKey]);

  const selectVersion = (version: number) => {
    setSearchParams({ jurisdiction, version: String(version) });
  };

  return (
    <div className="page document-viewer-page">
      <section className="document-viewer-shell admin-template-viewer">
        <div className="admin-inline-actions">
          <Link className="button ghost" to="/app/admin">
            {t("adminCaseCatalogBack")}
          </Link>
        </div>
        {template ? (
          <header className="document-viewer-toolbar">
            <div className="document-viewer-title">
              <span>{t("adminCaseCatalogTemplateDetailTitle")}</span>
              <strong>{template.title}</strong>
              <small>
                {template.template_key} | {template.jurisdiction}
                {template.language ? ` / ${template.language}` : ""}
              </small>
            </div>
            <div className="admin-inline-actions">
              <span className="hint">{t("adminCaseCatalogVersionLabel", { version: template.version })}</span>
              {!template.is_latest_version ? <span className="hint">{t("adminCaseCatalogReadOnlyVersion")}</span> : null}
            </div>
          </header>
        ) : null}

        {isLoading ? <p className="hint">{t("adminCaseCatalogTemplateLoading")}</p> : null}
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        {template ? (
          <>
            <section className="admin-panel">
              <div className="admin-template-meta">
                <div>
                  <strong>{t("adminCaseCatalogCategory")}</strong>
                  <span>{template.category}</span>
                </div>
                <div>
                  <strong>{t("adminCaseCatalogTemplateKind")}</strong>
                  <span>{template.template_kind}</span>
                </div>
                <div>
                  <strong>{t("adminCaseCatalogStoredAt")}</strong>
                  <span>{template.stored_at ?? template.created_at ?? t("adminNotConfigured")}</span>
                </div>
                <div>
                  <strong>{t("adminCaseCatalogLatestVersion")}</strong>
                  <span>v{template.latest_version}</span>
                </div>
              </div>
              {template.description ? <p className="admin-muted">{template.description}</p> : null}
            </section>

            <section className="admin-panel">
              <h2>{t("adminCaseCatalogVersionHistory")}</h2>
              <div className="admin-template-version-list">
                {versions.map((item) => (
                  <button
                    key={item.template_id}
                    type="button"
                    className={`admin-template-version ${item.version === template.version ? "is-active" : ""}`}
                    onClick={() => selectVersion(item.version)}
                  >
                    <strong>v{item.version}</strong>
                    <span>{item.stored_at ?? item.created_at ?? t("adminNotConfigured")}</span>
                    <small>{item.is_latest_version ? t("adminCaseCatalogLatestBadge") : t("adminCaseCatalogReadOnlyShort")}</small>
                  </button>
                ))}
              </div>
            </section>

            {previewUrl ? <iframe className="document-viewer-frame" src={previewUrl} title={template.title} /> : null}
          </>
        ) : null}
      </section>
    </div>
  );
};

export default AdminCaseCatalogTemplatePage;
