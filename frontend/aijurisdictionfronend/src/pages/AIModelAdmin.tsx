import React from "react";
import { createSearchParams } from "react-router-dom";
import { FaBriefcase, FaBug, FaCheck, FaDownload, FaEdit, FaKey, FaPlus, FaRoute, FaSearch, FaServer, FaSyncAlt, FaTrash, FaUserCog, FaUserPlus, FaUsers } from "react-icons/fa";
import {
  AIModelAdminDashboard,
  AIModelCredential,
  AIModelProfile,
  AIModelRoutePolicy,
  AIModelUserOverrideDetail,
  AdminCaseList,
  AdminCaseSummary,
  AdminCaseUser,
  AdminUserSummary,
  AdminUsersPage,
  AdminDebugTrace,
  CaseCatalogCaseType,
  CaseWorkflowAssignment,
  DocumentTemplateCatalogItem,
  FlowPackCatalogItem,
  RegisteredCaseWorkflowGraph,
  OllamaModelInventory,
  disableAIModelUserOverride,
  fetchAdminCaseCatalogCaseTypes,
  fetchAdminCaseCatalogDocumentTemplates,
  fetchCaseWorkflowAssignments,
  fetchFlowPackCatalog,
  fetchRegisteredCaseWorkflowGraphs,
  validateCaseWorkflowAssignment,
  assignCaseWorkflow,
  createDraftFlowPackVersion,
  fetchAdminUsers,
  fetchAdminCaseExportBlob,
  fetchAdminUserCases,
  fetchAIModelAdminDashboard,
  fetchAIModelUserOverride,
  fetchOllamaModels,
  deleteAIModelProvider,
  deleteAIModelProfile,
  deleteAIModelGroup,
  deleteAIModelRoutePolicy,
  searchAdminCaseUsers,
  searchAIModelAssignmentUsers,
  softDeleteAdminCase,
  upsertAIModelUserOverride,
  upsertAIModelProvider,
  upsertAIModelProfile,
  upsertAIModelGroup,
  addAIModelGroupMember,
  patchAIModelCredential,
  upsertAIModelRoutePolicy,
  upsertAIModelCredential,
  importOllamaModel,
  setOllamaModelDefault,
  removeOllamaModel,
  updateAdminUser,
  fetchAdminDebugTrace,
  fetchAdminDebugExport
} from "../api/adminModelClient";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";

type AdminSection = "users" | "assignments" | "cases" | "caseCatalog" | "providers" | "profiles" | "credentials" | "groups" | "policies" | "ollamaImport" | "ollama" | "debug" | "audit";
type AdminFormMode = "table" | "create" | "edit";
type AdminDashboardLoadState = "idle" | "loading" | "success" | "error";
type AdminCaseCatalogLoadState = "idle" | "loading" | "success" | "error";
type AdminCaseCatalogSection = "caseTypes" | "caseTemplates" | "casePrompts";

const emptyProvider = {
  provider_code: "",
  provider_type: "azurefoundry",
  display_name: "",
  base_url: "",
  api_version: "",
  region: "",
  data_zone: "eu",
  health_check_url: "",
  model_parameters: "{}",
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
  model_parameters: "{}",
  input_price_per_1m: 0,
  cached_input_price_per_1m: 0,
  output_price_per_1m: 0,
  billing_currency: "EUR",
  eu_data_zone_capable: true,
  is_default_for_free: false,
  enabled: true,
  reason: ""
};

const parseModelParameters = (value: string): Record<string, boolean | number | string | null> => {
  const parsed: unknown = JSON.parse(value || "{}");
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Model parameters must be a JSON object.");
  }
  return parsed as Record<string, boolean | number | string | null>;
};

