import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiRequestError } from "../src/client";

function mockFetchOnce(response: { status: number; body?: unknown }) {
  const fetchMock = vi.fn().mockResolvedValue({
    status: response.status,
    ok: response.status >= 200 && response.status < 300,
    json: async () => response.body,
  } as Response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ApiClient", () => {
  it("attaches a bearer token from the access token provider", async () => {
    const fetchMock = mockFetchOnce({ status: 200, body: { ok: true } });
    const client = new ApiClient({ baseUrl: "http://api.test", getAccessToken: () => "token-123" });

    await client.get("/api/v1/whoami");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer token-123");
  });

  it("omits the Authorization header when there is no access token", async () => {
    const fetchMock = mockFetchOnce({ status: 200, body: { ok: true } });
    const client = new ApiClient({ baseUrl: "http://api.test", getAccessToken: () => null });

    await client.get("/api/v1/whoami");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.has("Authorization")).toBe(false);
  });

  it("returns the parsed JSON body on success", async () => {
    mockFetchOnce({ status: 200, body: { data: { id: "1" } } });
    const client = new ApiClient({ baseUrl: "http://api.test" });

    const result = await client.get<{ data: { id: string } }>("/api/v1/things");

    expect(result).toEqual({ data: { id: "1" } });
  });

  it("returns undefined for a 204 No Content response", async () => {
    mockFetchOnce({ status: 204 });
    const client = new ApiClient({ baseUrl: "http://api.test" });

    const result = await client.post<void>("/api/v1/logout", { refresh_token: "x" });

    expect(result).toBeUndefined();
  });

  it("throws an ApiRequestError built from the standard error envelope on a non-2xx response", async () => {
    mockFetchOnce({
      status: 403,
      body: { code: "FORBIDDEN", message: "Not allowed", correlation_id: "abc", details: [] },
    });
    const client = new ApiClient({ baseUrl: "http://api.test" });

    await expect(client.get("/api/v1/secret")).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ApiRequestError);
      const apiError = error as ApiRequestError;
      expect(apiError.status).toBe(403);
      expect(apiError.code).toBe("FORBIDDEN");
      expect(apiError.message).toBe("Not allowed");
      return true;
    });
  });

  it("strips a trailing slash from the base URL", async () => {
    const fetchMock = mockFetchOnce({ status: 200, body: {} });
    const client = new ApiClient({ baseUrl: "http://api.test/" });

    await client.get("/api/v1/things");

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe("http://api.test/api/v1/things");
  });
});
