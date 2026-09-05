import type { ApiClient } from "./client";
import type { DataResponse } from "./types";

// Mirrors app.identity.presentation.schemas — LoginRequest, TokenResponse,
// MfaChallengeResponse, VerifyMfaChallengeRequest, UserProfileResponse.

// The web dashboard authenticates with org_slug (Phase 2B) rather than the
// raw Organization UUID; exactly one of org_id/org_slug must be set,
// mirroring LoginRequest's own validator on the backend.
export type LoginRequest =
  | { org_slug: string; org_id?: never; email: string; password: string; remember_me?: boolean }
  | { org_id: string; org_slug?: never; email: string; password: string; remember_me?: boolean };

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in_seconds: number;
}

export interface MfaChallenge {
  mfa_challenge_user_id: string;
  available_factors: string[];
}

export type LoginResult =
  | { kind: "tokens"; tokens: TokenResponse }
  | { kind: "mfa_challenge"; challenge: MfaChallenge };

export interface VerifyMfaChallengeRequest {
  user_id: string;
  code: string;
  remember_me?: boolean;
}

export interface UserProfile {
  id: string;
  org_id: string;
  email: string;
  display_name: string;
  status: string;
  mfa_enabled: boolean;
}

export interface Session {
  id: string;
  device_label: string;
  ip_address: string;
  created_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface TotpEnrollment {
  factor_id: string;
  secret: string;
  provisioning_uri: string;
}

export interface RecoveryCodes {
  recovery_codes: string[];
}

function isMfaChallenge(result: TokenResponse | (MfaChallenge & { mfa_required: true })): result is MfaChallenge & {
  mfa_required: true;
} {
  return "mfa_challenge_user_id" in result;
}

export function createAuthApi(client: ApiClient) {
  return {
    /** POST /auth/login returns either a TokenResponse (no MFA needed) or a
     * MfaChallengeResponse (caller must then call verifyMfaChallenge) — the
     * backend distinguishes these by shape, not HTTP status, so the client
     * mirrors that with a discriminated union rather than throwing. */
    async login(request: LoginRequest): Promise<LoginResult> {
      const result = await client.post<TokenResponse | (MfaChallenge & { mfa_required: true })>(
        "/api/v1/auth/login",
        request,
      );
      if (isMfaChallenge(result)) {
        return { kind: "mfa_challenge", challenge: result };
      }
      return { kind: "tokens", tokens: result };
    },

    async verifyMfaChallenge(request: VerifyMfaChallengeRequest): Promise<TokenResponse> {
      const response = await client.post<DataResponse<TokenResponse>>("/api/v1/auth/mfa/verify", request);
      return response.data;
    },

    async refresh(refreshToken: string): Promise<TokenResponse> {
      const response = await client.post<DataResponse<TokenResponse>>("/api/v1/auth/refresh", {
        refresh_token: refreshToken,
      });
      return response.data;
    },

    async logout(refreshToken: string): Promise<void> {
      await client.post<void>("/api/v1/auth/logout", { refresh_token: refreshToken });
    },

    async getMyProfile(): Promise<UserProfile> {
      const response = await client.get<DataResponse<UserProfile>>("/api/v1/users/me");
      return response.data;
    },

    async startTotpEnrollment(): Promise<TotpEnrollment> {
      const response = await client.post<DataResponse<TotpEnrollment>>("/api/v1/users/me/mfa/totp/enroll");
      return response.data;
    },

    async confirmTotpEnrollment(factorId: string, code: string): Promise<RecoveryCodes> {
      const response = await client.post<DataResponse<RecoveryCodes>>("/api/v1/users/me/mfa/totp/confirm", {
        factor_id: factorId,
        code,
      });
      return response.data;
    },

    async regenerateRecoveryCodes(): Promise<RecoveryCodes> {
      const response = await client.post<DataResponse<RecoveryCodes>>(
        "/api/v1/users/me/mfa/recovery-codes/regenerate",
      );
      return response.data;
    },

    async disableMfa(): Promise<void> {
      await client.post<void>("/api/v1/users/me/mfa/disable");
    },

    async listSessions(): Promise<Session[]> {
      const response = await client.get<DataResponse<Session[]>>("/api/v1/auth/sessions");
      return response.data;
    },

    async revokeSession(sessionId: string): Promise<void> {
      await client.delete<void>(`/api/v1/auth/sessions/${sessionId}`);
    },
  };
}