const emptyCredential = {
  credential_id: null as string | null,
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

const emptyUserForm = {
  user_id: "",
  email: "",
  full_name: "",
  role: "user",
  is_enabled: true,
  reason: ""
};

const AIModelAdmin: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [activeSection, setActiveSection] = React.useState<AdminSection>("users");
  const [dashboard, setDashboard] = React.useState<AIModelAdminDashboard | null>(null);
  const [usersPage, setUsersPage] = React.useState<AdminUsersPage | null>(null);
  const [ollamaInventory, setOllamaInventory] = React.useState<OllamaModelInventory | null>(null);
  const [userForm, setUserForm] = React.useState(emptyUserForm);
  const [userMode, setUserMode] = React.useState<AdminFormMode>("table");
  const [providerForm, setProviderForm] = React.useState(emptyProvider);
  const [providerMode, setProviderMode] = React.useState<AdminFormMode>("table");
  const [providerCredentialsMode, setProviderCredentialsMode] = React.useState<AdminFormMode>("table");
  const [credentialForm, setCredentialForm] = React.useState(emptyCredential);
  const [profileForm, setProfileForm] = React.useState(emptyProfile);
  const [profileMode, setProfileMode] = React.useState<AdminFormMode>("table");
  const [groupForm, setGroupForm] = React.useState(emptyGroup);
  const [groupMode, setGroupMode] = React.useState<AdminFormMode>("table");
  const [policyForm, setPolicyForm] = React.useState(emptyPolicy);
  const [policyMode, setPolicyMode] = React.useState<AdminFormMode>("table");
  const [selectedGroupId, setSelectedGroupId] = React.useState("");
  const [selectedUserId, setSelectedUserId] = React.useState("");
  const [caseUserQuery, setCaseUserQuery] = React.useState("");
  const [caseUserResults, setCaseUserResults] = React.useState<AdminCaseUser[]>([]);
  const [selectedCaseUser, setSelectedCaseUser] = React.useState<AdminCaseUser | null>(null);
  const [adminCaseList, setAdminCaseList] = React.useState<AdminCaseList | null>(null);
  const [catalogCaseTypes, setCatalogCaseTypes] = React.useState<CaseCatalogCaseType[]>([]);
  const [catalogTemplates, setCatalogTemplates] = React.useState<DocumentTemplateCatalogItem[]>([]);
  const [workflowAssignments, setWorkflowAssignments] = React.useState<CaseWorkflowAssignment[]>([]);
  const [workflowGraphs, setWorkflowGraphs] = React.useState<RegisteredCaseWorkflowGraph[]>([]);
  const [flowPacks, setFlowPacks] = React.useState<FlowPackCatalogItem[]>([]);
  const [workflowCaseTypeKey, setWorkflowCaseTypeKey] = React.useState("");
  const [workflowGraphRef, setWorkflowGraphRef] = React.useState("legal_document_workflow@1");
  const [workflowFlowRef, setWorkflowFlowRef] = React.useState("");
  const [workflowReplacementConfirmed, setWorkflowReplacementConfirmed] = React.useState(false);
  const [workflowValidation, setWorkflowValidation] = React.useState("");
  const [catalogLoadState, setCatalogLoadState] = React.useState<AdminCaseCatalogLoadState>("idle");
  const [activeCatalogSection, setActiveCatalogSection] = React.useState<AdminCaseCatalogSection>("caseTypes");
  const [caseDeleteReason, setCaseDeleteReason] = React.useState(t("adminCasesDefaultReason"));
  const [exportingAdminCaseId, setExportingAdminCaseId] = React.useState<string | null>(null);
  const [assignmentQuery, setAssignmentQuery] = React.useState("");
  const [assignmentUsers, setAssignmentUsers] = React.useState<AdminUserSummary[]>([]);
  const [assignmentDetail, setAssignmentDetail] = React.useState<AIModelUserOverrideDetail | null>(null);
  const [assignmentModelProfileId, setAssignmentModelProfileId] = React.useState("");
  const [assignmentReason, setAssignmentReason] = React.useState("");
  const [ollamaModel, setOllamaModel] = React.useState("");
  const [ollamaReason, setOllamaReason] = React.useState("");
  const [ollamaRemoveReason, setOllamaRemoveReason] = React.useState("");
  const [dashboardLoadState, setDashboardLoadState] = React.useState<AdminDashboardLoadState>("idle");
  const [status, setStatus] = React.useState("");
  const [error, setError] = React.useState("");
  const [debugCorrelationId, setDebugCorrelationId] = React.useState("");
  const [debugTrace, setDebugTrace] = React.useState<AdminDebugTrace | null>(null);
  const [debugView, setDebugView] = React.useState<"timeline" | "flow">("timeline");
  const [formSubmitting, setFormSubmitting] = React.useState(false);
  const formSubmittingRef = React.useRef(false);
  const editFormRef = React.useRef<HTMLFormElement | null>(null);
  const adminContentRef = React.useRef<HTMLElement | null>(null);
  const formWasOpenRef = React.useRef(false);
  const dashboardRequestInFlight = React.useRef(false);

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
  const activeProfiles = React.useMemo(
    () => (dashboard?.profiles ?? []).filter((profile) => !profile.deleted_at),
    [dashboard?.profiles]
  );
  const activeGroups = React.useMemo(
    () => (dashboard?.groups ?? []).filter((group) => !group.deleted_at),
    [dashboard?.groups]
  );
  const activeGroupIds = React.useMemo(
    () => new Set(activeGroups.map((group) => group.model_group_id)),
    [activeGroups]
  );
  const activePolicies = React.useMemo(
    () => (dashboard?.policies ?? []).filter((policy) => !policy.deleted_at),
    [dashboard?.policies]
  );
  const catalogPrompts = React.useMemo(
    () => catalogCaseTypes
      .filter((item) => item.prompt)
      .map((item) => ({
        case_type_id: item.case_type_id,
        case_type_key: item.case_type_key,
        case_type_name: item.name,
        jurisdiction: item.jurisdiction,
        linked_templates: item.templates,
        prompt: item.prompt
      })),
    [catalogCaseTypes]
  );

  const reload = React.useCallback(async () => {
    if (!adminUserId || dashboardRequestInFlight.current) return;
    dashboardRequestInFlight.current = true;
    setDashboardLoadState("loading");
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
      setDashboardLoadState("success");
    } catch (loadError) {
      setDashboardLoadState("error");
      setError(loadError instanceof Error ? loadError.message : t("adminLoadFailed"));
    } finally {
      dashboardRequestInFlight.current = false;
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

  const loadCaseCatalog = React.useCallback(async () => {
    if (!adminUserId || catalogLoadState === "loading") return;
    setCatalogLoadState("loading");
    setError("");
    try {
      const [caseTypesResponse, templatesResponse, assignmentsResponse, graphsResponse, flowsResponse] = await Promise.all([
        fetchAdminCaseCatalogCaseTypes(adminAuth),
        fetchAdminCaseCatalogDocumentTemplates(adminAuth),
        fetchCaseWorkflowAssignments(adminAuth),
        fetchRegisteredCaseWorkflowGraphs(adminAuth),
        fetchFlowPackCatalog(adminAuth)
      ]);
      setCatalogCaseTypes(caseTypesResponse.items);
      setCatalogTemplates(templatesResponse.items);
      setWorkflowAssignments(assignmentsResponse.items);
      setWorkflowGraphs(graphsResponse);
      setFlowPacks(flowsResponse.items);
      setCatalogLoadState("success");
    } catch (loadError) {
      setCatalogLoadState("error");
      setError(loadError instanceof Error ? loadError.message : t("adminCaseCatalogLoadFailed"));
    }
  }, [adminAuth, adminUserId, catalogLoadState, t]);

  const workflowAssignmentInput = React.useCallback(() => {
    const [graphKey, graphVersion] = workflowGraphRef.split("@");
    const [flowKey, flowVersion] = workflowFlowRef.split("@");
    return {
      case_type_key: workflowCaseTypeKey,
      jurisdiction: "SK",
      graph_key: graphKey ?? "",
      graph_version: Number(graphVersion),
      flow_key: flowKey ?? "",
      flow_version: Number(flowVersion),
      confirmation: workflowReplacementConfirmed
    };
  }, [workflowCaseTypeKey, workflowFlowRef, workflowGraphRef, workflowReplacementConfirmed]);

  const validateWorkflowAssignment = async () => {
    setError("");
    try {
      const result = await validateCaseWorkflowAssignment(adminAuth, workflowAssignmentInput());
      setWorkflowValidation(`${result.status}: ${result.message}`);
    } catch (validationError) {
      setWorkflowValidation("");
      setError(validationError instanceof Error ? validationError.message : t("adminCaseCatalogLoadFailed"));
    }
  };

  const saveWorkflowAssignment = async () => {
    setError("");
    try {
      await assignCaseWorkflow(adminAuth, workflowAssignmentInput());
      setWorkflowValidation("");
      setWorkflowReplacementConfirmed(false);
      setCatalogLoadState("idle");
      await loadCaseCatalog();
      setStatus(t("adminSaved"));
    } catch (assignmentError) {
      setError(assignmentError instanceof Error ? assignmentError.message : t("adminCaseCatalogLoadFailed"));
    }
  };

  const cloneWorkflowFlowDraft = async () => {
    const [flowKey] = workflowFlowRef.split("@");
    if (!flowKey) return;
    try {
      const draft = await createDraftFlowPackVersion(adminAuth, flowKey, "SK");
      setFlowPacks((items) => [draft, ...items]);
      setWorkflowFlowRef(`${draft.flow_key}@${draft.version}`);
      setWorkflowValidation(`draft: ${draft.flow_key}@${draft.version}`);
    } catch (draftError) {
      setError(draftError instanceof Error ? draftError.message : t("adminCaseCatalogLoadFailed"));
    }
  };

  const runAction = async (action: () => Promise<unknown>, successMessage: string) => {
    setError("");
    setStatus("");
    try {
      await action();
      setStatus(successMessage);
      await reload();
      await loadUsersPage(usersOffset);
      return true;
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : t("adminSaveFailed"));
      return false;
    }
  };

  const runFormAction = async (action: () => Promise<unknown>, successMessage: string) => {
    if (formSubmittingRef.current) {
      return false;
    }
    formSubmittingRef.current = true;
    setFormSubmitting(true);
    try {
      return await runAction(action, successMessage);
    } finally {
      formSubmittingRef.current = false;
      setFormSubmitting(false);
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

  const exportAdminCase = async (caseItem: AdminCaseSummary) => {
    if (!selectedCaseUser || !caseDeleteReason.trim()) {
      setError(t("adminCasesExportReasonRequired"));
      return;
    }
    setError("");
    setStatus("");
    setExportingAdminCaseId(caseItem.case_id);
    try {
      const exported = await fetchAdminCaseExportBlob(
        adminAuth,
        caseItem.case_id,
        selectedCaseUser.user_id,
        caseDeleteReason.trim()
      );
      const objectUrl = URL.createObjectURL(exported.blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = exported.filename;
      anchor.rel = "noopener";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
      setStatus(t("adminCasesExportSuccess"));
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : t("adminCasesExportFailed"));
    } finally {
      setExportingAdminCaseId(null);
    }
  };

  const localProfiles = activeProfiles.filter((profile) => profile.model_profile_id.includes("local") || profile.provider_id.includes("local"));
  const externalProfiles = activeProfiles.filter((profile) => !localProfiles.includes(profile));
  const enabledProfiles = activeProfiles.filter((profile) => profile.enabled);
  const freeDefaultProfile = activeProfiles.find((profile) => profile.is_default_for_free);
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
    model_parameters: JSON.stringify(provider.model_parameters ?? {}, null, 2),
    is_external: provider.is_external,
    is_local: provider.is_local,
    enabled: provider.enabled,
    reason: "",
    ...overrides
  });
  const userToForm = (targetUser: AdminUserSummary, overrides: Partial<typeof emptyUserForm> = {}) => ({
    user_id: targetUser.user_id,
    email: targetUser.email,
    full_name: targetUser.full_name,
    role: targetUser.role,
    is_enabled: targetUser.is_enabled,
    reason: "",
    ...overrides
  });
  const showUserEditForm = (targetUser: AdminUserSummary) => {
    setUserForm(userToForm(targetUser));
    setUserMode("edit");
    setStatus("");
    setError("");
  };
  const cancelUserForm = () => {
    setUserForm(emptyUserForm);
    setUserMode("table");
    setStatus("");
    setError("");
  };
  const saveUserForm = async () => {
    const saved = await runFormAction(
      () => updateAdminUser(adminAuth, userForm.user_id, {
        role: userForm.role,
        is_enabled: userForm.is_enabled,
        reason: userForm.reason || "Updated from admin user management."
      }),
      t("adminUserSaved")
    );
    if (saved) {
      setUserForm(emptyUserForm);
      setUserMode("table");
    }
  };
  const deleteProviderFromCredentials = async (provider: AIModelAdminDashboard["providers"][number]) => {
    const reason = window.prompt(t("adminProviderDeleteReasonPrompt"), "Soft delete provider from admin UI.");
    if (!reason?.trim()) {
      return;
    }
    const deleted = await runAction(
      () => deleteAIModelProvider(adminAuth, provider.provider_id, { reason: reason.trim() }),
      t("adminProviderDeleted")
    );
    if (deleted) {
      setProviderCredentialsMode("table");
      setProviderMode("table");
      setProviderForm(emptyProvider);
    }
  };
  const credentialToForm = (credential: AIModelCredential) => ({
    credential_id: credential.credential_id,
    provider_id: credential.provider_id,
    credential_name: credential.credential_name,
    secret_type: credential.secret_type,
    secret_value: "",
    enabled: credential.enabled,
    reason: ""
  });
  const showCredentialCreateForm = () => {
    setCredentialForm({
      ...emptyCredential,
      provider_id: activeProviders[0]?.provider_id ?? dashboard?.providers[0]?.provider_id ?? ""
    });
    setProviderCredentialsMode("create");
    setStatus("");
    setError("");
  };
  const showCredentialEditForm = (credential: AIModelCredential) => {
    setCredentialForm(credentialToForm(credential));
    setProviderCredentialsMode("edit");
    setStatus("");
    setError("");
  };
  const cancelCredentialForm = () => {
    setCredentialForm(emptyCredential);
    setProviderCredentialsMode("table");
    setStatus("");
    setError("");
  };
  const saveCredentialForm = async () => {
    const isExistingWithoutSecret = Boolean(credentialForm.credential_id) && !credentialForm.secret_value.trim();
    const saved = await runFormAction(
      () => isExistingWithoutSecret
        ? patchAIModelCredential(adminAuth, credentialForm.credential_id as string, {
          enabled: credentialForm.enabled,
          reason: credentialForm.reason || "Update provider credential status from admin UI."
        })
        : upsertAIModelCredential(adminAuth, credentialForm),
      t("adminSaved")
    );
    if (saved) {
      setCredentialForm(emptyCredential);
      setProviderCredentialsMode("table");
    }
  };
  const toggleCredential = async (credential: AIModelCredential) => {
    const updated = await runAction(
      () => patchAIModelCredential(adminAuth, credential.credential_id, {
        enabled: !credential.enabled,
        reason: credential.enabled ? "Disable provider credential from admin UI." : "Enable provider credential from admin UI."
      }),
      credential.enabled ? t("adminCredentialDisabled") : t("adminCredentialEnabled")
    );
    if (updated) {
      setCredentialForm(emptyCredential);
      setProviderCredentialsMode("table");
    }
  };
  const showProviderAdminCreateForm = () => {
    setProviderForm(emptyProvider);
    setProviderMode("create");
    setStatus("");
    setError("");
  };
  const showProviderAdminEditForm = (provider: AIModelAdminDashboard["providers"][number]) => {
    setProviderForm(providerToForm(provider));
    setProviderMode("edit");
    setStatus("");
    setError("");
  };
  const cancelProviderAdminForm = () => {
    setProviderForm(emptyProvider);
    setProviderMode("table");
    setStatus("");
    setError("");
  };
  const saveProviderAdminForm = async () => {
    const saved = await runFormAction(
      () => upsertAIModelProvider(adminAuth, {
        ...providerForm,
        model_parameters: parseModelParameters(providerForm.model_parameters)
      }),
      t("adminProviderSaved")
    );
    if (saved) {
      setProviderForm(emptyProvider);
      setProviderMode("table");
    }
  };
  const profileToForm = (profile: AIModelProfile, overrides: Partial<typeof emptyProfile> = {}) => ({
    model_profile_id: profile.model_profile_id,
    provider_id: profile.provider_id,
    model_code: profile.model_code,
    deployment_name: profile.deployment_name,
    model_parameters: JSON.stringify(profile.model_parameters ?? {}, null, 2),
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
  const showProfileCreateForm = () => {
    setProfileForm(emptyProfile);
    setProfileMode("create");
    setStatus("");
    setError("");
  };
  const showProfileEditForm = (profile: AIModelProfile) => {
    setProfileForm(profileToForm(profile));
    setProfileMode("edit");
    setStatus("");
    setError("");
  };
  const cancelProfileForm = () => {
    setProfileForm(emptyProfile);
    setProfileMode("table");
    setStatus("");
    setError("");
  };
  const saveProfileForm = async () => {
    const saved = await runFormAction(
      () => upsertAIModelProfile(adminAuth, {
        ...profileForm,
        model_parameters: parseModelParameters(profileForm.model_parameters)
      }),
      t("adminProfileSaved")
    );
    if (saved) {
      setProfileForm(emptyProfile);
      setProfileMode("table");
    }
  };
  const deleteProfileFromAdmin = async (profile: AIModelProfile) => {
    const reason = window.prompt(t("adminDeleteReasonPrompt"), "Soft delete model profile from admin UI.");
    if (!reason?.trim()) return;
    const deleted = await runAction(
      () => deleteAIModelProfile(adminAuth, profile.model_profile_id, { reason: reason.trim() }),
      t("adminProfileDeleted")
    );
    if (deleted) {
      setProfileForm(emptyProfile);
      setProfileMode("table");
    }
  };
  const saveProfileChange = (
    profile: AIModelProfile,
    overrides: Partial<typeof emptyProfile>,
    successMessage: string
  ) => {
    setError("");
    setStatus("");
    void (async () => {
      try {
        const form = profileToForm(profile, overrides);
        const savedProfile = await upsertAIModelProfile(adminAuth, {
          ...form,
          model_parameters: parseModelParameters(form.model_parameters)
        });
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
  const groupToForm = (group: AIModelAdminDashboard["groups"][number], overrides: Partial<typeof emptyGroup> = {}) => ({
    group_code: group.group_code,
    display_name: group.display_name,
    priority: group.priority,
    enabled: group.enabled,
    reason: "",
    ...overrides
  });
  const showGroupCreateForm = () => {
    setGroupForm(emptyGroup);
    setGroupMode("create");
    setStatus("");
    setError("");
  };
  const showGroupEditForm = (group: AIModelAdminDashboard["groups"][number]) => {
    setGroupForm(groupToForm(group));
    setGroupMode("edit");
    setStatus("");
    setError("");
  };
  const cancelGroupForm = () => {
    setGroupForm(emptyGroup);
    setGroupMode("table");
    setStatus("");
    setError("");
  };
  const saveGroupForm = async () => {
    const saved = await runFormAction(() => upsertAIModelGroup(adminAuth, groupForm), t("adminGroupSaved"));
    if (saved) {
      setGroupForm(emptyGroup);
      setGroupMode("table");
    }
  };
  const deleteGroupFromAdmin = async (group: AIModelAdminDashboard["groups"][number]) => {
    const reason = window.prompt(t("adminDeleteReasonPrompt"), "Soft delete model group from admin UI.");
    if (!reason?.trim()) return;
    const deleted = await runAction(
      () => deleteAIModelGroup(adminAuth, group.model_group_id, { reason: reason.trim() }),
      t("adminGroupDeleted")
    );
    if (deleted) {
      setGroupForm(emptyGroup);
      setGroupMode("table");
    }
  };
  const showPolicyCreateForm = () => {
    setPolicyForm(emptyPolicy);
    setPolicyMode("create");
    setStatus("");
    setError("");
  };
  const showPolicyEditForm = (policy: AIModelRoutePolicy) => {
    setPolicyForm(policyToForm(policy));
    setPolicyMode("edit");
    setStatus("");
    setError("");
  };
  const cancelPolicyForm = () => {
    setPolicyForm(emptyPolicy);
    setPolicyMode("table");
    setStatus("");
    setError("");
  };
  const savePolicyForm = async () => {
    const saved = await runFormAction(() => upsertAIModelRoutePolicy(adminAuth, policyForm), t("adminPolicySaved"));
    if (saved) {
      setPolicyForm(emptyPolicy);
      setPolicyMode("table");
    }
  };
  const deletePolicyFromAdmin = async (policy: AIModelRoutePolicy) => {
    const reason = window.prompt(t("adminDeleteReasonPrompt"), "Soft delete routing policy from admin UI.");
    if (!reason?.trim()) return;
    const deleted = await runAction(
      () => deleteAIModelRoutePolicy(adminAuth, policy.policy_id, { reason: reason.trim() }),
      t("adminPolicyDeleted")
    );
    if (deleted) {
      setPolicyForm(emptyPolicy);
      setPolicyMode("table");
    }
  };
  const setOllamaModelAsDefault = async (item: OllamaModelInventory["models"][number]) => {
    await setOllamaModelDefault(adminAuth, item.name, ollamaRemoveReason || "Set local Ollama model as default from admin UI.");
    await reloadOllama();
  };
  const selectAdminSection = (section: AdminSection) => {
    setUserMode("table");
    setProviderMode("table");
    setProviderCredentialsMode("table");
    setProfileMode("table");
    setGroupMode("table");
    setPolicyMode("table");
    setUserForm(emptyUserForm);
    setProviderForm(emptyProvider);
    setCredentialForm(emptyCredential);
    setProfileForm(emptyProfile);
    setGroupForm(emptyGroup);
    setPolicyForm(emptyPolicy);
    setStatus("");
    setError("");
    setActiveSection(section);
    if (section === "ollama") {
      void reloadOllama();
    } else if (section === "caseCatalog") {
      void loadCaseCatalog();
    } else if (dashboardLoadState !== "success") {
      void reload();
    }
  };

  const activeFormMode: AdminFormMode = activeSection === "users"
    ? userMode
    : activeSection === "providers"
      ? providerMode
      : activeSection === "profiles"
        ? profileMode
        : activeSection === "credentials"
          ? providerCredentialsMode
          : activeSection === "groups"
            ? groupMode
            : activeSection === "policies"
              ? policyMode
              : "table";

  React.useEffect(() => {
    const formIsOpen = activeFormMode !== "table";
    if (formIsOpen) {
      editFormRef.current?.focus();
    } else if (formWasOpenRef.current) {
      adminContentRef.current?.focus();
    }
    formWasOpenRef.current = formIsOpen;
  }, [activeFormMode, activeSection]);

  const sections: Array<{ key: AdminSection; label: string; icon: React.ReactNode }> = [
    { key: "users", label: t("adminUsersTitle"), icon: <FaUsers aria-hidden="true" /> },
    { key: "assignments", label: t("adminAssignmentTitle"), icon: <FaUserCog aria-hidden="true" /> },
    { key: "cases", label: t("adminCasesTitle"), icon: <FaBriefcase aria-hidden="true" /> },
    { key: "caseCatalog", label: t("adminCaseCatalogTitle"), icon: <FaBriefcase aria-hidden="true" /> },
    { key: "providers", label: t("adminProvidersTitle"), icon: <FaServer aria-hidden="true" /> },
    { key: "profiles", label: t("adminProfilesTitle"), icon: <FaServer aria-hidden="true" /> },
    { key: "credentials", label: t("adminCredentialsTitle"), icon: <FaKey aria-hidden="true" /> },
    { key: "groups", label: t("adminGroupsTitle"), icon: <FaUserPlus aria-hidden="true" /> },
    { key: "policies", label: t("adminPoliciesTitle"), icon: <FaRoute aria-hidden="true" /> },
    { key: "ollamaImport", label: t("adminOllamaImportTitle"), icon: <FaDownload aria-hidden="true" /> },
    { key: "ollama", label: t("adminOllamaTitle"), icon: <FaDownload aria-hidden="true" /> },
    { key: "debug", label: t("adminDebugTitle"), icon: <FaBug aria-hidden="true" /> },
    { key: "audit", label: t("adminAuditTitle"), icon: <FaKey aria-hidden="true" /> }
  ];

  const openCatalogTemplate = (template: DocumentTemplateCatalogItem) => {
    const search = createSearchParams({
      jurisdiction: template.jurisdiction,
      version: String(template.version)
    }).toString();
    window.location.assign(`/app/admin/case-catalog/templates/${encodeURIComponent(template.template_key)}?${search}`);
  };

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
            <React.Fragment key={section.key}>
              <button
                type="button"
                className={`admin-sidebar__item ${activeSection === section.key ? "is-active" : ""}`}
                onClick={() => selectAdminSection(section.key)}
              >
                {section.icon}
                <span>{section.label}</span>
              </button>
              {section.key === "caseCatalog" && activeSection === "caseCatalog" ? (
                <div className="admin-sidebar__submenu" role="group" aria-label={t("adminCaseCatalogTitle")}>
                  <button
                    type="button"
                    className={`admin-sidebar__subitem ${activeCatalogSection === "caseTypes" ? "is-active" : ""}`}
                    onClick={() => setActiveCatalogSection("caseTypes")}
                  >
                    {t("adminCaseCatalogCaseTypesTitle")}
                  </button>
                  <button
                    type="button"
                    className={`admin-sidebar__subitem ${activeCatalogSection === "caseTemplates" ? "is-active" : ""}`}
                    onClick={() => setActiveCatalogSection("caseTemplates")}
                  >
                    {t("adminCaseCatalogTemplatesTitle")}
                  </button>
                  <button
                    type="button"
                    className={`admin-sidebar__subitem ${activeCatalogSection === "casePrompts" ? "is-active" : ""}`}
                    onClick={() => setActiveCatalogSection("casePrompts")}
                  >
                    {t("adminCaseCatalogPromptsTitle")}
                  </button>
                </div>
              ) : null}
            </React.Fragment>
          ))}
        </aside>

        <section
          className="admin-content"
          ref={adminContentRef}
          tabIndex={-1}
          aria-busy={dashboardLoadState === "loading" && !dashboard}
        >
          {activeSection !== "ollama" && activeSection !== "caseCatalog" && dashboardLoadState === "loading" && !dashboard ? (
            <div className="admin-panel admin-load-state" role="status">
              <p>{t("adminLoading")}</p>
            </div>
          ) : null}

          {activeSection !== "ollama" && activeSection !== "caseCatalog" && dashboardLoadState === "error" && !dashboard ? (
            <div className="admin-panel admin-load-state">
              <p>{t("adminLoadFailed")}</p>
              <button className="secondary-button" type="button" onClick={() => void reload()}>
                <FaSyncAlt aria-hidden="true" />{t("adminRetry")}
              </button>
            </div>
          ) : null}

          {dashboard || activeSection === "ollama" || activeSection === "caseCatalog" ? <>
          {activeSection === "users" ? (
            <section className="admin-table-section">
              <h2>{t("adminUsersTitle")}</h2>
              {userMode === "table" ? (
                <>
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
                              <div className="admin-inline-actions">
                                <button className="button ghost" type="button" onClick={() => showUserEditForm(item)}>
                                  <FaEdit aria-hidden="true" />{t("adminEdit")}
                                </button>
                                <button
                                  className="button ghost"
                                  type="button"
                                  onClick={() => void runAction(
                                    () => updateAdminUser(adminAuth, item.user_id, {
                                      role: item.role === "admin" ? "user" : "admin",
                                      is_enabled: item.is_enabled,
                                      reason: "Updated from admin user management."
                                    }),
                                    t("adminUserSaved")
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
                                    t("adminUserSaved")
                                  )}
                                >
                                  {item.is_enabled ? t("adminDisableUser") : t("adminEnableUser")}
                                </button>
                              </div>
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
                </>
              ) : (
                <form ref={editFormRef} tabIndex={-1} className="admin-form-stack" onSubmit={(event) => {
                  event.preventDefault();
                  void saveUserForm();
                }}>
                  <h3>{t("adminUserEditTitle")}</h3>
                  <label>{t("adminUser")}<input value={`${userForm.full_name} (${userForm.email})`} readOnly /></label>
                  <label>{t("adminRole")}<select value={userForm.role} onChange={(event) => setUserForm({ ...userForm, role: event.target.value })}><option value="user">user</option><option value="admin">admin</option></select></label>
                  <div className="admin-toggle-row">
                    <label><input type="checkbox" checked={userForm.is_enabled} onChange={(event) => setUserForm({ ...userForm, is_enabled: event.target.checked })} />{t("adminEnabled")}</label>
                  </div>
                  <label>{t("adminReason")}<input value={userForm.reason} onChange={(event) => setUserForm({ ...userForm, reason: event.target.value })} /></label>
                  <div className="admin-inline-actions">
                    <button className="primary-button" type="submit" disabled={formSubmitting}><FaCheck aria-hidden="true" />{t("adminSaveUser")}</button>
                    <button className="button ghost" type="button" onClick={cancelUserForm} disabled={formSubmitting}>{t("adminCancel")}</button>
                  </div>
                </form>
              )}
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
                            <div className="admin-inline-actions">
                              <button
                                className="button ghost"
                                type="button"
                                disabled={caseItem.status === "deleted" || !caseDeleteReason.trim() || exportingAdminCaseId === caseItem.case_id}
                                onClick={() => void exportAdminCase(caseItem)}
                              >
                                <FaDownload aria-hidden="true" />{t("adminCasesExport")}
                              </button>
                              <button
                                className="button ghost"
                                type="button"
                                disabled={caseItem.status === "deleted" || !caseDeleteReason.trim()}
                                onClick={() => void deleteAdminCase(caseItem)}
                              >
                                <FaTrash aria-hidden="true" />{t("adminCasesSoftDelete")}
                              </button>
                            </div>
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

          {activeSection === "caseCatalog" ? (
            <section className="admin-grid">
              <section className="admin-panel">
                <div className="admin-section-heading">
                  <h2>{t("adminCaseCatalogTitle")}</h2>
                  <button className="secondary-button" type="button" onClick={() => void loadCaseCatalog()}>
                    {t("adminRefresh")}
                  </button>
                </div>
                <p className="admin-muted">{t("adminCaseCatalogHelp")}</p>
                <p className="admin-muted">{t("adminCaseCatalogPrivacyNote")}</p>
              </section>

              {catalogLoadState === "loading" ? (
                <section className="admin-panel admin-load-state" role="status">
                  <p>{t("adminCaseCatalogLoading")}</p>
                </section>
              ) : null}

              {catalogLoadState === "error" ? (
                <section className="admin-panel admin-load-state">
                  <p>{t("adminCaseCatalogLoadFailed")}</p>
                  <button className="secondary-button" type="button" onClick={() => void loadCaseCatalog()}>
                    <FaSyncAlt aria-hidden="true" />{t("adminRetry")}
                  </button>
                </section>
              ) : null}

              {catalogLoadState === "success" ? (
                <>
                  {activeCatalogSection === "caseTypes" ? (
                  <section className="admin-panel">
                    <h2>{t("adminCaseCatalogCaseTypesTitle")}</h2>
                    <AdminRecordsTable
                      emptyLabel={t("adminCaseCatalogEmptyCaseTypes")}
                      headers={[
                        t("adminCaseCatalogCaseType"),
                        t("adminCaseCatalogJurisdiction"),
                        t("adminCaseCatalogLinkedTemplates"),
                        t("adminCaseCatalogPromptStatus"),
                        "LangGraph / flow",
                        "Validation",
                        t("adminStatus"),
                        t("adminAction")
                      ]}
                      rows={catalogCaseTypes.map((item) => {
                        const assignment = workflowAssignments.find((candidate) =>
                          candidate.case_type_key === item.case_type_key && candidate.is_active
                        );
                        return [
                          <div>
                            <strong>{item.name}</strong>
                            <div><small>{item.case_type_key}</small></div>
                          </div>,
                          [item.jurisdiction, item.language].filter(Boolean).join(" / "),
                          renderLinkedTemplatesCell(item.templates, t("adminCaseCatalogNoLinkedTemplates")),
                          item.prompt ? t("adminCaseCatalogPromptAvailable") : t("adminCaseCatalogPromptMissing"),
                          assignment
                            ? `${assignment.graph_key}@${assignment.graph_version} / ${assignment.flow_key}@${assignment.flow_version}`
                            : t("adminNotConfigured"),
                          assignment?.validation_status ?? t("adminNotConfigured"),
                          item.is_enabled ? t("adminEnabled") : t("adminDisabled"),
                          <button
                            className="button ghost"
                            type="button"
                            onClick={() => {
                              setWorkflowCaseTypeKey(item.case_type_key);
                              if (assignment) {
                                setWorkflowGraphRef(`${assignment.graph_key}@${assignment.graph_version}`);
                                setWorkflowFlowRef(`${assignment.flow_key}@${assignment.flow_version}`);
                              }
                              setWorkflowReplacementConfirmed(false);
                              setWorkflowValidation("");
                            }}
                          >
                            {t("adminEdit")}
                          </button>
                        ];
                      })}
                    />
                    <form className="admin-form-stack" onSubmit={(event) => event.preventDefault()}>
                      <h3>Case workflow assignment</h3>
                      <p className="admin-muted">
                        Only reviewed registered graphs and schema-constrained flow-pack versions can be assigned.
                        Published versions are immutable and changes apply only to new cases.
                      </p>
                      <label>
                        {t("adminCaseCatalogCaseType")}
                        <select value={workflowCaseTypeKey} onChange={(event) => setWorkflowCaseTypeKey(event.target.value)}>
                          <option value="">{t("adminNotConfigured")}</option>
                          {catalogCaseTypes.filter((item) => item.is_enabled).map((item) => (
                            <option key={item.case_type_key} value={item.case_type_key}>{item.name}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Registered LangGraph
                        <select value={workflowGraphRef} onChange={(event) => setWorkflowGraphRef(event.target.value)}>
                          {workflowGraphs.map((graph) => (
                            <option key={`${graph.graph_key}@${graph.graph_version}`} value={`${graph.graph_key}@${graph.graph_version}`}>
                              {graph.graph_key}@{graph.graph_version}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Published flow pack
                        <select value={workflowFlowRef} onChange={(event) => setWorkflowFlowRef(event.target.value)}>
                          <option value="">{t("adminNotConfigured")}</option>
                          {flowPacks.map((flow) => (
                            <option key={`${flow.flow_key}@${flow.version}`} value={`${flow.flow_key}@${flow.version}`}>
                              {flow.title} — {flow.flow_key}@{flow.version} ({flow.lifecycle_state})
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={workflowReplacementConfirmed}
                          onChange={(event) => setWorkflowReplacementConfirmed(event.target.checked)}
                        />
                        Confirm prospective replacement of the active default assignment
                      </label>
                      {workflowValidation ? <p className="form-success">{workflowValidation}</p> : null}
                      <div className="admin-inline-actions">
                        <button className="secondary-button" type="button" disabled={!workflowFlowRef} onClick={() => void cloneWorkflowFlowDraft()}>
                          Create immutable-version draft
                        </button>
                        <button className="secondary-button" type="button" disabled={!workflowCaseTypeKey || !workflowFlowRef} onClick={() => void validateWorkflowAssignment()}>
                          Validate compatibility
                        </button>
                        <button className="primary-button" type="button" disabled={!workflowCaseTypeKey || !workflowFlowRef || !workflowReplacementConfirmed} onClick={() => void saveWorkflowAssignment()}>
                          Assign for new cases
                        </button>
                      </div>
                    </form>
                  </section>
                  ) : null}

                  {activeCatalogSection === "caseTemplates" ? (
                  <section className="admin-panel">
                    <h2>{t("adminCaseCatalogTemplatesTitle")}</h2>
                    <AdminRecordsTable
                      emptyLabel={t("adminCaseCatalogEmptyTemplates")}
                      headers={[
                        t("adminCaseCatalogTemplate"),
                        t("adminCaseCatalogCategory"),
                        t("adminCaseCatalogTemplateKind"),
                        t("adminCaseCatalogVersion"),
                        t("adminCaseCatalogCompleteness"),
                        t("adminCaseCatalogSourceProfile"),
                        t("adminCaseCatalogSourceCaptured"),
                        t("adminCaseCatalogLegalReview"),
                        t("adminCaseCatalogStoredAt"),
                        t("adminStatus")
                      ]}
                      rows={catalogTemplates.map((item) => [
                        <button className="button ghost admin-link-button" type="button" onClick={() => openCatalogTemplate(item)}>
                          <strong>{item.title}</strong>
                          <div><small>{item.template_key}</small></div>
                        </button>,
                        item.category,
                        item.template_kind,
                        `v${item.version}`,
                        (item.body_completeness_status ?? "metadata_only").replaceAll("_", " "),
                        item.source_profile || t("adminNotConfigured"),
                        item.source_captured_at ?? t("adminNotConfigured"),
                        item.source_review_status === "reviewed_full_body"
                          ? `${t("adminCaseCatalogReviewed")}${item.reviewed_by ? `: ${item.reviewed_by}` : ""}`
                          : (item.source_review_status ?? "unreviewed").replaceAll("_", " "),
                        item.stored_at ?? item.created_at ?? t("adminNotConfigured"),
                        item.is_enabled
                          ? item.newer_version_available
                            ? t("adminCaseCatalogNewerVersionAvailable")
                            : t("adminEnabled")
                          : t("adminDisabled")
                      ])}
                    />
                  </section>
                  ) : null}

                  {activeCatalogSection === "casePrompts" ? (
                  <section className="admin-panel">
                    <h2>{t("adminCaseCatalogPromptsTitle")}</h2>
                    <AdminRecordsTable
                      emptyLabel={t("adminCaseCatalogEmptyPrompts")}
                      headers={[
                        t("adminCaseCatalogCaseType"),
                        t("adminCaseCatalogLinkedTemplates"),
                        t("adminCaseCatalogPrompt")
                      ]}
                      rows={catalogPrompts.map((item) => [
                        <div>
                          <strong>{item.case_type_name}</strong>
                          <div><small>{item.case_type_key}</small></div>
                        </div>,
                        renderLinkedTemplatesCell(item.linked_templates, t("adminCaseCatalogNoLinkedTemplates")),
                        <details>
                          <summary>{t("adminCaseCatalogViewPrompt")}</summary>
                          <div style={{ whiteSpace: "pre-wrap" }}>{item.prompt?.prompt_text ?? ""}</div>
                        </details>
                      ])}
                    />
                  </section>
                  ) : null}
                </>
              ) : null}
            </section>
          ) : null}

          {activeSection === "providers" ? (
            <section className="admin-panel">
              <h2>{t("adminProvidersTitle")}</h2>
              {providerMode === "table" ? (
                <>
                  <button className="primary-button" type="button" onClick={showProviderAdminCreateForm}>
                    <FaPlus aria-hidden="true" />{t("adminAddProvider")}
                  </button>
                  <AdminRecordsTable
                    emptyLabel={t("adminEmptyProviders")}
                    headers={[t("adminProviderCode"), t("adminProviderType"), t("adminBaseUrl"), t("adminStatus"), t("adminAction")]}
                    rows={activeProviders.map((provider) => [
                      provider.display_name,
                      provider.provider_type,
                      provider.base_url || provider.health_check_url || t("adminNotConfigured"),
                      provider.enabled ? t("adminEnabled") : t("adminDisabled"),
                      <div className="admin-inline-actions">
                        <button className="button ghost" type="button" onClick={() => showProviderAdminEditForm(provider)}>
                          <FaEdit aria-hidden="true" />{t("adminEdit")}
                        </button>
                        <button className="button ghost" type="button" onClick={() => void deleteProviderFromCredentials(provider)}>
                          <FaTrash aria-hidden="true" />{t("adminDeleteProvider")}
                        </button>
                      </div>
                    ])}
                  />
                </>
              ) : (
                <form ref={editFormRef} tabIndex={-1} className="admin-form-stack" onSubmit={(event) => {
                  event.preventDefault();
                  void saveProviderAdminForm();
                }}>
                  <h3>{providerMode === "create" ? t("adminProviderCreateTitle") : t("adminProviderEditTitle")}</h3>
                  <label>{t("adminProviderCode")}<input value={providerForm.provider_code} onChange={(event) => setProviderForm({ ...providerForm, provider_code: event.target.value })} disabled={providerMode === "edit"} /></label>
                  <label>{t("adminProviderType")}<select value={providerForm.provider_type} onChange={(event) => setProviderForm({ ...providerForm, provider_type: event.target.value })}><option value="local">local</option><option value="ollama">ollama</option><option value="azurefoundry">azurefoundry</option><option value="openai">openai</option><option value="openai_compatible">openai_compatible</option></select></label>
                  <label>{t("adminDisplayName")}<input value={providerForm.display_name} onChange={(event) => setProviderForm({ ...providerForm, display_name: event.target.value })} /></label>
                  <label>{t("adminBaseUrl")}<input value={providerForm.base_url} onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })} /></label>
                  <label>{t("adminApiVersion")}<input value={providerForm.api_version} onChange={(event) => setProviderForm({ ...providerForm, api_version: event.target.value })} /></label>
                  <label>{t("adminRegion")}<input value={providerForm.region} onChange={(event) => setProviderForm({ ...providerForm, region: event.target.value })} /></label>
                  <label>{t("adminDataZone")}<input value={providerForm.data_zone} onChange={(event) => setProviderForm({ ...providerForm, data_zone: event.target.value })} /></label>
                  <label>{t("adminHealthUrl")}<input value={providerForm.health_check_url} onChange={(event) => setProviderForm({ ...providerForm, health_check_url: event.target.value })} /></label>
                  <label>{t("adminModelParameters")}<textarea aria-label="adminModelParameters" rows={5} value={providerForm.model_parameters} onChange={(event) => setProviderForm({ ...providerForm, model_parameters: event.target.value })} /></label>
                  <p className="admin-muted">{t("adminModelParametersHelp")}</p>
                  <div className="admin-toggle-row">
                    <label><input type="checkbox" checked={providerForm.is_external} onChange={(event) => setProviderForm({ ...providerForm, is_external: event.target.checked })} />{t("adminExternal")}</label>
                    <label><input type="checkbox" checked={providerForm.is_local} onChange={(event) => setProviderForm({ ...providerForm, is_local: event.target.checked })} />{t("adminLocal")}</label>
                    <label><input type="checkbox" checked={providerForm.enabled} onChange={(event) => setProviderForm({ ...providerForm, enabled: event.target.checked })} />{t("adminEnabled")}</label>
                  </div>
                  <label>{t("adminReason")}<input value={providerForm.reason} onChange={(event) => setProviderForm({ ...providerForm, reason: event.target.value })} /></label>
                  <div className="admin-inline-actions">
                    <button className="primary-button" type="submit" disabled={formSubmitting}><FaCheck aria-hidden="true" />{t("adminSaveProvider")}</button>
                    <button className="button ghost" type="button" onClick={cancelProviderAdminForm} disabled={formSubmitting}>{t("adminCancel")}</button>
                  </div>
                </form>
              )}
            </section>
          ) : null}

          {activeSection === "profiles" ? (
            <section className="admin-panel">
              <h2>{t("adminProfilesTitle")}</h2>
              {profileMode === "table" ? (
                <>
                  <button className="primary-button" type="button" onClick={showProfileCreateForm}>
                    <FaPlus aria-hidden="true" />{t("adminAddProfile")}
                  </button>
                  <AdminRecordsTable
                    emptyLabel={t("adminEmptyProfiles")}
                    headers={[t("adminModelCode"), t("adminProvider"), t("adminDeployment"), t("adminModelParameters"), t("adminPrices"), t("adminStatus"), t("adminAction")]}
                    rows={activeProfiles.map((profile) => [
                      profile.model_profile_id,
                      providerById.get(profile.provider_id)?.display_name ?? profile.provider_id,
                      profile.deployment_name || profile.model_code,
                      Object.keys(profile.model_parameters ?? {}).sort().join(", ") || t("adminNotConfigured"),
                      `${profile.input_price_per_1m}/${profile.cached_input_price_per_1m}/${profile.output_price_per_1m} ${profile.billing_currency}`,
                      `${profile.enabled ? t("adminEnabled") : t("adminDisabled")}${profile.is_default_for_free ? `, ${t("adminDefaultFreeModel")}` : ""}`,
                      <div className="admin-inline-actions">
                        <button className="button ghost" type="button" onClick={() => showProfileEditForm(profile)}>
                          <FaEdit aria-hidden="true" />{t("adminEdit")}
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
                        <button className="button ghost" type="button" onClick={() => void deleteProfileFromAdmin(profile)}>
                          <FaTrash aria-hidden="true" />{t("adminDelete")}
                        </button>
                      </div>
                    ])}
                  />
                  <p className="admin-muted">{t("adminCurrentFreeModel")}: <strong>{freeDefaultLabel}</strong></p>
                </>
              ) : (
                <form ref={editFormRef} tabIndex={-1} className="admin-form-stack" onSubmit={(event) => {
                  event.preventDefault();
                  void saveProfileForm();
                }}>
                  <h3>{profileMode === "create" ? t("adminProfileCreateTitle") : t("adminProfileEditTitle")}</h3>
                  <label>{t("adminProvider")}<select value={profileForm.provider_id} onChange={(event) => setProfileForm({ ...profileForm, provider_id: event.target.value })}><option value="">{t("adminSelect")}</option>{activeProviders.map((provider) => <option key={provider.provider_id} value={provider.provider_id}>{provider.display_name}</option>)}</select></label>
                  <label>{t("adminModelCode")}<input value={profileForm.model_code} onChange={(event) => setProfileForm({ ...profileForm, model_code: event.target.value })} disabled={profileMode === "edit"} /></label>
                  <label>{t("adminDeployment")}<input value={profileForm.deployment_name} onChange={(event) => setProfileForm({ ...profileForm, deployment_name: event.target.value })} /></label>
                  <label>{t("adminModelParameters")}<textarea aria-label="adminProfileModelParameters" rows={5} value={profileForm.model_parameters} onChange={(event) => setProfileForm({ ...profileForm, model_parameters: event.target.value })} /></label>
                  <p className="admin-muted">{t("adminModelParametersProfileHelp")}</p>
                  <div className="admin-price-grid">
                    <label>{t("adminInputPrice")}<input type="number" min="0" step="0.0001" value={profileForm.input_price_per_1m} onChange={(event) => setProfileForm({ ...profileForm, input_price_per_1m: Number(event.target.value) })} /></label>
                    <label>{t("adminCachedInputPrice")}<input type="number" min="0" step="0.0001" value={profileForm.cached_input_price_per_1m} onChange={(event) => setProfileForm({ ...profileForm, cached_input_price_per_1m: Number(event.target.value) })} /></label>
                    <label>{t("adminOutputPrice")}<input type="number" min="0" step="0.0001" value={profileForm.output_price_per_1m} onChange={(event) => setProfileForm({ ...profileForm, output_price_per_1m: Number(event.target.value) })} /></label>
                  </div>
                  <div className="admin-toggle-row">
                    <label><input type="checkbox" checked={profileForm.eu_data_zone_capable} onChange={(event) => setProfileForm({ ...profileForm, eu_data_zone_capable: event.target.checked })} />{t("adminEuDataZone")}</label>
                    <label><input type="checkbox" checked={profileForm.enabled} onChange={(event) => setProfileForm({ ...profileForm, enabled: event.target.checked })} />{t("adminEnabled")}</label>
                  </div>
                  <label>{t("adminReason")}<input value={profileForm.reason} onChange={(event) => setProfileForm({ ...profileForm, reason: event.target.value })} /></label>
                  <div className="admin-inline-actions">
                    <button className="primary-button" type="submit" disabled={formSubmitting}><FaCheck aria-hidden="true" />{t("adminSaveProfile")}</button>
                    <button className="button ghost" type="button" onClick={cancelProfileForm} disabled={formSubmitting}>{t("adminCancel")}</button>
                  </div>
                </form>
              )}
            </section>
          ) : null}

          {activeSection === "credentials" ? (
            <section className="admin-panel" aria-label={t("adminCredentialsTitle")}>
              <h2>{t("adminCredentialsTitle")}</h2>
              <p className="admin-muted">{t("adminCredentialsHelp")}</p>
              {providerCredentialsMode === "table" ? (
                <>
                  <button className="primary-button" type="button" onClick={showCredentialCreateForm}>
                    <FaPlus aria-hidden="true" />{t("adminSaveCredential")}
                  </button>
                  <AdminRecordsTable
                    emptyLabel={t("adminEmptyCredentials")}
                    headers={[t("adminProvider"), t("adminCredentialName"), t("adminCredentialType"), t("adminCredentialPreview"), t("adminStatus"), t("adminAction")]}
                    rows={(dashboard?.credentials ?? []).map((credential) => [
                      providerById.get(credential.provider_id)?.display_name ?? credential.provider_id,
                      credential.credential_name,
                      credential.secret_type,
                      credential.secret_preview || t("adminNotConfigured"),
                      credential.enabled ? t("adminEnabled") : t("adminDisabled"),
                      <div className="admin-inline-actions">
                        <button
                          className="button ghost"
                          type="button"
                          onClick={() => showCredentialEditForm(credential)}
                        >
                          <FaEdit aria-hidden="true" />{t("adminEdit")}
                        </button>
                        <button
                          className="button ghost"
                          type="button"
                          onClick={() => void toggleCredential(credential)}
                        >
                          <FaCheck aria-hidden="true" />{credential.enabled ? t("adminDisableCredential") : t("adminEnableCredential")}
                        </button>
                      </div>
                    ])}
                  />
                </>
              ) : (
                <form ref={editFormRef} tabIndex={-1} className="admin-form-stack" onSubmit={(event) => {
                  event.preventDefault();
                  void saveCredentialForm();
                }}>
                  <h3>{providerCredentialsMode === "create" ? t("adminSaveCredential") : t("adminEdit")}</h3>
                  <label>{t("adminProvider")}<select value={credentialForm.provider_id} onChange={(event) => setCredentialForm({ ...credentialForm, provider_id: event.target.value })} disabled={providerCredentialsMode === "edit"}><option value="">{t("adminSelect")}</option>{activeProviders.map((provider) => <option key={provider.provider_id} value={provider.provider_id}>{provider.display_name}</option>)}</select></label>
                  <label>{t("adminCredentialName")}<input value={credentialForm.credential_name} onChange={(event) => setCredentialForm({ ...credentialForm, credential_name: event.target.value })} disabled={providerCredentialsMode === "edit"} /></label>
                  <label>{t("adminCredentialType")}<input value={credentialForm.secret_type} onChange={(event) => setCredentialForm({ ...credentialForm, secret_type: event.target.value })} disabled={providerCredentialsMode === "edit"} /></label>
                  <label>{t("adminCredentialValue")}<input type="password" value={credentialForm.secret_value} onChange={(event) => setCredentialForm({ ...credentialForm, secret_value: event.target.value })} /></label>
                  <div className="admin-toggle-row">
                    <label><input type="checkbox" checked={credentialForm.enabled} onChange={(event) => setCredentialForm({ ...credentialForm, enabled: event.target.checked })} />{t("adminEnabled")}</label>
                  </div>
                  <label>{t("adminReason")}<input value={credentialForm.reason} onChange={(event) => setCredentialForm({ ...credentialForm, reason: event.target.value })} /></label>
                  <div className="admin-inline-actions">
                    <button className="primary-button" type="submit" disabled={formSubmitting}><FaKey aria-hidden="true" />{t("adminSaveCredential")}</button>
                    <button className="button ghost" type="button" onClick={cancelCredentialForm} disabled={formSubmitting}>{t("adminCancel")}</button>
                  </div>
                </form>
              )}
            </section>
          ) : null}

          {activeSection === "groups" ? (
            <section className={groupMode === "table" ? "admin-grid" : undefined}>
              <section className="admin-panel">
                <h2>{t("adminGroupsTitle")}</h2>
                {groupMode === "table" ? (
                  <>
                    <button className="primary-button" type="button" onClick={showGroupCreateForm}>
                      <FaPlus aria-hidden="true" />{t("adminAddGroup")}
                    </button>
                    <AdminRecordsTable
                      emptyLabel={t("adminEmptyGroups")}
                      headers={[t("adminGroupCode"), t("adminDisplayName"), t("adminPriority"), t("adminStatus"), t("adminAction")]}
                      rows={activeGroups.map((group) => [
                        group.group_code,
                        group.display_name,
                        String(group.priority),
                        group.enabled ? t("adminEnabled") : t("adminDisabled"),
                        <div className="admin-inline-actions">
                          <button className="button ghost" type="button" onClick={() => showGroupEditForm(group)}>
                            <FaEdit aria-hidden="true" />{t("adminEdit")}
                          </button>
                          <button className="button ghost" type="button" onClick={() => void deleteGroupFromAdmin(group)}>
                            <FaTrash aria-hidden="true" />{t("adminDelete")}
                          </button>
                        </div>
                      ])}
                    />
                  </>
                ) : (
                  <form ref={editFormRef} tabIndex={-1} className="admin-form-stack" onSubmit={(event) => {
                    event.preventDefault();
                    void saveGroupForm();
                  }}>
                    <h3>{groupMode === "create" ? t("adminGroupCreateTitle") : t("adminGroupEditTitle")}</h3>
                    <label>{t("adminGroupCode")}<input value={groupForm.group_code} onChange={(event) => setGroupForm({ ...groupForm, group_code: event.target.value })} disabled={groupMode === "edit"} /></label>
                    <label>{t("adminDisplayName")}<input value={groupForm.display_name} onChange={(event) => setGroupForm({ ...groupForm, display_name: event.target.value })} /></label>
                    <label>{t("adminPriority")}<input type="number" value={groupForm.priority} onChange={(event) => setGroupForm({ ...groupForm, priority: Number(event.target.value) })} /></label>
                    <div className="admin-toggle-row">
                      <label><input type="checkbox" checked={groupForm.enabled} onChange={(event) => setGroupForm({ ...groupForm, enabled: event.target.checked })} />{t("adminEnabled")}</label>
                    </div>
                    <label>{t("adminReason")}<input value={groupForm.reason} onChange={(event) => setGroupForm({ ...groupForm, reason: event.target.value })} /></label>
                    <div className="admin-inline-actions">
                      <button className="primary-button" type="submit" disabled={formSubmitting}><FaCheck aria-hidden="true" />{t("adminSaveGroup")}</button>
                      <button className="button ghost" type="button" onClick={cancelGroupForm} disabled={formSubmitting}>{t("adminCancel")}</button>
                    </div>
                  </form>
                )}
              </section>
              {groupMode === "table" ? <form className="admin-panel" onSubmit={(event) => {
                event.preventDefault();
                void runAction(() => addAIModelGroupMember(adminAuth, selectedGroupId, selectedUserId), t("adminSaved"));
              }}>
                <h2>{t("adminMembersTitle")}</h2>
                <AdminRecordsTable
                  emptyLabel={t("adminEmptyMembers")}
                  headers={[t("adminGroup"), t("adminUser"), t("adminCreated")]}
                  rows={(dashboard?.memberships ?? []).filter((membership) => activeGroupIds.has(membership.model_group_id)).map((membership) => [
                    activeGroups.find((group) => group.model_group_id === membership.model_group_id)?.display_name ?? membership.model_group_id,
                    `${membership.full_name} (${membership.email})`,
                    membership.created_at
                  ])}
                />
                <label>{t("adminGroup")}<select value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>{activeGroups.map((group) => <option key={group.model_group_id} value={group.model_group_id}>{group.display_name}</option>)}</select></label>
                <label>{t("adminUser")}<select value={selectedUserId} onChange={(event) => setSelectedUserId(event.target.value)}>{dashboard?.users.map((item) => <option key={item.user_id} value={item.user_id}>{item.full_name} ({item.email})</option>)}</select></label>
                <button className="primary-button" type="submit"><FaUserPlus aria-hidden="true" />{t("adminAssignUser")}</button>
              </form> : null}
            </section>
          ) : null}

          {activeSection === "policies" ? (
            <section className="admin-panel">
              <h2>{t("adminPoliciesTitle")}</h2>
              <p className="admin-muted">{t("adminPolicyHelp")}</p>
              {policyMode === "table" ? (
                <>
                  <button className="primary-button" type="button" onClick={showPolicyCreateForm}>
                    <FaPlus aria-hidden="true" />{t("adminAddPolicy")}
                  </button>
                  <AdminRecordsTable
                    emptyLabel={t("adminEmptyPolicies")}
                    headers={[t("adminPolicyId"), t("adminTaskType"), t("adminPlanCode"), t("adminGroup"), t("adminExternalModel"), t("adminLocalModel"), t("adminPriority"), t("adminStatus"), t("adminAction")]}
                    rows={activePolicies.map((policy) => [
                      policy.policy_id,
                      policy.task_type,
                      policy.plan_code || t("adminDefaultPolicy"),
                      activeGroups.find((group) => group.model_group_id === policy.model_group_id)?.display_name ?? t("adminDefaultPolicy"),
                      policy.preferred_external_model_profile_id ?? t("adminNotConfigured"),
                      policy.preferred_local_model_profile_id ?? t("adminNotConfigured"),
                      String(policy.priority),
                      policy.enabled ? t("adminEnabled") : t("adminDisabled"),
                      <div className="admin-inline-actions">
                        <button className="button ghost" type="button" onClick={() => showPolicyEditForm(policy)}>
                          <FaEdit aria-hidden="true" />{t("adminEdit")}
                        </button>
                        <button className="button ghost" type="button" onClick={() => void deletePolicyFromAdmin(policy)}>
                          <FaTrash aria-hidden="true" />{t("adminDelete")}
                        </button>
                      </div>
                    ])}
                  />
                </>
              ) : (
                <form ref={editFormRef} tabIndex={-1} className="admin-form-stack" onSubmit={(event) => {
                  event.preventDefault();
                  void savePolicyForm();
                }}>
                  <h3>{policyMode === "create" ? t("adminPolicyCreateTitle") : t("adminPolicyEditTitle")}</h3>
                  <div className="admin-price-grid">
                    <label>{t("adminTaskType")}<input value={policyForm.task_type} onChange={(event) => setPolicyForm({ ...policyForm, task_type: event.target.value })} /></label>
                    <label>{t("adminPlanCode")}<input value={policyForm.plan_code} onChange={(event) => setPolicyForm({ ...policyForm, plan_code: event.target.value })} /></label>
                    <label>{t("adminPriority")}<input type="number" value={policyForm.priority} onChange={(event) => setPolicyForm({ ...policyForm, priority: Number(event.target.value) })} /></label>
                  </div>
                  <div className="admin-price-grid">
                    <label>{t("adminGroup")}<select value={policyForm.model_group_id ?? ""} onChange={(event) => setPolicyForm({ ...policyForm, model_group_id: event.target.value || null })}><option value="">{t("adminDefaultPolicy")}</option>{activeGroups.map((group) => <option key={group.model_group_id} value={group.model_group_id}>{group.display_name}</option>)}</select></label>
                    <label>{t("adminExternalModel")}<select value={policyForm.preferred_external_model_profile_id ?? ""} onChange={(event) => setPolicyForm({ ...policyForm, preferred_external_model_profile_id: event.target.value || null })}><option value="">{t("adminSelect")}</option>{externalProfiles.map((profile) => <option key={profile.model_profile_id} value={profile.model_profile_id}>{profile.model_code}</option>)}</select></label>
                    <label>{t("adminLocalModel")}<select value={policyForm.preferred_local_model_profile_id ?? ""} onChange={(event) => setPolicyForm({ ...policyForm, preferred_local_model_profile_id: event.target.value || null })}><option value="">{t("adminSelect")}</option>{localProfiles.map((profile) => <option key={profile.model_profile_id} value={profile.model_profile_id}>{profile.model_code}</option>)}</select></label>
                  </div>
                  <div className="admin-toggle-row">
                    <label><input type="checkbox" checked={policyForm.allow_external} onChange={(event) => setPolicyForm({ ...policyForm, allow_external: event.target.checked })} />{t("adminAllowExternal")}</label>
                    <label><input type="checkbox" checked={policyForm.require_external_ack} onChange={(event) => setPolicyForm({ ...policyForm, require_external_ack: event.target.checked })} />{t("adminRequireAck")}</label>
                    <label><input type="checkbox" checked={policyForm.fallback_local_on_budget} onChange={(event) => setPolicyForm({ ...policyForm, fallback_local_on_budget: event.target.checked })} />{t("adminBudgetFallback")}</label>
                    <label><input type="checkbox" checked={policyForm.enabled} onChange={(event) => setPolicyForm({ ...policyForm, enabled: event.target.checked })} />{t("adminEnabled")}</label>
                  </div>
                  <label>{t("adminReason")}<input value={policyForm.reason} onChange={(event) => setPolicyForm({ ...policyForm, reason: event.target.value })} /></label>
                  <div className="admin-inline-actions">
                    <button className="primary-button" type="submit" disabled={formSubmitting}><FaCheck aria-hidden="true" />{t("adminSavePolicy")}</button>
                    <button className="button ghost" type="button" onClick={cancelPolicyForm} disabled={formSubmitting}>{t("adminCancel")}</button>
                  </div>
                </form>
              )}
            </section>
          ) : null}

          {activeSection === "ollamaImport" ? (
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
          ) : null}

          {activeSection === "ollama" ? (
            <section className="admin-table-section">
              <div className="admin-section-heading">
                <h2>{t("adminOllamaTitle")}</h2>
                <button className="secondary-button" type="button" onClick={() => void reloadOllama()}>{t("adminRefresh")}</button>
              </div>
              <p className="admin-muted">{ollamaInventory?.base_url ?? "http://127.0.0.1:11434"}</p>
              <label className="admin-field">{t("adminOllamaActionReason")}<input value={ollamaRemoveReason} onChange={(event) => setOllamaRemoveReason(event.target.value)} /></label>
              <div className="admin-table-scroll">
                <table>
                  <thead><tr><th>{t("adminModelCode")}</th><th>{t("adminStatus")}</th><th>{t("adminProfilesTitle")}</th><th>{t("adminAction")}</th></tr></thead>
                  <tbody>{ollamaInventory?.models.map((item) => (
                    <tr key={item.name}>
                      <td>
                        <span className={item.is_default ? "admin-default-model-name" : undefined}>{item.name}</span><br />
                        <small>{formatModelSize(item.size)}</small>
                      </td>
                      <td>
                        {!item.installed ? t("adminOllamaNotInstalled") : item.is_default ? t("adminOllamaDefault") : item.is_running ? t("adminOllamaRunning") : t("adminOllamaUnused")}
                        {item.is_default ? <p className="admin-muted">{t("adminOllamaDefaultWarning")}</p> : null}
                        {item.removal_blockers.length ? <ul className="admin-compact-list">{item.removal_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul> : null}
                      </td>
                      <td>{item.configured_profile_ids.length ? item.configured_profile_ids.join(", ") : t("adminNotConfigured")}</td>
                      <td>
                        <div className="admin-inline-actions">
                          <button
                            className="button ghost"
                            type="button"
                            disabled={item.is_default || !item.installed}
                            title={item.is_default ? t("adminOllamaDefaultWarning") : undefined}
                            onClick={() => void runAction(
                              () => setOllamaModelAsDefault(item),
                              t("adminOllamaDefaultSet")
                            )}
                          >
                            <FaCheck aria-hidden="true" />{t("adminOllamaSetDefault")}
                          </button>
                          <button
                            className="button ghost"
                            type="button"
                            disabled={item.is_default || !item.configured_profile_ids.length || !item.removable}
                            title={item.is_default ? t("adminOllamaDefaultWarning") : item.removal_blockers.join(" ")}
                            onClick={() => void runAction(async () => {
                              await removeOllamaModel(adminAuth, item.name, ollamaRemoveReason || "Disable local Ollama model profile from admin UI.");
                              setOllamaRemoveReason("");
                              await reloadOllama();
                            }, t("adminOllamaRemoveStarted"))}
                          >
                            <FaCheck aria-hidden="true" />{t("adminOllamaDisable")}
                          </button>
                          <button
                            className="button ghost"
                            type="button"
                            disabled={item.is_default || !item.removable}
                            title={item.is_default ? t("adminOllamaDefaultWarning") : item.removal_blockers.join(" ")}
                            onClick={() => void runAction(async () => {
                              await removeOllamaModel(adminAuth, item.name, ollamaRemoveReason || "Remove local Ollama model from admin UI.");
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
          ) : null}

          {activeSection === "audit" ? (
            <section className="admin-table-section">
              <h2>{t("adminAuditTitle")}</h2>
              <div className="admin-table-scroll">
                <table><thead><tr><th>{t("adminAction")}</th><th>{t("adminEntity")}</th><th>{t("adminActor")}</th><th>{t("adminCreated")}</th></tr></thead><tbody>{dashboard?.audit_events.map((event) => <tr key={event.audit_event_id}><td>{event.action}</td><td>{event.entity_type}: {event.entity_id}</td><td>{event.admin_email}</td><td>{event.created_at}</td></tr>)}</tbody></table>
              </div>
            </section>
          ) : null}
          {activeSection === "debug" ? (
            <section className="admin-table-section admin-debug">
              <h2>{t("adminDebugTitle")}</h2>
              <p className="admin-muted">{t("adminDebugHelp")}</p>
              <form className="admin-debug__search" onSubmit={(event) => {
                event.preventDefault();
                setError("");
                void fetchAdminDebugTrace(adminAuth, debugCorrelationId.trim())
                  .then(setDebugTrace)
                  .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
              }}>
                <label>{t("adminDebugCorrelationId")}<input value={debugCorrelationId} onChange={(event) => setDebugCorrelationId(event.target.value)} required /></label>
                <button className="primary-button" type="submit"><FaSearch aria-hidden="true" />{t("adminDebugSearch")}</button>
              </form>
              {debugTrace ? <>
                <div className="admin-inline-actions">
                  <button className="button ghost" type="button" onClick={() => setDebugView("timeline")}>{t("adminDebugTimeline")}</button>
                  <button className="button ghost" type="button" onClick={() => setDebugView("flow")}>{t("adminDebugFlow")}</button>
                  <button className="button ghost" type="button" onClick={() => void fetchAdminDebugExport(adminAuth, debugTrace.correlation_id).then(({ blob, filename }) => {
                    const url = URL.createObjectURL(blob);
                    const anchor = document.createElement("a");
                    anchor.href = url;
                    anchor.download = filename;
                    anchor.click();
                    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
                  })}><FaDownload aria-hidden="true" />{t("adminDebugExport")}</button>
                </div>
                <p className="admin-muted">{debugTrace.correlation_id} · {t("adminDebugRetention")}</p>
                {debugView === "timeline" ? (
                  <ol className="admin-debug__timeline">
                    {debugTrace.timeline.map((item) => <li key={`${item.kind}-${item.event_id}`}>
                      <time>{item.created_at}</time>
                      <strong>{item.component} → {item.stage}</strong>
                      <span className={`admin-debug__status admin-debug__status--${item.status}`}>{item.status}</span>
                      <details><summary>{t("adminDebugDetails")}</summary><pre>{JSON.stringify(item.payload, null, 2)}</pre></details>
                    </li>)}
                  </ol>
                ) : (
                  <div className="admin-debug__flow" aria-label={t("adminDebugFlow")}>
                    {debugTrace.flow.nodes.map((node, index) => <React.Fragment key={node.id}>
                      {index > 0 ? <span aria-hidden="true">→</span> : null}<strong>{node.label}</strong>
                    </React.Fragment>)}
                  </div>
                )}
              </> : null}
            </section>
          ) : null}
          </> : null}
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

const renderLinkedTemplatesCell = (
  templates: DocumentTemplateCatalogItem[],
  emptyLabel: string
): React.ReactNode => {
  if (!templates.length) {
    return emptyLabel;
  }
  return (
    <ul className="admin-compact-list">
      {templates.map((template) => (
        <li key={template.template_id || template.template_key}>
          {template.title} ({template.template_key})
        </li>
      ))}
    </ul>
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
