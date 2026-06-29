import { chatApiRuntimeConfig } from "./chatClient";

export interface AIModelProvider {
  provider_id: string;
  provider_code: string;
  provider_type: string;
  display_name: string;
  base_url: string;
  api_version: string;
  region: string;
  data_zone: string;
  is_external: boolean;
  is_local: boolean;
  health_check_url: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AIModelProfile {
  model_profile_id: string;
  provider_id: string;
  model_code: string;
  deployment_name: string;
  context_window_tokens: number;
  input_price_per_1m: number;
  cached_input_price_per_1m: number;
  output_price_per_1m: number;
  billing_currency: string;
  effective_from: string | null;
  effective_to: string | null;
  eu_data_zone_capable: boolean;
  is_default_for_free: boolean;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AIModelCredential {
  credential_id: string;
  provider_id: string;
  credential_name: string;
  secret_type: string;
  secret_preview: string;
  secret_value: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  last_revealed_at: string | null;
}

export interface AIModelRoutePolicy {
  policy_id: string;
  task_type: string;
  plan_code: string;
  model_group_id: string | null;
  preferred_external_model_profile_id: string | null;
  preferred_local_model_profile_id: string | null;
  allow_external: boolean;
  require_external_ack: boolean;
  require_eu_data_zone: boolean;
  fallback_local_on_error: boolean;
  fallback_local_on_budget: boolean;
  max_cost_eur: number;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AIModelGroup {
  model_group_id: string;
  group_code: string;
  display_name: string;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AIModelGroupMembership {
  model_group_id: string;
  user_id: string;
  email: string;
  full_name: string;
  created_at: string;
}

export interface AdminUserSummary {
  user_id: string;
  phone_number: string | null;
  email: string;
  full_name: string;
  role: string;
  is_enabled: boolean;
  created_at: string | null;
}

export interface AdminUsersPage {
  items: AdminUserSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface AIModelAdminAuditEvent {
  audit_event_id: string;
  admin_user_id: string;
  admin_email: string;
  action: string;
  entity_type: string;
  entity_id: string;
  old_value_summary: string;
  new_value_summary: string;
  reason: string;
  correlation_id: string;
  created_at: string;
}

export interface AIModelAdminDashboard {
  providers: AIModelProvider[];
  profiles: AIModelProfile[];
  credentials: AIModelCredential[];
  policies: AIModelRoutePolicy[];
  groups: AIModelGroup[];
  memberships: AIModelGroupMembership[];
  users: AdminUserSummary[];
  users_page: {
    total: number;
    limit: number;
    offset: number;
  };
  audit_events: AIModelAdminAuditEvent[];
  route_priority: string[];
  compliance_notes: string[];
  grafana_url: string;
}

export interface OllamaModelInventoryItem {
  name: string;
  model: string;
  modified_at: string;
  size: number;
  digest: string;
  details: Record<string, unknown>;
  configured_profile_ids: string[];
  active_policy_ids: string[];
  is_default: boolean;
  is_running: boolean;
  removable: boolean;
  removal_blockers: string[];
}

export interface OllamaModelInventory {
  base_url: string;
  models: OllamaModelInventoryItem[];
}

export interface OllamaModelJob {
  job_id: string;
  action: string;
  model: string;
  status: string;
  message: string;
  created_at: string;
  updated_at: string;
}

export interface ProviderUpsertInput {
  provider_code: string;
  provider_type: string;
  display_name: string;
  base_url: string;
  region: string;
  data_zone: string;
  health_check_url: string;
  is_external: boolean;
  is_local: boolean;
  enabled: boolean;
  reason: string;
}

export interface ProfileUpsertInput {
  provider_id: string;
  model_code: string;
  deployment_name: string;
  input_price_per_1m: number;
  cached_input_price_per_1m: number;
  output_price_per_1m: number;
  billing_currency: string;
  eu_data_zone_capable: boolean;
  is_default_for_free: boolean;
  enabled: boolean;
  reason: string;
}

export interface CredentialUpsertInput {
  provider_id: string;
  credential_name: string;
  secret_type: string;
  secret_value: string;
  enabled: boolean;
  reason: string;
}

export interface UserAdminUpdateInput {
  role: string;
  is_enabled: boolean;
  reason: string;
}

export interface GroupUpsertInput {
  group_code: string;
  display_name: string;
  priority: number;
  enabled: boolean;
  reason: string;
}

export interface PolicyUpsertInput {
  task_type: string;
  plan_code: string;
  model_group_id: string | null;
  preferred_external_model_profile_id: string | null;
  preferred_local_model_profile_id: string | null;
  allow_external: boolean;
  require_external_ack: boolean;
  require_eu_data_zone: boolean;
  fallback_local_on_error: boolean;
  fallback_local_on_budget: boolean;
  max_cost_eur: number;
  priority: number;
  enabled: boolean;
  reason: string;
}

export interface AdminAuthContext {
  userId: string;
  deviceId?: string;
  deviceAuthToken?: string;
}

type AdminAuthInput = AdminAuthContext | string;

const normalizeAdminAuth = (adminAuth: AdminAuthInput): AdminAuthContext =>
  typeof adminAuth === "string" ? { userId: adminAuth } : adminAuth;

const adminHeaders = (adminAuthInput: AdminAuthInput): HeadersInit => {
  const config = chatApiRuntimeConfig();
  const adminAuth = normalizeAdminAuth(adminAuthInput);
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "x-api-key": config.apiKey,
    "x-jurisdigta-admin-user-id": adminAuth.userId
  };
  if (adminAuth.deviceId && adminAuth.deviceAuthToken) {
    headers["x-jurisdigta-device-id"] = adminAuth.deviceId;
    headers["x-jurisdigta-device-token"] = adminAuth.deviceAuthToken;
  }
  return headers;
};

const adminRequest = async <T>(path: string, adminAuth: AdminAuthInput, init?: RequestInit): Promise<T> => {
  const config = chatApiRuntimeConfig();
  const response = await fetch(`${config.baseUrl}${path}`, {
    ...init,
    headers: adminHeaders(adminAuth)
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      } else if (payload.detail && typeof payload.detail === "object" && "blockers" in payload.detail) {
        const blockers = (payload.detail as { blockers?: unknown }).blockers;
        detail = Array.isArray(blockers) ? blockers.join(" ") : JSON.stringify(payload.detail);
      }
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
};

export const fetchAIModelAdminDashboard = (adminAuth: AdminAuthContext): Promise<AIModelAdminDashboard> =>
  adminRequest<AIModelAdminDashboard>("/v1/admin/ai-models", adminAuth, { method: "GET" });

export const fetchAdminUsers = (
  adminAuth: AdminAuthContext,
  limit: number,
  offset: number,
  query = ""
): Promise<AdminUsersPage> => {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset)
  });
  if (query.trim()) {
    params.set("query", query.trim());
  }
  return adminRequest<AdminUsersPage>(`/v1/admin/users?${params.toString()}`, adminAuth, { method: "GET" });
};

export const fetchAIModelCredentials = (
  adminAuth: AdminAuthInput,
  reveal: boolean
): Promise<AIModelCredential[]> =>
  adminRequest<AIModelCredential[]>(`/v1/admin/ai-models/credentials?reveal=${reveal ? "true" : "false"}`, adminAuth, {
    method: "GET"
  });

export const upsertAIModelProvider = (
  adminUserId: AdminAuthInput,
  input: ProviderUpsertInput
): Promise<AIModelProvider> =>
  adminRequest<AIModelProvider>("/v1/admin/ai-models/providers", adminUserId, {
    method: "POST",
    body: JSON.stringify(input)
  });

export const upsertAIModelProfile = (
  adminUserId: AdminAuthInput,
  input: ProfileUpsertInput
): Promise<AIModelProfile> =>
  adminRequest<AIModelProfile>("/v1/admin/ai-models/profiles", adminUserId, {
    method: "POST",
    body: JSON.stringify(input)
  });

export const upsertAIModelCredential = (
  adminUserId: AdminAuthInput,
  input: CredentialUpsertInput
): Promise<AIModelCredential> =>
  adminRequest<AIModelCredential>(`/v1/admin/ai-models/providers/${input.provider_id}/credentials`, adminUserId, {
    method: "POST",
    body: JSON.stringify({
      credential_name: input.credential_name,
      secret_type: input.secret_type,
      secret_value: input.secret_value,
      enabled: input.enabled,
      reason: input.reason
    })
  });

export const updateAdminUser = (
  adminUserId: AdminAuthInput,
  userId: string,
  input: UserAdminUpdateInput
): Promise<AdminUserSummary> =>
  adminRequest<AdminUserSummary>(`/v1/admin/users/${encodeURIComponent(userId)}`, adminUserId, {
    method: "PATCH",
    body: JSON.stringify(input)
  });

export const upsertAIModelGroup = (adminUserId: AdminAuthInput, input: GroupUpsertInput): Promise<AIModelGroup> =>
  adminRequest<AIModelGroup>("/v1/admin/ai-models/groups", adminUserId, {
    method: "POST",
    body: JSON.stringify(input)
  });

export const addAIModelGroupMember = (
  adminUserId: AdminAuthInput,
  modelGroupId: string,
  userId: string
): Promise<AIModelGroupMembership> =>
  adminRequest<AIModelGroupMembership>(`/v1/admin/ai-models/groups/${modelGroupId}/members`, adminUserId, {
    method: "POST",
    body: JSON.stringify({ user_id: userId })
  });

export const upsertAIModelRoutePolicy = (
  adminUserId: AdminAuthInput,
  input: PolicyUpsertInput
): Promise<AIModelRoutePolicy> =>
  adminRequest<AIModelRoutePolicy>("/v1/admin/ai-models/policies", adminUserId, {
    method: "POST",
    body: JSON.stringify(input)
  });

export const fetchOllamaModels = (adminUserId: AdminAuthInput): Promise<OllamaModelInventory> =>
  adminRequest<OllamaModelInventory>("/v1/admin/ai-models/ollama/models", adminUserId, { method: "GET" });

export const importOllamaModel = (adminUserId: AdminAuthInput, model: string, reason: string): Promise<OllamaModelJob> =>
  adminRequest<OllamaModelJob>("/v1/admin/ai-models/ollama/import", adminUserId, {
    method: "POST",
    body: JSON.stringify({ model, reason })
  });

export const removeOllamaModel = (adminUserId: AdminAuthInput, model: string, reason: string): Promise<OllamaModelJob> =>
  adminRequest<OllamaModelJob>(`/v1/admin/ai-models/ollama/models/${encodeURIComponent(model)}`, adminUserId, {
    method: "DELETE",
    body: JSON.stringify({ reason })
  });
