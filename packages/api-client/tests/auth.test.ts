import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../src/client";
import { createAuthApi } from "../src/auth";

function mockFetchOnce(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("auth api", () => {
  it("returns a tokens result when login succeeds without MFA", async () => {
    mockFetchOnce({ access_token: "a", refresh_token: "r", token_type: "Bearer", expires_in_seconds: 900 });
    const auth = createAuthApi(new ApiClient({ baseUrl: "http://api.test" }));

    const result = await auth.login({ org_id: "org-1", email: "a@b.com", password: "secret" });

    expect(result).toEqual({
      kind: "tokens",
      tokens: { access_token: "a", refresh_token: "r", token_type: "Bearer", expires_in_seconds: 900 },
    });
  });

  it("logs in with org_slug instead of org_id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ access_token: "a", refresh_token: "r", token_type: "Bearer", expires_in_seconds: 900 }),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const auth = createAuthApi(new ApiClient({ baseUrl: "http://api.test" }));

    const result = await auth.login({ org_slug: "acme", email: "a@b.com", password: "secret" });

    expect(result.kind).toBe("tokens");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ org_slug: "acme", email: "a@b.com", password: "secret" });
  });

  it("returns an mfa_challenge result when login requires a second factor", async () => {
    mockFetchOnce({ mfa_required: true, mfa_challenge_user_id: "user-1", available_factors: ["totp"] });
    const auth = createAuthApi(new ApiClient({ baseUrl: "http://api.test" }));

    const result = await auth.login({ org_id: "org-1", email: "a@b.com", password: "secret" });

    expect(result).toEqual({
      kind: "mfa_challenge",
      challenge: { mfa_challenge_user_id: "user-1", available_factors: ["totp"], mfa_required: true },
    });
  });

  it("unwraps the DataResponse envelope for verifyMfaChallenge", async () => {
    mockFetchOnce({ data: { access_token: "a", refresh_token: "r", token_type: "Bearer", expires_in_seconds: 900 } });
    const auth = createAuthApi(new ApiClient({ baseUrl: "http://api.test" }));

    const tokens = await auth.verifyMfaChallenge({ user_id: "user-1", code: "123456" });

    expect(tokens.access_token).toBe("a");
  });

  it("unwraps the DataResponse envelope for getMyProfile", async () => {
    mockFetchOnce({
      data: { id: "u1", org_id: "o1", email: "a@b.com", display_name: "A", status: "active", mfa_enabled: false },
    });
    const auth = createAuthApi(new ApiClient({ baseUrl: "http://api.test" }));

    const profile = await auth.getMyProfile();

    expect(profile.org_id).toBe("o1");
  });

  it("posts to the TOTP enroll endpoint with no body and unwraps the response", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ data: { factor_id: "f1", secret: "SECRET", provisioning_uri: "otpauth://…" } }),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const auth = createAuthApi(new ApiClient({ baseUrl: "http://api.test" }));

    const enrollment = await auth.startTotpEnrollment();

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/users/me/mfa/totp/enroll");
    expect(init.method).toBe("POST");
    expect(enrollment.factor_id).toBe("f1");
  });

  it("posts factor_id and code to confirm TOTP enrollment", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ data: { recovery_codes: ["ABC-123"] } }),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const auth = createAuthApi(new ApiClient({ baseUrl: "http://api.test" }));

    const codes = await auth.confirmTotpEnrollment("f1", "654321");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/users/me/mfa/totp/confirm");
    expect(JSON.parse(init.body as string)).toEqual({ factor_id: "f1", code: "654321" });
    expect(codes.recovery_codes).toEqual(["ABC-123"]);
  });

  it("posts to the recovery-codes regenerate endpoint", async () => {
    mockFetchOnce({ data: { recovery_codes: ["NEW-1", "NEW-2"] } });
    const auth = createAuthApi(new ApiClient({ baseUrl: "http://api.test" }));

    const codes = await auth.regenerateRecoveryCodes();

    expect(codes.recovery_codes).toEqual(["NEW-1", "NEW-2"]);
  });

  it("posts to the disable-MFA endpoint", async () => {
    const fetchMock = mockFetchOnce(undefined, 204);
    const auth = createAuthApi(new ApiClient({ baseUrl: "http://api.test" }));

    await auth.disableMfa();

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/users/me/mfa/disable");
    expect(init.method).toBe("POST");
  });

  it("unwraps the DataResponse envelope for listSessions", async () => {
    mockFetchOnce({
      data: [
        {
          id: "s1", device_label: "Chrome on macOS", ip_address: "127.0.0.1",
          created_at: "2026-01-01T00:00:00Z", expires_at: "2026-01-08T00:00:00Z", is_current: false,
        },
      ],
    });
    const auth = createAuthApi(new ApiClient({ baseUrl: "http://api.test" }));

    const sessions = await auth.listSessions();

    expect(sessions).toHaveLength(1);
    expect(sessions[0].device_label).toBe("Chrome on macOS");
  });

  it("sends a DELETE request when revoking a session", async () => {
    const fetchMock = mockFetchOnce(undefined, 204);
    const auth = createAuthApi(new ApiClient({ baseUrl: "http://api.test" }));

    await auth.revokeSession("s1");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/auth/sessions/s1");
    expect(init.method).toBe("DELETE");
  });
});
