import type { ApiClient } from "./client";
import type { PagedResponse } from "./types";

// Mirrors app.ticket_system.presentation.schemas.TicketListItemResponse and
// the GET /organizations/{org_id}/tickets query params (status,
// claimed_by_discord_user_id, sort, page, page_size).

export interface TicketListItem {
  id: string;
  ticket_number: number;
  title: string;
  status: string;
  discord_channel_id: string;
  opener_discord_user_id: string | null;
  claimed_by_discord_user_id: string | null;
  created_at: string;
  closed_at: string | null;
}

export interface TicketSearchParams {
  page?: number;
  page_size?: number;
  status?: string;
  claimed_by_discord_user_id?: string;
  /** e.g. "-created_at" or "ticket_number" — see _TICKET_SORT_FIELDS on the backend. */
  sort?: string;
}

export function createTicketsApi(client: ApiClient) {
  return {
    async search(orgId: string, params: TicketSearchParams = {}): Promise<PagedResponse<TicketListItem>> {
      const query = new URLSearchParams();
      if (params.page !== undefined) query.set("page", String(params.page));
      if (params.page_size !== undefined) query.set("page_size", String(params.page_size));
      if (params.status) query.set("status", params.status);
      if (params.claimed_by_discord_user_id) {
        query.set("claimed_by_discord_user_id", params.claimed_by_discord_user_id);
      }
      if (params.sort) query.set("sort", params.sort);

      const queryString = query.toString();
      return client.get<PagedResponse<TicketListItem>>(
        `/api/v1/organizations/${orgId}/tickets${queryString ? `?${queryString}` : ""}`,
      );
    },
  };
}
