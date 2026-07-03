import React from "react";
import { FaBriefcase, FaCheck, FaDownload, FaEdit, FaKey, FaPlus, FaRoute, FaSearch, FaServer, FaSyncAlt, FaTrash, FaUserCog, FaUserPlus, FaUsers } from "react-icons/fa";
import {
  AIModelAdminDashboard,
  AIModelProfile,
  AIModelRoutePolicy,
  AIModelUserOverrideDetail,
  AdminCaseList,
  AdminCaseSummary,
  AdminCaseUser,
  AdminUserSummary,
  AdminUsersPage,
  OllamaModelInventory,
  disableAIModelUserOverride,
  fetchAdminUsers,
  fetchAdminUserCases,
  fetchAIModelAdminDashboard,
  fetchAIModelUserOverride,
  fetchOllamaModels,
  deleteAIModelProvider,
  searchAdminCaseUsers,
  searchAIModelAssignmentUsers,
  softDeleteAdminCase,
  upsertAIModelUserOverride,
  upsertAIModelProvider,
  upsertAIModelProfile,
  upsertAIModelGroup,
  addAIModelGroupMember,
  upsertAIModelRoutePolicy,
  importOllamaModel,
  removeOllamaModel,
  updateAdminUser
} from "../api/adminModelClient";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";

type AdminSection = "users" | "assignments" | "cases" | "providers" | "profiles" | "credentials" | "groups" | "policies" | "ollama" | "audit";

const emptyProvider = {
  provider_code: "",
  provider_type: "azurefoundry",
  display_name: "",
  base_url: "",
  api_version: "",
  region: "",
  data_zone: "eu",
  health_check_url: "",
  is_external: true,
  is_local: false,
  enabled: true,
  reason: ""
};

