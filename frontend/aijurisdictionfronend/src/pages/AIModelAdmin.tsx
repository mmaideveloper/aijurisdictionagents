import React from "react";
import { FaDownload, FaKey, FaPlus, FaRoute, FaServer, FaSyncAlt, FaTrash, FaUserPlus, FaUsers } from "react-icons/fa";
import {
  AIModelAdminDashboard,
  OllamaModelInventory,
  fetchAIModelAdminDashboard,
  fetchOllamaModels,
  upsertAIModelProvider,
  upsertAIModelProfile,
  upsertAIModelGroup,
  addAIModelGroupMember,
  upsertAIModelRoutePolicy,
  upsertAIModelCredential,
  importOllamaModel,
  removeOllamaModel,
  updateAdminUser
} from "../api/adminModelClient";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";

type AdminSection = "users" | "providers" | "profiles" | "credentials" | "groups" | "policies" | "ollama" | "audit";

const emptyProvider = {
  provider_code: "",
  provider_type: "azurefoundry",
  display_name: "",
  base_url: "",
  region: "",
  data_zone: "eu",
  health_check_url: "",
  is_external: true,
  is_local: false,
  enabled: true,
  reason: ""
};

const emptyProfile = {
  provider_id: "",
  model_code: "",
  deployment_name: "",
  input_price_per_1m: 0,
  cached_input_price_per_1m: 0,
  output_price_per_1m: 0,
  billing_currency: "EUR",
  eu_data_zone_capable: true,
  is_default_for_free: false,
  enabled: true,
  reason: ""
};

const emptyCredential = {
  provider_id: "",
  credential_name: "default",
  secret_type: "api_key",
  secret_value: "",
  enabled: true,
  reason: ""
};

const emptyGroup = {
  group_code: "",
  display_name: "",
  priority: 10,
  enabled: true,
  reason: ""
};

const emptyPolicy = {
  task_type: "default",
  plan_code: "case",
  model_group_id: null as string | null,
  preferred_external_model_profile_id: null as string | null,
  preferred_local_model_profile_id: "local_ollama_default" as string | null,
  allow_external: true,
  require_external_ack: true,
  require_eu_data_zone: true,
  fallback_local_on_error: true,
  fallback_local_on_budget: true,
  max_cost_eur: 0,
  priority: 0,
  enabled: true,
  reason: ""
};

