import type { ApiClient } from "./client";
import type { DataResponse } from "./types";

// Mirrors app.identity.presentation.schemas — CreateInvitationRequest,
// InvitationResponse. list_pending_invitations accepts page/page_size query
// params but (unlike member search) returns a plain DataResponse<list>, not
// a PagedResponse — the backend doesn't compute a total count for this list.

export interface Invitation {
  id: string;
  org_id: string;
  email: string;
  role_id: string;
  invited_by_user_id: string;
  status: string;
  created_at: string;
  expires_at: string;
}

export interface ListInvitationsParams {
  page?: number;
  page_size?: number;
}

export function createInvitationsApi(client: ApiClient) {
  return {
    async listPending(orgId: string, params: ListInvitationsParams = {}): Promise<Invitation[]> {
      const query = new URLSearchParams();
      if (params.page !== undefined) query.set("page", String(params.page));
      if (params.page_size !== undefined) query.set("page_size", String(params.page_size));

      const queryString = query.toString();
      const response = await client.get<DataResponse<Invitation[]>>(
        `/api/v1/organizations/${orgId}/invitations${queryString ? `?${queryString}` : ""}`,
      );
      return response.data;
    },

    async create(orgId: string, email: string, roleId: string): Promise<Invitation> {
      const response = await client.post<DataResponse<Invitation>>(
        `/api/v1/organizations/${orgId}/invitations`,
        { email, role_id: roleId },
      );
      return response.data;
    },

    async revoke(orgId: string, invitationId: string): Promise<void> {
      await client.delete<void>(`/api/v1/organizations/${orgId}/invitations/${invitationId}`);
    },
  };
}
