import type { ApiClient } from "./client";
import type { UserProfile } from "./auth";
import type { DataResponse, PagedResponse } from "./types";

// Mirrors app.identity.presentation.schemas.OrganizationResponse — the
// freeform `settings` dict is a separate concept from the four profile
// fields Phase 2B actually exposes editing for (name/slug/description/
// logo_url), which go through PATCH /organizations/{org_id}, not
// PUT .../settings.

export interface Organization {
  id: string;
  name: string;
  slug: string;
  owner_user_id: string;
  status: string;
  settings: Record<string, unknown>;
  description: string | null;
  logo_url: string | null;
}

export interface UpdateOrganizationProfile {
  name?: string;
  slug?: string;
  description?: string;
  logo_url?: string;
}

export interface MemberSearchParams {
  page?: number;
  page_size?: number;
  q?: string;
  status?: string;
  /** e.g. "-created_at" or "display_name" — see _MEMBER_SORT_FIELDS on the backend. */
  sort?: string;
}

export function createOrganizationsApi(client: ApiClient) {
  return {
    async get(orgId: string): Promise<Organization> {
      const response = await client.get<DataResponse<Organization>>(`/api/v1/organizations/${orgId}`);
      return response.data;
    },

    async update(orgId: string, patch: UpdateOrganizationProfile): Promise<Organization> {
      const response = await client.patch<DataResponse<Organization>>(`/api/v1/organizations/${orgId}`, patch);
      return response.data;
    },

    async updateSettings(orgId: string, settings: Record<string, unknown>): Promise<Organization> {
      const response = await client.put<DataResponse<Organization>>(`/api/v1/organizations/${orgId}/settings`, {
        settings,
      });
      return response.data;
    },

    async searchMembers(orgId: string, params: MemberSearchParams = {}): Promise<PagedResponse<UserProfile>> {
      const query = new URLSearchParams();
      if (params.page !== undefined) query.set("page", String(params.page));
      if (params.page_size !== undefined) query.set("page_size", String(params.page_size));
      if (params.q) query.set("q", params.q);
      if (params.status) query.set("status", params.status);
      if (params.sort) query.set("sort", params.sort);

      const queryString = query.toString();
      return client.get<PagedResponse<UserProfile>>(
        `/api/v1/organizations/${orgId}/members${queryString ? `?${queryString}` : ""}`,
      );
    },

    async getMember(orgId: string, userId: string): Promise<UserProfile> {
      const response = await client.get<DataResponse<UserProfile>>(`/api/v1/organizations/${orgId}/members/${userId}`);
      return response.data;
    },
  };
}