const AIModelAdmin: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [activeSection, setActiveSection] = React.useState<AdminSection>("users");
  const [dashboard, setDashboard] = React.useState<AIModelAdminDashboard | null>(null);
  const [ollamaInventory, setOllamaInventory] = React.useState<OllamaModelInventory | null>(null);
  const [providerForm, setProviderForm] = React.useState(emptyProvider);
  const [profileForm, setProfileForm] = React.useState(emptyProfile);
  const [credentialForm, setCredentialForm] = React.useState(emptyCredential);
  const [groupForm, setGroupForm] = React.useState(emptyGroup);
  const [policyForm, setPolicyForm] = React.useState(emptyPolicy);
  const [selectedGroupId, setSelectedGroupId] = React.useState("");
  const [selectedUserId, setSelectedUserId] = React.useState("");
  const [ollamaModel, setOllamaModel] = React.useState("");
  const [ollamaReason, setOllamaReason] = React.useState("");
  const [ollamaRemoveReason, setOllamaRemoveReason] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [error, setError] = React.useState("");

  const adminUserId = user?.userId ?? "";

  const reload = React.useCallback(async () => {
    if (!adminUserId) return;
    setError("");
    try {
      const nextDashboard = await fetchAIModelAdminDashboard(adminUserId);
      setDashboard(nextDashboard);
      const firstProvider = nextDashboard.providers[0];
      const localProfile = nextDashboard.profiles.find((profile) => profile.model_profile_id === "local_ollama_default");
      setProfileForm((current) => ({ ...current, provider_id: current.provider_id || firstProvider?.provider_id || "" }));
      setCredentialForm((current) => ({ ...current, provider_id: current.provider_id || firstProvider?.provider_id || "" }));
      setPolicyForm((current) => ({
        ...current,
        preferred_local_model_profile_id: current.preferred_local_model_profile_id || localProfile?.model_profile_id || null
      }));
      setSelectedGroupId((current) => current || nextDashboard.groups[0]?.model_group_id || "");
      setSelectedUserId((current) => current || nextDashboard.users[0]?.user_id || "");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("adminLoadFailed"));
    }
  }, [adminUserId, t]);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  const reloadOllama = React.useCallback(async () => {
    if (!adminUserId) return;
    try {
      setOllamaInventory(await fetchOllamaModels(adminUserId));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("adminOllamaLoadFailed"));
    }
  }, [adminUserId, t]);

  React.useEffect(() => {
    void reloadOllama();
  }, [reloadOllama]);

  const runAction = async (action: () => Promise<unknown>, successMessage: string) => {
    setError("");
    setStatus("");
    try {
      await action();
      setStatus(successMessage);
      await reload();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : t("adminSaveFailed"));
    }
  };

  const localProfiles = dashboard?.profiles.filter((profile) => profile.model_profile_id.includes("local") || profile.provider_id.includes("local")) ?? [];
  const externalProfiles = dashboard?.profiles.filter((profile) => !localProfiles.includes(profile)) ?? [];

  const sections: Array<{ key: AdminSection; label: string; icon: React.ReactNode }> = [
    { key: "users", label: t("adminUsersTitle"), icon: <FaUsers aria-hidden="true" /> },
    { key: "providers", label: t("adminProvidersTitle"), icon: <FaServer aria-hidden="true" /> },
    { key: "profiles", label: t("adminProfilesTitle"), icon: <FaServer aria-hidden="true" /> },
    { key: "credentials", label: t("adminCredentialsTitle"), icon: <FaKey aria-hidden="true" /> },
    { key: "groups", label: t("adminGroupsTitle"), icon: <FaUserPlus aria-hidden="true" /> },
    { key: "policies", label: t("adminPoliciesTitle"), icon: <FaRoute aria-hidden="true" /> },
    { key: "ollama", label: t("adminOllamaTitle"), icon: <FaDownload aria-hidden="true" /> },
    { key: "audit", label: t("adminAuditTitle"), icon: <FaKey aria-hidden="true" /> }
  ];

  return (
    <main className="app-shell admin-models">
      <section className="page-heading">
        <div>
          <p className="eyebrow">{t("adminEyebrow")}</p>
          <h1>{t("adminTitle")}</h1>
          <p>{t("adminSubtitle")}</p>
        </div>
        <button className="icon-button" type="button" onClick={() => void reload()} aria-label={t("adminRefresh")}>
          <FaSyncAlt aria-hidden="true" />
        </button>
      </section>

      {status ? <p className="form-success">{status}</p> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}

      <section className="admin-alert">
        <strong>{t("adminExternalWarningTitle")}</strong>
        <span>{t("adminExternalWarningBody")}</span>
      </section>

      <div className="admin-workspace">
        <aside className="admin-sidebar" aria-label={t("navAdmin")}>
          {sections.map((section) => (
            <button
              key={section.key}
              type="button"
              className={`admin-sidebar__item ${activeSection === section.key ? "is-active" : ""}`}
              onClick={() => setActiveSection(section.key)}
            >
              {section.icon}
              <span>{section.label}</span>
            </button>
          ))}
        </aside>

        <section className="admin-content">
          {activeSection === "users" ? (
            <section className="admin-table-section">
              <h2>{t("adminUsersTitle")}</h2>
              <div className="admin-table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{t("adminUser")}</th>
                      <th>{t("adminRole")}</th>
                      <th>{t("adminStatus")}</th>
                      <th>{t("adminAction")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard?.users.map((item) => (
                      <tr key={item.user_id}>
                        <td>{item.full_name} ({item.email})</td>
                        <td>{item.role}</td>
                        <td>{item.is_enabled ? t("adminEnabled") : t("adminDisabled")}</td>
                        <td>
                          <button
                            className="button ghost"
                            type="button"
                            onClick={() => void runAction(
                              () => updateAdminUser(adminUserId, item.user_id, {
                                role: item.role === "admin" ? "user" : "admin",
                                is_enabled: item.is_enabled,
                                reason: "Updated from admin user management."
                              }),
                              t("adminSaved")
                            )}
                          >
                            {item.role === "admin" ? t("adminMakeUser") : t("adminMakeAdmin")}
                          </button>
                          <button
                            className="button ghost"
                            type="button"
                            onClick={() => void runAction(
                              () => updateAdminUser(adminUserId, item.user_id, {
                                role: item.role === "admin" ? "admin" : "user",
                                is_enabled: !item.is_enabled,
                                reason: "Updated from admin user management."
                              }),
                              t("adminSaved")
                            )}
                          >
                            {item.is_enabled ? t("adminDisableUser") : t("adminEnableUser")}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {activeSection === "providers" ? (
            <form className="admin-panel" onSubmit={(event) => {
              event.preventDefault();
              void runAction(() => upsertAIModelProvider(adminUserId, providerForm), t("adminSaved"));
            }}>
              <h2>{t("adminProvidersTitle")}</h2>
              <label>{t("adminProviderCode")}<input value={providerForm.provider_code} onChange={(event) => setProviderForm({ ...providerForm, provider_code: event.target.value })} /></label>
              <label>{t("adminProviderType")}<select value={providerForm.provider_type} onChange={(event) => setProviderForm({ ...providerForm, provider_type: event.target.value })}><option value="local">local</option><option value="azurefoundry">azurefoundry</option><option value="openai">openai</option><option value="openai_compatible">openai_compatible</option></select></label>
              <label>{t("adminDisplayName")}<input value={providerForm.display_name} onChange={(event) => setProviderForm({ ...providerForm, display_name: event.target.value })} /></label>
              <label>{t("adminBaseUrl")}<input value={providerForm.base_url} onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })} /></label>
              <label>{t("adminRegion")}<input value={providerForm.region} onChange={(event) => setProviderForm({ ...providerForm, region: event.target.value })} /></label>
              <div className="admin-toggle-row">
                <label><input type="checkbox" checked={providerForm.is_external} onChange={(event) => setProviderForm({ ...providerForm, is_external: event.target.checked })} />{t("adminExternal")}</label>
                <label><input type="checkbox" checked={providerForm.is_local} onChange={(event) => setProviderForm({ ...providerForm, is_local: event.target.checked })} />{t("adminLocal")}</label>
                <label><input type="checkbox" checked={providerForm.enabled} onChange={(event) => setProviderForm({ ...providerForm, enabled: event.target.checked })} />{t("adminEnabled")}</label>
              </div>
              <button className="primary-button" type="submit"><FaPlus aria-hidden="true" />{t("adminSaveProvider")}</button>
            </form>
          ) : null}

          {activeSection === "profiles" ? (
            <form className="admin-panel" onSubmit={(event) => {
              event.preventDefault();
              void runAction(() => upsertAIModelProfile(adminUserId, profileForm), t("adminSaved"));
            }}>
              <h2>{t("adminProfilesTitle")}</h2>
              <label>{t("adminProvider")}<select value={profileForm.provider_id} onChange={(event) => setProfileForm({ ...profileForm, provider_id: event.target.value })}><option value="">{t("adminSelect")}</option>{dashboard?.providers.map((provider) => <option key={provider.provider_id} value={provider.provider_id}>{provider.display_name}</option>)}</select></label>
              <label>{t("adminModelCode")}<input value={profileForm.model_code} onChange={(event) => setProfileForm({ ...profileForm, model_code: event.target.value })} /></label>
              <label>{t("adminDeployment")}<input value={profileForm.deployment_name} onChange={(event) => setProfileForm({ ...profileForm, deployment_name: event.target.value })} /></label>
              <div className="admin-price-grid">
                <label>{t("adminInputPrice")}<input type="number" min="0" step="0.0001" value={profileForm.input_price_per_1m} onChange={(event) => setProfileForm({ ...profileForm, input_price_per_1m: Number(event.target.value) })} /></label>
                <label>{t("adminCachedInputPrice")}<input type="number" min="0" step="0.0001" value={profileForm.cached_input_price_per_1m} onChange={(event) => setProfileForm({ ...profileForm, cached_input_price_per_1m: Number(event.target.value) })} /></label>
                <label>{t("adminOutputPrice")}<input type="number" min="0" step="0.0001" value={profileForm.output_price_per_1m} onChange={(event) => setProfileForm({ ...profileForm, output_price_per_1m: Number(event.target.value) })} /></label>
              </div>
              <div className="admin-toggle-row">
                <label><input type="checkbox" checked={profileForm.eu_data_zone_capable} onChange={(event) => setProfileForm({ ...profileForm, eu_data_zone_capable: event.target.checked })} />{t("adminEuDataZone")}</label>
                <label><input type="checkbox" checked={profileForm.enabled} onChange={(event) => setProfileForm({ ...profileForm, enabled: event.target.checked })} />{t("adminEnabled")}</label>
              </div>
              <button className="primary-button" type="submit"><FaPlus aria-hidden="true" />{t("adminSaveProfile")}</button>
            </form>
          ) : null}

          {activeSection === "credentials" ? (
            <form className="admin-panel" onSubmit={(event) => {
              event.preventDefault();
              void runAction(() => upsertAIModelCredential(adminUserId, credentialForm), t("adminSaved"));
            }}>
              <h2>{t("adminCredentialsTitle")}</h2>
              <label>{t("adminProvider")}<select value={credentialForm.provider_id} onChange={(event) => setCredentialForm({ ...credentialForm, provider_id: event.target.value })}><option value="">{t("adminSelect")}</option>{dashboard?.providers.map((provider) => <option key={provider.provider_id} value={provider.provider_id}>{provider.display_name}</option>)}</select></label>
              <label>{t("adminCredentialName")}<input value={credentialForm.credential_name} onChange={(event) => setCredentialForm({ ...credentialForm, credential_name: event.target.value })} /></label>
              <label>{t("adminCredentialType")}<input value={credentialForm.secret_type} onChange={(event) => setCredentialForm({ ...credentialForm, secret_type: event.target.value })} /></label>
              <label>{t("adminCredentialValue")}<input type="password" value={credentialForm.secret_value} onChange={(event) => setCredentialForm({ ...credentialForm, secret_value: event.target.value })} /></label>
              <div className="admin-toggle-row"><label><input type="checkbox" checked={credentialForm.enabled} onChange={(event) => setCredentialForm({ ...credentialForm, enabled: event.target.checked })} />{t("adminEnabled")}</label></div>
              <button className="primary-button" type="submit"><FaKey aria-hidden="true" />{t("adminSaveCredential")}</button>
              <div className="admin-table-scroll"><table><thead><tr><th>{t("adminProvider")}</th><th>{t("adminCredentialName")}</th><th>{t("adminCredentialType")}</th><th>{t("adminCredentialPreview")}</th><th>{t("adminStatus")}</th></tr></thead><tbody>{dashboard?.credentials.map((credential) => <tr key={credential.credential_id}><td>{credential.provider_id}</td><td>{credential.credential_name}</td><td>{credential.secret_type}</td><td>{credential.secret_preview}</td><td>{credential.enabled ? t("adminEnabled") : t("adminDisabled")}</td></tr>)}</tbody></table></div>
            </form>
          ) : null}

          {activeSection === "groups" ? (
            <section className="admin-grid">
              <form className="admin-panel" onSubmit={(event) => {
                event.preventDefault();
                void runAction(() => upsertAIModelGroup(adminUserId, groupForm), t("adminSaved"));
              }}>
                <h2>{t("adminGroupsTitle")}</h2>
                <label>{t("adminGroupCode")}<input value={groupForm.group_code} onChange={(event) => setGroupForm({ ...groupForm, group_code: event.target.value })} /></label>
                <label>{t("adminDisplayName")}<input value={groupForm.display_name} onChange={(event) => setGroupForm({ ...groupForm, display_name: event.target.value })} /></label>
                <label>{t("adminPriority")}<input type="number" value={groupForm.priority} onChange={(event) => setGroupForm({ ...groupForm, priority: Number(event.target.value) })} /></label>
                <button className="primary-button" type="submit"><FaPlus aria-hidden="true" />{t("adminSaveGroup")}</button>
              </form>
              <form className="admin-panel" onSubmit={(event) => {
                event.preventDefault();
                void runAction(() => addAIModelGroupMember(adminUserId, selectedGroupId, selectedUserId), t("adminSaved"));
              }}>
                <h2>{t("adminMembersTitle")}</h2>
                <label>{t("adminGroup")}<select value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>{dashboard?.groups.map((group) => <option key={group.model_group_id} value={group.model_group_id}>{group.display_name}</option>)}</select></label>
                <label>{t("adminUser")}<select value={selectedUserId} onChange={(event) => setSelectedUserId(event.target.value)}>{dashboard?.users.map((item) => <option key={item.user_id} value={item.user_id}>{item.full_name} ({item.email})</option>)}</select></label>
                <button className="primary-button" type="submit"><FaUserPlus aria-hidden="true" />{t("adminAssignUser")}</button>
              </form>
            </section>
          ) : null}

          {activeSection === "policies" ? (
            <form className="admin-panel" onSubmit={(event) => {
              event.preventDefault();
              void runAction(() => upsertAIModelRoutePolicy(adminUserId, policyForm), t("adminSaved"));
            }}>
              <h2>{t("adminPoliciesTitle")}</h2>
              <div className="admin-price-grid">
                <label>{t("adminTaskType")}<input value={policyForm.task_type} onChange={(event) => setPolicyForm({ ...policyForm, task_type: event.target.value })} /></label>
                <label>{t("adminPlanCode")}<input value={policyForm.plan_code} onChange={(event) => setPolicyForm({ ...policyForm, plan_code: event.target.value })} /></label>
                <label>{t("adminPriority")}<input type="number" value={policyForm.priority} onChange={(event) => setPolicyForm({ ...policyForm, priority: Number(event.target.value) })} /></label>
              </div>
              <div className="admin-price-grid">
                <label>{t("adminGroup")}<select value={policyForm.model_group_id ?? ""} onChange={(event) => setPolicyForm({ ...policyForm, model_group_id: event.target.value || null })}><option value="">{t("adminDefaultPolicy")}</option>{dashboard?.groups.map((group) => <option key={group.model_group_id} value={group.model_group_id}>{group.display_name}</option>)}</select></label>
                <label>{t("adminExternalModel")}<select value={policyForm.preferred_external_model_profile_id ?? ""} onChange={(event) => setPolicyForm({ ...policyForm, preferred_external_model_profile_id: event.target.value || null })}><option value="">{t("adminSelect")}</option>{externalProfiles.map((profile) => <option key={profile.model_profile_id} value={profile.model_profile_id}>{profile.model_code}</option>)}</select></label>
                <label>{t("adminLocalModel")}<select value={policyForm.preferred_local_model_profile_id ?? ""} onChange={(event) => setPolicyForm({ ...policyForm, preferred_local_model_profile_id: event.target.value || null })}><option value="">{t("adminSelect")}</option>{localProfiles.map((profile) => <option key={profile.model_profile_id} value={profile.model_profile_id}>{profile.model_code}</option>)}</select></label>
              </div>
              <div className="admin-toggle-row">
                <label><input type="checkbox" checked={policyForm.allow_external} onChange={(event) => setPolicyForm({ ...policyForm, allow_external: event.target.checked })} />{t("adminAllowExternal")}</label>
                <label><input type="checkbox" checked={policyForm.require_external_ack} onChange={(event) => setPolicyForm({ ...policyForm, require_external_ack: event.target.checked })} />{t("adminRequireAck")}</label>
                <label><input type="checkbox" checked={policyForm.fallback_local_on_budget} onChange={(event) => setPolicyForm({ ...policyForm, fallback_local_on_budget: event.target.checked })} />{t("adminBudgetFallback")}</label>
              </div>
              <button className="primary-button" type="submit"><FaPlus aria-hidden="true" />{t("adminSavePolicy")}</button>
            </form>
          ) : null}

          {activeSection === "ollama" ? (
            <section className="admin-grid">
              <form className="admin-panel" onSubmit={(event) => {
                event.preventDefault();
                void runAction(async () => {
                  await importOllamaModel(adminUserId, ollamaModel, ollamaReason);
                  setOllamaModel("");
                  setOllamaReason("");
                  await reloadOllama();
                }, t("adminOllamaImportStarted"));
              }}>
                <h2>{t("adminOllamaImportTitle")}</h2>
                <label>{t("adminOllamaModelTag")}<input value={ollamaModel} onChange={(event) => setOllamaModel(event.target.value)} placeholder="qwen3:1.7b" /></label>
                <label>{t("adminReason")}<input value={ollamaReason} onChange={(event) => setOllamaReason(event.target.value)} /></label>
                <button className="primary-button" type="submit" disabled={!ollamaModel.trim() || !ollamaReason.trim()}><FaDownload aria-hidden="true" />{t("adminOllamaImport")}</button>
              </form>

              <section className="admin-table-section admin-panel--wide">
                <div className="admin-section-heading">
                  <h2>{t("adminOllamaTitle")}</h2>
                  <button className="secondary-button" type="button" onClick={() => void reloadOllama()}>{t("adminRefresh")}</button>
                </div>
                <p className="admin-muted">{ollamaInventory?.base_url ?? "http://127.0.0.1:11434"}</p>
                <label>{t("adminOllamaRemoveReason")}<input value={ollamaRemoveReason} onChange={(event) => setOllamaRemoveReason(event.target.value)} /></label>
                <div className="admin-table-scroll">
                  <table>
                    <thead><tr><th>{t("adminModelCode")}</th><th>{t("adminStatus")}</th><th>{t("adminProfilesTitle")}</th><th>{t("adminAction")}</th></tr></thead>
                    <tbody>{ollamaInventory?.models.map((item) => (
                      <tr key={item.name}>
                        <td>{item.name}<br /><small>{formatModelSize(item.size)}</small></td>
                        <td>
                          {item.is_default ? t("adminOllamaDefault") : item.is_running ? t("adminOllamaRunning") : t("adminOllamaUnused")}
                          {item.removal_blockers.length ? <ul className="admin-compact-list">{item.removal_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul> : null}
                        </td>
                        <td>{item.configured_profile_ids.length ? item.configured_profile_ids.join(", ") : t("adminNotConfigured")}</td>
                        <td>
                          <button
                            className="button ghost"
                            type="button"
                            disabled={!item.removable || !ollamaRemoveReason.trim()}
                            title={item.removal_blockers.join(" ")}
                            onClick={() => void runAction(async () => {
                              await removeOllamaModel(adminUserId, item.name, ollamaRemoveReason);
                              setOllamaRemoveReason("");
                              await reloadOllama();
                            }, t("adminOllamaRemoveStarted"))}
                          >
                            <FaTrash aria-hidden="true" />{t("adminOllamaRemove")}
                          </button>
                        </td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              </section>
            </section>
          ) : null}

          {activeSection === "audit" ? (
            <section className="admin-table-section">
              <h2>{t("adminAuditTitle")}</h2>
              <div className="admin-table-scroll">
                <table><thead><tr><th>{t("adminAction")}</th><th>{t("adminEntity")}</th><th>{t("adminActor")}</th><th>{t("adminCreated")}</th></tr></thead><tbody>{dashboard?.audit_events.map((event) => <tr key={event.audit_event_id}><td>{event.action}</td><td>{event.entity_type}: {event.entity_id}</td><td>{event.admin_email}</td><td>{event.created_at}</td></tr>)}</tbody></table>
              </div>
            </section>
          ) : null}
        </section>
      </div>
    </main>
  );
};

const formatModelSize = (bytes: number): string => {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "";
  }
  const gib = bytes / (1024 * 1024 * 1024);
  return `${gib.toFixed(gib >= 10 ? 0 : 1)} GiB`;
};

export default AIModelAdmin;
