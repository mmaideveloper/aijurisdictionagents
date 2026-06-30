import React from "react";
import {
  listProviderCredentials,
  ProviderCredential,
  softDeleteProviderCredential,
  updateProviderCredential
} from "../api/providerCredentialsClient";

type EditableFields = {
  display_name: string;
  description: string;
  endpoint: string;
  deployment: string;
  embeddings_model: string;
  api_version: string;
  auth_method: string;
  secret_name: string;
  has_secret: boolean;
  is_enabled: boolean;
};

const editableFromCredential = (credential: ProviderCredential): EditableFields => ({
  display_name: credential.display_name,
  description: credential.description,
  endpoint: credential.endpoint,
  deployment: credential.deployment,
  embeddings_model: credential.embeddings_model,
  api_version: credential.api_version,
  auth_method: credential.auth_method,
  secret_name: credential.secret_name,
  has_secret: credential.has_secret,
  is_enabled: credential.is_enabled
});

const AdminProviderCredentials: React.FC = () => {
  const [credentials, setCredentials] = React.useState<ProviderCredential[]>([]);
  const [selectedKey, setSelectedKey] = React.useState<string>("");
  const [form, setForm] = React.useState<EditableFields | null>(null);
  const [includeDeleted, setIncludeDeleted] = React.useState(false);
  const [status, setStatus] = React.useState("");
  const [error, setError] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [isSaving, setIsSaving] = React.useState(false);

  const selectedCredential = React.useMemo(
    () => credentials.find((item) => item.provider_key === selectedKey) ?? credentials[0],
    [credentials, selectedKey]
  );

  const loadCredentials = React.useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const items = await listProviderCredentials(includeDeleted);
      setCredentials(items);
      const nextSelected = items.find((item) => item.provider_key === selectedKey) ?? items[0];
      setSelectedKey(nextSelected?.provider_key ?? "");
      setForm(nextSelected ? editableFromCredential(nextSelected) : null);
      setStatus(items.length ? "" : "Žiadne záznamy");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Načítanie zlyhalo");
    } finally {
      setIsLoading(false);
    }
  }, [includeDeleted, selectedKey]);

  React.useEffect(() => {
    void loadCredentials();
  }, [loadCredentials]);

  React.useEffect(() => {
    if (selectedCredential) {
      setForm(editableFromCredential(selectedCredential));
    }
  }, [selectedCredential]);

  const updateField = <Key extends keyof EditableFields>(key: Key, value: EditableFields[Key]) => {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  };

  const handleSave = async () => {
    if (!selectedCredential || !form) {
      return;
    }
    setIsSaving(true);
    setError("");
    setStatus("");
    try {
      const updated = await updateProviderCredential(selectedCredential.provider_key, form);
      setCredentials((current) =>
        current.map((item) => (item.provider_key === updated.provider_key ? updated : item))
      );
      setForm(editableFromCredential(updated));
      setStatus("Uložené");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Uloženie zlyhalo");
    } finally {
      setIsSaving(false);
    }
  };

  const handleSoftDelete = async () => {
    if (!selectedCredential) {
      return;
    }
    setIsSaving(true);
    setError("");
    setStatus("");
    try {
      const deleted = await softDeleteProviderCredential(selectedCredential.provider_key);
      setCredentials((current) =>
        includeDeleted
          ? current.map((item) => (item.provider_key === deleted.provider_key ? deleted : item))
          : current.filter((item) => item.provider_key !== deleted.provider_key)
      );
      setSelectedKey("");
      setForm(null);
      setStatus("Soft delete dokončený");
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Vymazanie zlyhalo");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section className="admin-provider-page">
      <div className="admin-provider-header">
        <div>
          <p className="section-eyebrow">Admin</p>
          <h1>Prihlasovacie údaje poskytovateľa</h1>
        </div>
        <div className="admin-provider-actions">
          <label className="admin-provider-toggle">
            <input
              type="checkbox"
              checked={includeDeleted}
              onChange={(event) => setIncludeDeleted(event.target.checked)}
            />
            <span>Zobraziť vymazané</span>
          </label>
          <button type="button" className="secondary-button" onClick={loadCredentials} disabled={isLoading}>
            Obnoviť
          </button>
        </div>
      </div>

      {error ? <p className="form-error">{error}</p> : null}
      {status ? <p className="form-status">{status}</p> : null}

      <div className="admin-provider-layout">
        <div className="admin-provider-list" aria-label="Zoznam poskytovateľov">
          {credentials.map((credential) => (
            <button
              key={credential.provider_key}
              type="button"
              className={`admin-provider-list-item${
                credential.provider_key === selectedCredential?.provider_key ? " is-active" : ""
              }`}
              onClick={() => setSelectedKey(credential.provider_key)}
            >
              <span>
                <strong>{credential.display_name}</strong>
                <small>{credential.provider_key}</small>
              </span>
              <span className={`status-pill ${credential.is_deleted ? "status-pill--deleted" : ""}`}>
                {credential.is_deleted ? "Vymazané" : credential.is_enabled ? "Aktívne" : "Vypnuté"}
              </span>
            </button>
          ))}
        </div>

        <div className="admin-provider-editor">
          {selectedCredential && form ? (
            <>
              <div className="admin-provider-editor-title">
                <h2>{selectedCredential.display_name}</h2>
                <span className="muted-text">Aktualizované {new Date(selectedCredential.updated_at).toLocaleString()}</span>
              </div>
              <div className="admin-provider-form-grid">
                <label>
                  Názov
                  <input value={form.display_name} onChange={(event) => updateField("display_name", event.target.value)} />
                </label>
                <label>
                  Endpoint
                  <input value={form.endpoint} onChange={(event) => updateField("endpoint", event.target.value)} />
                </label>
                <label>
                  Deployment
                  <input value={form.deployment} onChange={(event) => updateField("deployment", event.target.value)} />
                </label>
                <label>
                  Embedding model
                  <input
                    value={form.embeddings_model}
                    onChange={(event) => updateField("embeddings_model", event.target.value)}
                  />
                </label>
                <label>
                  API verzia
                  <input value={form.api_version} onChange={(event) => updateField("api_version", event.target.value)} />
                </label>
                <label>
                  Auth metóda
                  <input value={form.auth_method} onChange={(event) => updateField("auth_method", event.target.value)} />
                </label>
                <label>
                  Secret
                  <input value={form.secret_name} onChange={(event) => updateField("secret_name", event.target.value)} />
                </label>
                <label className="admin-provider-checkbox">
                  <input
                    type="checkbox"
                    checked={form.has_secret}
                    onChange={(event) => updateField("has_secret", event.target.checked)}
                  />
                  <span>Secret je nastavený</span>
                </label>
                <label className="admin-provider-checkbox">
                  <input
                    type="checkbox"
                    checked={form.is_enabled}
                    onChange={(event) => updateField("is_enabled", event.target.checked)}
                  />
                  <span>Aktívne</span>
                </label>
                <label className="admin-provider-form-wide">
                  Popis
                  <textarea value={form.description} onChange={(event) => updateField("description", event.target.value)} />
                </label>
              </div>
              <div className="admin-provider-footer">
                <button
                  type="button"
                  className="primary-button"
                  onClick={handleSave}
                  disabled={isSaving || selectedCredential.is_deleted}
                >
                  Uložiť
                </button>
                <button
                  type="button"
                  className="danger-button"
                  onClick={handleSoftDelete}
                  disabled={isSaving || selectedCredential.is_deleted}
                >
                  Soft delete
                </button>
              </div>
            </>
          ) : (
            <p className="muted-text">Žiadny poskytovateľ nie je vybraný.</p>
          )}
        </div>
      </div>
    </section>
  );
};

export default AdminProviderCredentials;