const emptyProfile = {
  model_profile_id: null as string | null,
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

const emptyGroup = {
  group_code: "",
  display_name: "",
  priority: 10,
  enabled: true,
  reason: ""
};

const emptyPolicy = {
  policy_id: null as string | null,
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
  const [providerCredentialsMode, setProviderCredentialsMode] = React.useState<"table" | "create" | "edit">("table");
  const [profileForm, setProfileForm] = React.useState(emptyProfile);
  const [groupForm, setGroupForm] = React.useState(emptyGroup);
  const [policyForm, setPolicyForm] = React.useState(emptyPolicy);
  const [selectedGroupId, setSelectedGroupId] = React.useState("");
  const [selectedUserId, setSelectedUserId] = React.useState("");
  const [caseUserQuery, setCaseUserQuery] = React.useState("");
  const [caseUserResults, setCaseUserResults] = React.useState<AdminCaseUser[]>([]);
  const [selectedCaseUser, setSelectedCaseUser] = React.useState<AdminCaseUser | null>(null);
  const [adminCaseList, setAdminCaseList] = React.useState<AdminCaseList | null>(null);
  const [caseDeleteReason, setCaseDeleteReason] = React.useState(t("adminCasesDefaultReason"));
  const [assignmentQuery, setAssignmentQuery] = React.useState("");
  const [assignmentUsers, setAssignmentUsers] = React.useState<AdminUserSummary[]>([]);
  const [assignmentDetail, setAssignmentDetail] = React.useState<AIModelUserOverrideDetail | null>(null);
  const [assignmentModelProfileId, setAssignmentModelProfileId] = React.useState("");
  const [assignmentReason, setAssignmentReason] = React.useState("");
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
  const activeProviders = React.useMemo(
    () => (dashboard?.providers ?? []).filter((provider) => !provider.deleted_at),
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
      const firstActiveProvider = nextDashboard.providers.find((provider) => !provider.deleted_at);
      setProfileForm((current) => ({ ...current, provider_id: current.provider_id || firstActiveProvider?.provider_id || firstProvider?.provider_id || "" }));
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

  const loadAdminCasesForUser = React.useCallback(async (targetUser: AdminCaseUser) => {
    if (!adminUserId) return;
    setError("");
    try {
      const nextCaseList = await fetchAdminUserCases(adminAuth, targetUser.user_id, true);
      setSelectedCaseUser(nextCaseList.user);
      setAdminCaseList(nextCaseList);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("adminCasesLoadFailed"));
    }
  }, [adminAuth, adminUserId, t]);

  const searchCaseUsers = React.useCallback(async () => {
    if (!adminUserId || !caseUserQuery.trim()) return;
    setError("");
    setStatus("");
    try {
      const results = await searchAdminCaseUsers(adminAuth, caseUserQuery, 25);
      setCaseUserResults(results.items);
      const onlyResult = results.items[0];
      if (results.items.length === 1 && onlyResult) {
        await loadAdminCasesForUser(onlyResult);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("adminCasesSearchFailed"));
    }
  }, [adminAuth, adminUserId, caseUserQuery, loadAdminCasesForUser, t]);

  const loadAssignmentForUser = React.useCallback(async (targetUser: AdminUserSummary) => {
    if (!adminUserId) return;
    setError("");
    try {
      const detail = await fetchAIModelUserOverride(adminAuth, targetUser.user_id);
      setAssignmentDetail(detail);
      setAssignmentModelProfileId(detail.override?.model_profile_id ?? "");
      setAssignmentReason("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("adminAssignmentLoadFailed"));
    }
  }, [adminAuth, adminUserId, t]);

  const searchAssignmentUsers = React.useCallback(async () => {
    if (!adminUserId || !assignmentQuery.trim()) return;
    setError("");
    setStatus("");
    try {
      const results = await searchAIModelAssignmentUsers(adminAuth, assignmentQuery, 25);
      setAssignmentUsers(results.items);
      const onlyResult = results.items[0];
      if (results.items.length === 1 && onlyResult) {
        await loadAssignmentForUser(onlyResult);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("adminAssignmentSearchFailed"));
    }
  }, [adminAuth, adminUserId, assignmentQuery, loadAssignmentForUser, t]);

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

  const deleteAdminCase = async (caseItem: AdminCaseSummary) => {
    if (!selectedCaseUser || !caseDeleteReason.trim()) {
      setError(t("adminCasesReasonRequired"));
      return;
    }
    const confirmed = window.confirm(
      t("adminCasesDeleteConfirm", {
        title: caseItem.title,
        id: caseItem.case_id,
        email: selectedCaseUser.email
      })
    );
    if (!confirmed) {
      return;
    }
    setError("");
    setStatus("");
    try {
      await softDeleteAdminCase(adminAuth, caseItem.case_id, selectedCaseUser.user_id, caseDeleteReason.trim());
      setStatus(t("adminCasesDeleteSuccess"));
      await loadAdminCasesForUser(selectedCaseUser);
      await reload();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : t("adminCasesDeleteFailed"));
    }
  };

  const localProfiles = dashboard?.profiles.filter((profile) => profile.model_profile_id.includes("local") || profile.provider_id.includes("local")) ?? [];
  const externalProfiles = dashboard?.profiles.filter((profile) => !localProfiles.includes(profile)) ?? [];
  const enabledProfiles = dashboard?.profiles.filter((profile) => profile.enabled) ?? [];
  const freeDefaultProfile = dashboard?.profiles.find((profile) => profile.is_default_for_free);
  const freeDefaultProvider = freeDefaultProfile ? providerById.get(freeDefaultProfile.provider_id) : undefined;
  const freeDefaultLabel = freeDefaultProfile
    ? `${freeDefaultProfile.deployment_name || freeDefaultProfile.model_code} (${freeDefaultProvider?.display_name ?? freeDefaultProfile.provider_id})`
    : t("adminNoFreeModel");
  const applyProfileToDashboard = React.useCallback((savedProfile: AIModelProfile) => {
    setDashboard((current) => {
      if (!current) return current;
      const profiles = current.profiles.map((profile) => {
        if (profile.model_profile_id === savedProfile.model_profile_id) {
          return savedProfile;
        }
        return savedProfile.is_default_for_free ? { ...profile, is_default_for_free: false } : profile;
      });
      if (!profiles.some((profile) => profile.model_profile_id === savedProfile.model_profile_id)) {
        profiles.push(savedProfile);
      }
      return { ...current, profiles };
    });
  }, []);
  const providerToForm = (provider: AIModelAdminDashboard["providers"][number], overrides: Partial<typeof emptyProvider> = {}) => ({
    provider_code: provider.provider_code,
    provider_type: provider.provider_type,
    display_name: provider.display_name,
    base_url: provider.base_url,
    api_version: provider.api_version,
    region: provider.region,
    data_zone: provider.data_zone,
    health_check_url: provider.health_check_url,
    is_external: provider.is_external,
    is_local: provider.is_local,
    enabled: provider.enabled,
    reason: "",
    ...overrides
  });
  const saveProviderChange = (
    provider: AIModelAdminDashboard["providers"][number],
    overrides: Partial<typeof emptyProvider>,
    successMessage: string
  ) => runAction(() => upsertAIModelProvider(adminAuth, providerToForm(provider, overrides)), successMessage);
  const providerStatusLabel = (provider: AIModelAdminDashboard["providers"][number]) => {
    if (provider.deleted_at) {
      return t("adminDeleted");
    }
    return provider.enabled ? t("adminEnabled") : t("adminDisabled");
  };
  const showProviderCreateForm = () => {
    setProviderForm(emptyProvider);
    setProviderCredentialsMode("create");
    setStatus("");
    setError("");
  };
  const showProviderEditForm = (provider: AIModelAdminDashboard["providers"][number]) => {
    setProviderForm(providerToForm(provider));
    setProviderCredentialsMode("edit");
    setStatus("");
    setError("");
  };
  const cancelProviderCredentialsForm = () => {
    setProviderForm(emptyProvider);
    setProviderCredentialsMode("table");
    setStatus("");
    setError("");
  };
  const saveProviderCredentialsForm = async () => {
    await runAction(() => upsertAIModelProvider(adminAuth, providerForm), t("adminProviderSaved"));
    setProviderForm(emptyProvider);
    setProviderCredentialsMode("table");
  };
  const deleteProviderFromCredentials = async (provider: AIModelAdminDashboard["providers"][number]) => {
    const reason = window.prompt(t("adminProviderDeleteReasonPrompt"), "Soft delete provider from admin UI.");
    if (!reason?.trim()) {
      return;
    }
    await runAction(
      () => deleteAIModelProvider(adminAuth, provider.provider_id, { reason: reason.trim() }),
      t("adminProviderDeleted")
    );
    setProviderCredentialsMode("table");
    setProviderForm(emptyProvider);
  };
  const profileToForm = (profile: AIModelProfile, overrides: Partial<typeof emptyProfile> = {}) => ({
    model_profile_id: profile.model_profile_id,
    provider_id: profile.provider_id,
    model_code: profile.model_code,
    deployment_name: profile.deployment_name,
    input_price_per_1m: profile.input_price_per_1m,
    cached_input_price_per_1m: profile.cached_input_price_per_1m,
    output_price_per_1m: profile.output_price_per_1m,
    billing_currency: profile.billing_currency,
    eu_data_zone_capable: profile.eu_data_zone_capable,
    is_default_for_free: profile.is_default_for_free,
    enabled: profile.enabled,
    reason: "",
    ...overrides
  });
  const saveProfileChange = (
    profile: AIModelProfile,
    overrides: Partial<typeof emptyProfile>,
    successMessage: string
  ) => {
    setError("");
    setStatus("");
    void (async () => {
      try {
        const savedProfile = await upsertAIModelProfile(adminAuth, profileToForm(profile, overrides));
        setStatus(successMessage);
        await reload();
        await loadUsersPage(usersOffset);
        applyProfileToDashboard(savedProfile);
      } catch (actionError) {
        setError(actionError instanceof Error ? actionError.message : t("adminSaveFailed"));
      }
    })();
  };
  const policyToForm = (policy: AIModelRoutePolicy, overrides: Partial<typeof emptyPolicy> = {}) => ({
    policy_id: policy.policy_id,
    task_type: policy.task_type,
    plan_code: policy.plan_code,
    model_group_id: policy.model_group_id,
    preferred_external_model_profile_id: policy.preferred_external_model_profile_id,
    preferred_local_model_profile_id: policy.preferred_local_model_profile_id,
    allow_external: policy.allow_external,
    require_external_ack: policy.require_external_ack,
    require_eu_data_zone: policy.require_eu_data_zone,
    fallback_local_on_error: policy.fallback_local_on_error,
    fallback_local_on_budget: policy.fallback_local_on_budget,
    max_cost_eur: policy.max_cost_eur,
    priority: policy.priority,
    enabled: policy.enabled,
    reason: "",
    ...overrides
  });
  const savePolicyChange = (
    policy: AIModelRoutePolicy,
    overrides: Partial<typeof emptyPolicy>,
    successMessage: string
  ) => runAction(() => upsertAIModelRoutePolicy(adminAuth, policyToForm(policy, overrides)), successMessage);
  const disableOllamaConfiguredProfiles = async (profileIds: string[]) => {
    const profiles = dashboard?.profiles.filter((profile) => profileIds.includes(profile.model_profile_id)) ?? [];
    await Promise.all(
      profiles.map((profile) =>
        upsertAIModelProfile(
          adminAuth,
          profileToForm(profile, {
            enabled: false,
            reason: ollamaRemoveReason || "Disable local Ollama model profile from admin UI."
          })
        )
      )
    );
  };

  const sections: Array<{ key: AdminSection; label: string; icon: React.ReactNode }> = [
    { key: "users", label: t("adminUsersTitle"), icon: <FaUsers aria-hidden="true" /> },
    { key: "assignments", label: t("adminAssignmentTitle"), icon: <FaUserCog aria-hidden="true" /> },
    { key: "cases", label: t("adminCasesTitle"), icon: <FaBriefcase aria-hidden="true" /> },
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

          {activeSection === "assignments" ? (
            <section className="admin-grid">
              <form className="admin-panel" onSubmit={(event) => {
                event.preventDefault();
                void searchAssignmentUsers();
              }}>
                <h2>{t("adminAssignmentTitle")}</h2>
                <p className="admin-muted">{t("adminAssignmentHelp")}</p>
                <label>
                  {t("adminAssignmentEmailSearch")}
                  <input
                    value={assignmentQuery}
                    onChange={(event) => setAssignmentQuery(event.target.value)}
                    placeholder="user@example.com"
                    type="email"
                  />
                </label>
                <button className="primary-button" type="submit" disabled={!assignmentQuery.trim()}>
                  <FaSearch aria-hidden="true" />{t("adminAssignmentSearch")}
                </button>
                <AdminRecordsTable
                  emptyLabel={t("adminAssignmentNoUsers")}
                  headers={[t("adminUser"), t("adminStatus"), t("adminAction")]}
                  rows={assignmentUsers.map((item) => [
                    `${item.full_name} (${item.email})`,
                    item.is_enabled ? t("adminEnabled") : t("adminDisabled"),
                    <button className="button ghost" type="button" onClick={() => void loadAssignmentForUser(item)}>
                      {t("adminAssignmentSelectUser")}
                    </button>
                  ])}
                />
              </form>

              <form className="admin-panel" onSubmit={(event) => {
                event.preventDefault();
                if (!assignmentDetail) return;
                void runAction(
                  async () => {
                    const detail = await upsertAIModelUserOverride(adminAuth, assignmentDetail.user.user_id, {
                      model_profile_id: assignmentModelProfileId,
                      reason: assignmentReason
                    });
                    setAssignmentDetail(detail);
                    setAssignmentModelProfileId(detail.override?.model_profile_id ?? "");
                    setAssignmentReason("");
                  },
                  t("adminAssignmentSaved")
                );
              }}>
                <h2>{assignmentDetail ? assignmentDetail.user.email : t("adminAssignmentSelectedUser")}</h2>
                <p className="admin-muted">{t("adminAssignmentPrivacyNote")}</p>
                <div className="admin-highlight">
                  <strong>{t("adminAssignmentCurrentModel")}</strong>
                  <span>{assignmentDetail?.override?.enabled ? assignmentDetail.override.model_profile_id : t("adminNotConfigured")}</span>
                </div>
                <div className="admin-highlight">
                  <strong>{t("adminAssignmentEffectiveRoute")}</strong>
                  <span>
                    {assignmentDetail
                      ? `${assignmentDetail.effective_route.route_type}: ${assignmentDetail.effective_route.provider_display_name ?? t("adminNotConfigured")} / ${assignmentDetail.effective_route.model_code ?? t("adminNotConfigured")}`
                      : t("adminAssignmentSelectUserFirst")}
                  </span>
                </div>
                <label>
                  {t("adminAssignmentModel")}
                  <select
                    value={assignmentModelProfileId}
                    onChange={(event) => setAssignmentModelProfileId(event.target.value)}
                    disabled={!assignmentDetail}
                  >
                    <option value="">{t("adminSelect")}</option>
                    {enabledProfiles.map((profile) => (
                      <option key={profile.model_profile_id} value={profile.model_profile_id}>
                        {providerById.get(profile.provider_id)?.display_name ?? profile.provider_id} / {profile.model_code}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("adminReason")}
                  <input
                    value={assignmentReason}
                    onChange={(event) => setAssignmentReason(event.target.value)}
                  />
                </label>
                <div className="admin-actions">
                  <button className="primary-button" type="submit" disabled={!assignmentDetail || !assignmentModelProfileId || !assignmentReason.trim()}>
                    <FaPlus aria-hidden="true" />{assignmentDetail?.override?.enabled ? t("adminAssignmentUpdate") : t("adminAssignmentSave")}
                  </button>
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={!assignmentDetail?.override?.enabled || !assignmentReason.trim()}
                    onClick={() => void runAction(
                      async () => {
                        if (!assignmentDetail) return;
                        const detail = await disableAIModelUserOverride(adminAuth, assignmentDetail.user.user_id, assignmentReason);
                        setAssignmentDetail(detail);
                        setAssignmentModelProfileId("");
                        setAssignmentReason("");
                      },
                      t("adminAssignmentDeleted")
                    )}
                  >
                    <FaTrash aria-hidden="true" />{t("adminAssignmentDelete")}
                  </button>
                </div>
              </form>
            </section>
          ) : null}

          {activeSection === "cases" ? (
            <section className="admin-grid">
              <form className="admin-panel" onSubmit={(event) => {
                event.preventDefault();
                void searchCaseUsers();
              }}>
                <h2>{t("adminCasesTitle")}</h2>
                <p className="admin-muted">{t("adminCasesHelp")}</p>
                <label>
                  {t("adminCasesEmailSearch")}
                  <input
                    value={caseUserQuery}
                    onChange={(event) => setCaseUserQuery(event.target.value)}
                    placeholder="mmatonok@gmail.com"
                    type="email"
                  />
                </label>
                <button className="primary-button" type="submit" disabled={!caseUserQuery.trim()}>
                  <FaSearch aria-hidden="true" />{t("adminCasesSearch")}
                </button>
                <AdminRecordsTable
                  emptyLabel={t("adminCasesNoUsers")}
                  headers={[t("adminUser"), t("adminStatus"), t("adminAction")]}
                  rows={caseUserResults.map((item) => [
                    `${item.full_name} (${item.email})`,
                    item.is_enabled ? t("adminEnabled") : t("adminDisabled"),
                    <button className="button ghost" type="button" onClick={() => void loadAdminCasesForUser(item)}>
                      {t("adminCasesViewCases")}
                    </button>
                  ])}
                />
              </form>

              <section className="admin-table-section">
                <h2>{selectedCaseUser ? selectedCaseUser.email : t("adminCasesUserCases")}</h2>
                <p className="admin-muted">{t("adminCasesPrivacyNote")}</p>
                <label className="admin-field">
                  {t("adminReason")}
                  <input
                    value={caseDeleteReason}
                    onChange={(event) => setCaseDeleteReason(event.target.value)}
                  />
                </label>
                <div className="admin-table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>{t("adminCasesCase")}</th>
                        <th>{t("adminStatus")}</th>
                        <th>{t("adminCreated")}</th>
                        <th>{t("adminCasesUpdated")}</th>
                        <th>{t("adminAction")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(adminCaseList?.cases ?? []).map((caseItem) => (
                        <tr key={caseItem.case_id}>
                          <td>{caseItem.title}<br /><small>{caseItem.case_id}</small></td>
                          <td>{caseItem.status}</td>
                          <td>{caseItem.created_at}</td>
                          <td>{caseItem.updated_at}</td>
                          <td>
                            <button
                              className="button ghost"
                              type="button"
                              disabled={caseItem.status === "deleted" || !caseDeleteReason.trim()}
                              onClick={() => void deleteAdminCase(caseItem)}
                            >
                              <FaTrash aria-hidden="true" />{t("adminCasesSoftDelete")}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {selectedCaseUser && !adminCaseList?.cases.length ? <p className="admin-muted">{t("adminCasesNoCases")}</p> : null}
                  {!selectedCaseUser ? <p className="admin-muted">{t("adminCasesSelectUser")}</p> : null}
                </div>
              </section>
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
                headers={[t("adminProviderCode"), t("adminProviderType"), t("adminBaseUrl"), t("adminStatus"), t("adminAction")]}
                rows={(dashboard?.providers ?? []).map((provider) => [
                  provider.display_name,
                  provider.provider_type,
                  provider.base_url || provider.health_check_url || t("adminNotConfigured"),
                  provider.enabled ? t("adminEnabled") : t("adminDisabled"),
                  <div className="admin-inline-actions">
                    <button className="button ghost" type="button" onClick={() => setProviderForm(providerToForm(provider))}>
                      <FaEdit aria-hidden="true" />{t("adminEdit")}
                    </button>
                    <button
                      className="button ghost"
                      type="button"
                      onClick={() => void saveProviderChange(
                        provider,
                        {
                          enabled: !provider.enabled,
                          reason: provider.enabled ? "Disable provider from admin UI." : "Enable provider from admin UI."
                        },
                        provider.enabled ? t("adminProviderDisabled") : t("adminProviderEnabled")
                      )}
                    >
                      <FaCheck aria-hidden="true" />{provider.enabled ? t("adminDisableProvider") : t("adminEnableProvider")}
                    </button>
                  </div>
                ])}
              />
              <label>{t("adminProviderCode")}<input value={providerForm.provider_code} onChange={(event) => setProviderForm({ ...providerForm, provider_code: event.target.value })} /></label>
              <label>{t("adminProviderType")}<select value={providerForm.provider_type} onChange={(event) => setProviderForm({ ...providerForm, provider_type: event.target.value })}><option value="local">local</option><option value="azurefoundry">azurefoundry</option><option value="openai">openai</option><option value="openai_compatible">openai_compatible</option></select></label>
              <label>{t("adminDisplayName")}<input value={providerForm.display_name} onChange={(event) => setProviderForm({ ...providerForm, display_name: event.target.value })} /></label>
              <label>{t("adminBaseUrl")}<input value={providerForm.base_url} onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })} /></label>
              <label>{t("adminRegion")}<input value={providerForm.region} onChange={(event) => setProviderForm({ ...providerForm, region: event.target.value })} /></label>
              <label>{t("adminDataZone")}<input value={providerForm.data_zone} onChange={(event) => setProviderForm({ ...providerForm, data_zone: event.target.value })} /></label>
              <label>{t("adminHealthUrl")}<input value={providerForm.health_check_url} onChange={(event) => setProviderForm({ ...providerForm, health_check_url: event.target.value })} /></label>
              <div className="admin-toggle-row">
                <label><input type="checkbox" checked={providerForm.is_external} onChange={(event) => setProviderForm({ ...providerForm, is_external: event.target.checked })} />{t("adminExternal")}</label>
                <label><input type="checkbox" checked={providerForm.is_local} onChange={(event) => setProviderForm({ ...providerForm, is_local: event.target.checked })} />{t("adminLocal")}</label>
                <label><input type="checkbox" checked={providerForm.enabled} onChange={(event) => setProviderForm({ ...providerForm, enabled: event.target.checked })} />{t("adminEnabled")}</label>
              </div>
              <label>{t("adminReason")}<input value={providerForm.reason} onChange={(event) => setProviderForm({ ...providerForm, reason: event.target.value })} /></label>
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
                headers={[t("adminModelCode"), t("adminProvider"), t("adminDeployment"), t("adminPrices"), t("adminStatus"), t("adminAction")]}
                rows={(dashboard?.profiles ?? []).map((profile) => [
                  profile.model_profile_id,
                  providerById.get(profile.provider_id)?.display_name ?? profile.provider_id,
                  profile.deployment_name || profile.model_code,
                  `${profile.input_price_per_1m}/${profile.cached_input_price_per_1m}/${profile.output_price_per_1m} ${profile.billing_currency}`,
                  `${profile.enabled ? t("adminEnabled") : t("adminDisabled")}${profile.is_default_for_free ? `, ${t("adminDefaultFreeModel")}` : ""}`,
                  <div className="admin-inline-actions">
                    <button className="button ghost" type="button" onClick={() => setProfileForm(profileToForm(profile))}>
                      <FaEdit aria-hidden="true" />{t("adminEdit")}
                    </button>
                    <button
                      className="button ghost"
                      type="button"
                      onClick={() => void saveProfileChange(
                        profile,
                        {
                          enabled: !profile.enabled,
                          reason: profile.enabled ? "Disable model profile from admin UI." : "Enable model profile from admin UI."
                        },
                        profile.enabled ? t("adminProfileDisabled") : t("adminProfileEnabled")
                      )}
                    >
                      <FaCheck aria-hidden="true" />{profile.enabled ? t("adminDisableModel") : t("adminEnableModel")}
                    </button>
                    <button
                      className="button ghost"
                      type="button"
                      onClick={() => void saveProfileChange(
                        profile,
                        {
                          enabled: true,
                          is_default_for_free: true,
                          reason: "Set as the default local model for free accounts."
                        },
                        t("adminDefaultLocalModelSet")
                      )}
                      hidden={profile.is_default_for_free || !(providerById.get(profile.provider_id)?.is_local ?? false)}
                    >
                      <FaCheck aria-hidden="true" />{t("adminSetFreeDefault")}
                    </button>
                  </div>
                ])}
              />
              <p className="admin-muted">{t("adminCurrentFreeModel")}: <strong>{freeDefaultLabel}</strong></p>
              <label>{t("adminProvider")}<select value={profileForm.provider_id} onChange={(event) => setProfileForm({ ...profileForm, provider_id: event.target.value })}><option value="">{t("adminSelect")}</option>{activeProviders.map((provider) => <option key={provider.provider_id} value={provider.provider_id}>{provider.display_name}</option>)}</select></label>
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
            <section className="admin-panel" aria-label={t("adminCredentialsTitle")}>
              <h2>{t("adminCredentialsTitle")}</h2>
              <p className="admin-muted">{t("adminProviderCredentialsHelp")}</p>
              {providerCredentialsMode === "table" ? (
                <button className="primary-button" type="button" onClick={showProviderCreateForm}>
                  <FaPlus aria-hidden="true" />{t("adminAddProvider")}
                </button>
              ) : null}
              <AdminRecordsTable
                emptyLabel={t("adminEmptyProviders")}
                headers={[t("adminProviderCode"), t("adminProviderType"), t("adminDisplayName"), t("adminBaseUrl"), t("adminStatus"), t("adminAction")]}
                rows={(dashboard?.providers ?? []).map((provider) => [
                  provider.provider_code,
                  provider.provider_type,
                  provider.display_name,
                  provider.base_url || provider.health_check_url || t("adminNotConfigured"),
                  providerStatusLabel(provider),
                  <div className="admin-inline-actions">
                    <button
                      className="button ghost"
                      type="button"
                      disabled={Boolean(provider.deleted_at)}
                      onClick={() => showProviderEditForm(provider)}
                    >
                      <FaEdit aria-hidden="true" />{t("adminEdit")}
                    </button>
                    <button
                      className="button ghost"
                      type="button"
                      disabled={Boolean(provider.deleted_at)}
                      onClick={() => void deleteProviderFromCredentials(provider)}
                    >
                      <FaTrash aria-hidden="true" />{t("adminDeleteProvider")}
                    </button>
                  </div>
                ])}
              />
              {providerCredentialsMode !== "table" ? (
                <form className="admin-form-stack" onSubmit={(event) => {
                  event.preventDefault();
                  void saveProviderCredentialsForm();
                }}>
                  <h3>{providerCredentialsMode === "create" ? t("adminProviderCreateTitle") : t("adminProviderEditTitle")}</h3>
                  <label>{t("adminProviderCode")}<input value={providerForm.provider_code} onChange={(event) => setProviderForm({ ...providerForm, provider_code: event.target.value })} disabled={providerCredentialsMode === "edit"} /></label>
                  <label>{t("adminProviderType")}<select value={providerForm.provider_type} onChange={(event) => setProviderForm({ ...providerForm, provider_type: event.target.value })}><option value="local">local</option><option value="ollama">ollama</option><option value="azurefoundry">azurefoundry</option><option value="openai">openai</option><option value="openai_compatible">openai_compatible</option></select></label>
                  <label>{t("adminDisplayName")}<input value={providerForm.display_name} onChange={(event) => setProviderForm({ ...providerForm, display_name: event.target.value })} /></label>
                  <label>{t("adminBaseUrl")}<input value={providerForm.base_url} onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })} /></label>
                  <label>{t("adminApiVersion")}<input value={providerForm.api_version} onChange={(event) => setProviderForm({ ...providerForm, api_version: event.target.value })} /></label>
                  <label>{t("adminRegion")}<input value={providerForm.region} onChange={(event) => setProviderForm({ ...providerForm, region: event.target.value })} /></label>
                  <label>{t("adminDataZone")}<input value={providerForm.data_zone} onChange={(event) => setProviderForm({ ...providerForm, data_zone: event.target.value })} /></label>
                  <label>{t("adminHealthUrl")}<input value={providerForm.health_check_url} onChange={(event) => setProviderForm({ ...providerForm, health_check_url: event.target.value })} /></label>
                  <div className="admin-toggle-row">
                    <label><input type="checkbox" checked={providerForm.is_external} onChange={(event) => setProviderForm({ ...providerForm, is_external: event.target.checked })} />{t("adminExternal")}</label>
                    <label><input type="checkbox" checked={providerForm.is_local} onChange={(event) => setProviderForm({ ...providerForm, is_local: event.target.checked })} />{t("adminLocal")}</label>
                    <label><input type="checkbox" checked={providerForm.enabled} onChange={(event) => setProviderForm({ ...providerForm, enabled: event.target.checked })} />{t("adminEnabled")}</label>
                  </div>
                  <label>{t("adminReason")}<input value={providerForm.reason} onChange={(event) => setProviderForm({ ...providerForm, reason: event.target.value })} /></label>
                  <div className="admin-inline-actions">
                    <button className="primary-button" type="submit"><FaCheck aria-hidden="true" />{t("adminSaveProvider")}</button>
                    <button className="button ghost" type="button" onClick={cancelProviderCredentialsForm}>{t("adminCancel")}</button>
                  </div>
                </form>
              ) : null}
            </section>
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
                headers={[t("adminPolicyId"), t("adminTaskType"), t("adminPlanCode"), t("adminGroup"), t("adminExternalModel"), t("adminLocalModel"), t("adminPriority"), t("adminStatus"), t("adminAction")]}
                rows={(dashboard?.policies ?? []).map((policy) => [
                  policy.policy_id,
                  policy.task_type,
                  policy.plan_code || t("adminDefaultPolicy"),
                  dashboard?.groups.find((group) => group.model_group_id === policy.model_group_id)?.display_name ?? t("adminDefaultPolicy"),
                  policy.preferred_external_model_profile_id ?? t("adminNotConfigured"),
                  policy.preferred_local_model_profile_id ?? t("adminNotConfigured"),
                  String(policy.priority),
                  policy.enabled ? t("adminEnabled") : t("adminDisabled"),
                  <div className="admin-inline-actions">
                    <button className="button ghost" type="button" onClick={() => setPolicyForm(policyToForm(policy))}>
                      <FaEdit aria-hidden="true" />{t("adminEdit")}
                    </button>
                    <button
                      className="button ghost"
                      type="button"
                      onClick={() => void savePolicyChange(
                        policy,
                        {
                          enabled: !policy.enabled,
                          reason: policy.enabled ? "Disable route policy from admin UI." : "Enable route policy from admin UI."
                        },
                        policy.enabled ? t("adminPolicyDisabled") : t("adminPolicyEnabled")
                      )}
                    >
                      <FaCheck aria-hidden="true" />{policy.enabled ? t("adminDisablePolicy") : t("adminEnablePolicy")}
                    </button>
                  </div>
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
                <label>{t("adminOllamaActionReason")}<input value={ollamaRemoveReason} onChange={(event) => setOllamaRemoveReason(event.target.value)} /></label>
                <div className="admin-table-scroll">
                  <table>
                    <thead><tr><th>{t("adminModelCode")}</th><th>{t("adminStatus")}</th><th>{t("adminProfilesTitle")}</th><th>{t("adminAction")}</th></tr></thead>
                    <tbody>{ollamaInventory?.models.map((item) => (
                      <tr key={item.name}>
                        <td>{item.name}<br /><small>{formatModelSize(item.size)}</small></td>
                        <td>
                          {!item.installed ? t("adminOllamaNotInstalled") : item.is_default ? t("adminOllamaDefault") : item.is_running ? t("adminOllamaRunning") : t("adminOllamaUnused")}
                          {item.removal_blockers.length ? <ul className="admin-compact-list">{item.removal_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul> : null}
                        </td>
                        <td>{item.configured_profile_ids.length ? item.configured_profile_ids.join(", ") : t("adminNotConfigured")}</td>
                        <td>
                          <div className="admin-inline-actions">
                            <button
                              className="button ghost"
                              type="button"
                              disabled={!item.configured_profile_ids.length || !ollamaRemoveReason.trim()}
                              onClick={() => void runAction(async () => {
                                await disableOllamaConfiguredProfiles(item.configured_profile_ids);
                                setOllamaRemoveReason("");
                                await reloadOllama();
                              }, t("adminOllamaProfilesDisabled"))}
                            >
                              <FaCheck aria-hidden="true" />{t("adminOllamaDisable")}
                            </button>
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
                          </div>
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
