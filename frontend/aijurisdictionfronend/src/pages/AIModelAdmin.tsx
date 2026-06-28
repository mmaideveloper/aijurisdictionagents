import React from "react";
import { FaDownload, FaKey, FaPlus, FaRoute, FaServer, FaSyncAlt, FaTrash, FaUserPlus, FaUsers } from "react-icons/fa";
import {
  AIModelAdminDashboard,
  AdminUsersPage,
  OllamaModelInventory,
  fetchAdminUsers,
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
  const [usersPage, setUsersPage] = React.useState<AdminUsersPage | null>(null);
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
  const adminAuth = React.useMemo(
    () => ({
      userId: adminUserId,
      deviceId: user?.deviceId,
      deviceAuthToken: user?.deviceAuthToken
    }),
    [adminUserId, user?.deviceAuthToken, user?.deviceId]
  );
  const visibleUsers = usersPage?.items ?? dashboard?.users ?? [];
  const usersTotal = usersPage?.total ?? dashboard?.users_page.total ?? visibleUsers.length;
  const usersLimit = usersPage?.limit ?? dashboard?.users_page.limit ?? 25;
  const usersOffset = usersPage?.offset ?? dashboard?.users_page.offset ?? 0;
  const providerById = React.useMemo(
    () => new Map((dashboard?.providers ?? []).map((provider) => [provider.provider_id, provider])),
    [dashboard?.providers]
  );

  const reload = React.useCallback(async () => {
    if (!adminUserId) return;
    setError("");
    try {
      const nextDashboard = await fetchAIModelAdminDashboard(adminAuth);
      setDashboard(nextDashboard);
      setUsersPage({
        items: nextDashboard.users,
        total: nextDashboard.users_page.total,
        limit: nextDashboard.users_page.limit,
        offset: nextDashboard.users_page.offset
      });
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
  }, [adminAuth, adminUserId, t]);

  const loadUsersPage = React.useCallback(async (offset: number) => {
    if (!adminUserId) return;
    setError("");
    try {
      setUsersPage(await fetchAdminUsers(adminAuth, usersLimit, Math.max(offset, 0)));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("adminLoadFailed"));
    }
  }, [adminAuth, adminUserId, t, usersLimit]);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  const reloadOllama = React.useCallback(async () => {
    if (!adminUserId) return;
    try {
      setOllamaInventory(await fetchOllamaModels(adminAuth));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("adminOllamaLoadFailed"));
    }
  }, [adminAuth, adminUserId, t]);

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
      await loadUsersPage(usersOffset);
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
                    {visibleUsers.map((item) => (
                      <tr key={item.user_id}>
                        <td>{item.full_name} ({item.email})</td>
                        <td>{item.role}</td>
                        <td>{item.is_enabled ? t("adminEnabled") : t("adminDisabled")}</td>
                        <td>
                          <button
                            className="button ghost"
                            type="button"
                            onClick={() => void runAction(
                              () => updateAdminUser(adminAuth, item.user_id, {
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
                              () => updateAdminUser(adminAuth, item.user_id, {
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
                {!visibleUsers.length ? <p className="admin-muted">{t("adminEmptyUsers")}</p> : null}
              </div>
              <div className="admin-pagination">
                <span>{t("adminPaginationSummary", {
                  start: usersTotal ? usersOffset + 1 : 0,
                  end: Math.min(usersOffset + usersLimit, usersTotal),
                  total: usersTotal
                })}</span>
                <button className="secondary-button" type="button" disabled={usersOffset <= 0} onClick={() => void loadUsersPage(usersOffset - usersLimit)}>{t("adminPrevious")}</button>
                <button className="secondary-button" type="button" disabled={usersOffset + usersLimit >= usersTotal} onClick={() => void loadUsersPage(usersOffset + usersLimit)}>{t("adminNext")}</button>
              </div>
            </section>
          ) : null}

          {activeSection === "providers" ? (
            <form className="admin-panel" onSubmit={(event) => {
              event.preventDefault();
              void runAction(() => upsertAIModelProvider(adminAuth, providerForm), t("adminSaved"));
            }}>
              <h2>{t("adminProvidersTitle")}</h2>
              <AdminRecordsTable
                emptyLabel={t("adminEmptyProviders")}
                headers={[t("adminProviderCode"), t("adminProviderType"), t("adminBaseUrl"), t("adminStatus")]}
                rows={(dashboard?.providers ?? []).map((provider) => [
                  provider.display_name,
                  provider.provider_type,
                  provider.base_url || provider.health_check_url || t("adminNotConfigured"),
                  provider.enabled ? t("adminEnabled") : t("adminDisabled")
                ])}
              />
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
              void runAction(() => upsertAIModelProfile(adminAuth, profileForm), t("adminSaved"));
            }}>
              <h2>{t("adminProfilesTitle")}</h2>
              <AdminRecordsTable
                emptyLabel={t("adminEmptyProfiles")}
                headers={[t("adminModelCode"), t("adminProvider"), t("adminDeployment"), t("adminPrices"), t("adminStatus")]}
                rows={(dashboard?.profiles ?? []).map((profile) => [
                  profile.model_profile_id,
                  providerById.get(profile.provider_id)?.display_name ?? profile.provider_id,
                  profile.deployment_name || profile.model_code,
                  `${profile.input_price_per_1m}/${profile.cached_input_price_per_1m}/${profile.output_price_per_1m} ${profile.billing_currency}`,
                  profile.enabled ? t("adminEnabled") : t("adminDisabled")
                ])}
              />
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
              void runAction(() => upsertAIModelCredential(adminAuth, credentialForm), t("adminSaved"));
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
                void runAction(() => upsertAIModelGroup(adminAuth, groupForm), t("adminSaved"));
              }}>
                <h2>{t("adminGroupsTitle")}</h2>
                <AdminRecordsTable
                  emptyLabel={t("adminEmptyGroups")}
                  headers={[t("adminGroupCode"), t("adminDisplayName"), t("adminPriority"), t("adminStatus")]}
                  rows={(dashboard?.groups ?? []).map((group) => [
                    group.group_code,
                    group.display_name,
                    String(group.priority),
                    group.enabled ? t("adminEnabled") : t("adminDisabled")
                  ])}
                />
                <label>{t("adminGroupCode")}<input value={groupForm.group_code} onChange={(event) => setGroupForm({ ...groupForm, group_code: event.target.value })} /></label>
                <label>{t("adminDisplayName")}<input value={groupForm.display_name} onChange={(event) => setGroupForm({ ...groupForm, display_name: event.target.value })} /></label>
                <label>{t("adminPriority")}<input type="number" value={groupForm.priority} onChange={(event) => setGroupForm({ ...groupForm, priority: Number(event.target.value) })} /></label>
                <button className="primary-button" type="submit"><FaPlus aria-hidden="true" />{t("adminSaveGroup")}</button>
              </form>
              <form className="admin-panel" onSubmit={(event) => {
                event.preventDefault();
                void runAction(() => addAIModelGroupMember(adminAuth, selectedGroupId, selectedUserId), t("adminSaved"));
              }}>
                <h2>{t("adminMembersTitle")}</h2>
                <AdminRecordsTable
                  emptyLabel={t("adminEmptyMembers")}
                  headers={[t("adminGroup"), t("adminUser"), t("adminCreated")]}
                  rows={(dashboard?.memberships ?? []).map((membership) => [
                    dashboard?.groups.find((group) => group.model_group_id === membership.model_group_id)?.display_name ?? membership.model_group_id,
                    `${membership.full_name} (${membership.email})`,
                    membership.created_at
                  ])}
                />
                <label>{t("adminGroup")}<select value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>{dashboard?.groups.map((group) => <option key={group.model_group_id} value={group.model_group_id}>{group.display_name}</option>)}</select></label>
                <label>{t("adminUser")}<select value={selectedUserId} onChange={(event) => setSelectedUserId(event.target.value)}>{dashboard?.users.map((item) => <option key={item.user_id} value={item.user_id}>{item.full_name} ({item.email})</option>)}</select></label>
                <button className="primary-button" type="submit"><FaUserPlus aria-hidden="true" />{t("adminAssignUser")}</button>
              </form>
            </section>
          ) : null}

          {activeSection === "policies" ? (
            <form className="admin-panel" onSubmit={(event) => {
              event.preventDefault();
              void runAction(() => upsertAIModelRoutePolicy(adminAuth, policyForm), t("adminSaved"));
            }}>
              <h2>{t("adminPoliciesTitle")}</h2>
              <p className="admin-muted">{t("adminPolicyHelp")}</p>
              <AdminRecordsTable
                emptyLabel={t("adminEmptyPolicies")}
                headers={[t("adminPolicyId"), t("adminTaskType"), t("adminPlanCode"), t("adminGroup"), t("adminExternalModel"), t("adminLocalModel"), t("adminPriority")]}
                rows={(dashboard?.policies ?? []).map((policy) => [
                  policy.policy_id,
                  policy.task_type,
                  policy.plan_code || t("adminDefaultPolicy"),
                  dashboard?.groups.find((group) => group.model_group_id === policy.model_group_id)?.display_name ?? t("adminDefaultPolicy"),
                  policy.preferred_external_model_profile_id ?? t("adminNotConfigured"),
                  policy.preferred_local_model_profile_id ?? t("adminNotConfigured"),
                  String(policy.priority)
                ])}
              />
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
                  await importOllamaModel(adminAuth, ollamaModel, ollamaReason);
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
                              await removeOllamaModel(adminAuth, item.name, ollamaRemoveReason);
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

const AdminRecordsTable: React.FC<{
  headers: string[];
  rows: Array<Array<React.ReactNode>>;
  emptyLabel: string;
}> = ({ headers, rows, emptyLabel }) => (
  <div className="admin-table-scroll admin-records-table">
    <table>
      <thead>
        <tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, rowIndex) => (
          <tr key={row.map((cell) => String(cell)).join("|") || rowIndex}>
            {row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
    {!rows.length ? <p className="admin-muted">{emptyLabel}</p> : null}
  </div>
);

const formatModelSize = (bytes: number): string => {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "";
  }
  const gib = bytes / (1024 * 1024 * 1024);
  return `${gib.toFixed(gib >= 10 ? 0 : 1)} GiB`;
};

export default AIModelAdmin;
