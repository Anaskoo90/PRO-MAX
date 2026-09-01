import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../src/client";
import { createAuthApi } from "../src/auth";

function mockFetchOnce(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status,
      ok: status >= 200 && status < 300,
      json: async () => body,
    } as Response),
  );
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
});
