import { ApiClient, type ApiClientOptions } from "./client";
import { createAuthApi } from "./auth";
import { createOrganizationsApi } from "./organizations";
import { createRolesApi } from "./roles";
import { createTicketsApi } from "./tickets";

export * from "./types";
export * from "./client";
export * from "./auth";
export * from "./organizations";
export * from "./roles";
export * from "./tickets";

export function createApiClient(options: ApiClientOptions) {
  const client = new ApiClient(options);
  return {
    client,
    auth: createAuthApi(client),
    organizations: createOrganizationsApi(client),
    roles: createRolesApi(client),
    tickets: createTicketsApi(client),
  };
}

export type GuildDeskApi = ReturnType<typeof createApiClient>;
