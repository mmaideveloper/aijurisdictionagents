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
  audit_events: AIModelAdminAuditEvent[];
  route_priority: string[];
  compliance_notes: string[];
  grafana_url: string;
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

const adminHeaders = (adminUserId: string): HeadersInit => {
  const config = chatApiRuntimeConfig();
  return {
    "Content-Type": "application/json",
    "x-api-key": config.apiKey,
    "x-jurisdigta-admin-user-id": adminUserId
  };
};

const adminRequest = async <T>(path: string, adminUserId: string, init?: RequestInit): Promise<T> => {
  const config = chatApiRuntimeConfig();
  const response = await fetch(`${config.baseUrl}${path}`, {
    ...init,
    headers: adminHeaders(adminUserId)
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || detail;
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

export const fetchAIModelAdminDashboard = (adminUserId: string): Promise<AIModelAdminDashboard> =>
  adminRequest<AIModelAdminDashboard>("/v1/admin/ai-models", adminUserId, { method: "GET" });

export const fetchAIModelCredentials = (
  adminUserId: string,
  reveal: boolean
): Promise<AIModelCredential[]> =>
  adminRequest<AIModelCredential[]>(`/v1/admin/ai-models/credentials?reveal=${reveal ? "true" : "false"}`, adminUserId, {
    method: "GET"
  });

export const upsertAIModelProvider = (
  adminUserId: string,
  input: ProviderUpsertInput
): Promise<AIModelProvider> =>
  adminRequest<AIModelProvider>("/v1/admin/ai-models/providers", adminUserId, {
    method: "POST",
    body: JSON.stringify(input)
  });

export const upsertAIModelProfile = (
  adminUserId: string,
  input: ProfileUpsertInput
): Promise<AIModelProfile> =>
  adminRequest<AIModelProfile>("/v1/admin/ai-models/profiles", adminUserId, {
    method: "POST",
    body: JSON.stringify(input)
  });

export const upsertAIModelCredential = (
  adminUserId: string,
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
  adminUserId: string,
  userId: string,
  input: UserAdminUpdateInput
): Promise<AdminUserSummary> =>
  adminRequest<AdminUserSummary>(`/v1/admin/users/${encodeURIComponent(userId)}`, adminUserId, {
    method: "PATCH",
    body: JSON.stringify(input)
  });

export const upsertAIModelGroup = (adminUserId: string, input: GroupUpsertInput): Promise<AIModelGroup> =>
  adminRequest<AIModelGroup>("/v1/admin/ai-models/groups", adminUserId, {
    method: "POST",
    body: JSON.stringify(input)
  });

export const addAIModelGroupMember = (
  adminUserId: string,
  modelGroupId: string,
  userId: string
): Promise<AIModelGroupMembership> =>
  adminRequest<AIModelGroupMembership>(`/v1/admin/ai-models/groups/${modelGroupId}/members`, adminUserId, {
    method: "POST",
    body: JSON.stringify({ user_id: userId })
  });

export const upsertAIModelRoutePolicy = (
  adminUserId: string,
  input: PolicyUpsertInput
): Promise<AIModelRoutePolicy> =>
  adminRequest<AIModelRoutePolicy>("/v1/admin/ai-models/policies", adminUserId, {
    method: "POST",
    body: JSON.stringify(input)
  });
