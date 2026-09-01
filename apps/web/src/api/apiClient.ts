import { createApiClient } from "@guilddesk/api-client";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// A plain mutable holder rather than React state: the ApiClient instance is
// a long-lived singleton created once at module load, so the access token
// it reads on every request has to live outside the component tree that
// owns it (AuthContext) instead of forcing a new client per render.
const tokenHolder: { accessToken: string | null } = { accessToken: null };

export function setAccessToken(token: string | null): void {
  tokenHolder.accessToken = token;
}

export const api = createApiClient({
  baseUrl: API_BASE_URL,
  getAccessToken: () => tokenHolder.accessToken,
});
