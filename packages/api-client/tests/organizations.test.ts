import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../src/client";
import { createOrganizationsApi } from "../src/organizations";

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

const SAMPLE_ORG = {
  id: "o1", name: "Acme", slug: "acme", owner_user_id: "u1", status: "active", settings: {},
  description: null, logo_url: null,
};

describe("organizations api", () => {
  it("unwraps the DataResponse envelope for get", async () => {
    mockFetchOnce({ data: SAMPLE_ORG });
    const organizations = createOrganizationsApi(new ApiClient({ baseUrl: "http://api.test" }));

    const org = await organizations.get("o1");

    expect(org.name).toBe("Acme");
  });

  it("sends a PATCH with the given profile fields on update", async () => {
    const fetchMock = mockFetchOnce({ data: { ...SAMPLE_ORG, name: "Acme Corp", slug: "acme-corp" } });
    const organizations = createOrganizationsApi(new ApiClient({ baseUrl: "http://api.test" }));

    await organizations.update("o1", { name: "Acme Corp", slug: "acme-corp" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/organizations/o1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ name: "Acme Corp", slug: "acme-corp" });
  });

  it("sends settings wrapped in a { settings } body on updateSettings", async () => {
    const fetchMock = mockFetchOnce({ data: { ...SAMPLE_ORG, settings: { theme: "dark" } } });
    const organizations = createOrganizationsApi(new ApiClient({ baseUrl: "http://api.test" }));

    await organizations.updateSettings("o1", { theme: "dark" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/organizations/o1/settings");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ settings: { theme: "dark" } });
  });

  it("returns the raw PagedResponse from searchMembers", async () => {
    mockFetchOnce({
      data: [{ id: "u1", org_id: "o1", email: "a@b.com", display_name: "A", status: "active", mfa_enabled: false }],
      page: 1, page_size: 20, total: 1, total_pages: 1,
    });
    const organizations = createOrganizationsApi(new ApiClient({ baseUrl: "http://api.test" }));

    const result = await organizations.searchMembers("o1");

    expect(result.total).toBe(1);
    expect(result.data[0].email).toBe("a@b.com");
  });

  it("builds a query string from the given search params", async () => {
    const fetchMock = mockFetchOnce({ data: [], page: 2, page_size: 10, total: 0, total_pages: 0 });
    const organizations = createOrganizationsApi(new ApiClient({ baseUrl: "http://api.test" }));

    await organizations.searchMembers("o1", { page: 2, page_size: 10, q: "alice", status: "active", sort: "email" });

    const [url] = fetchMock.mock.calls[0] as [string];
    const parsed = new URL(url);
    expect(parsed.searchParams.get("q")).toBe("alice");
    expect(parsed.searchParams.get("status")).toBe("active");
    expect(parsed.searchParams.get("sort")).toBe("email");
  });

  it("unwraps the DataResponse envelope for getMember", async () => {
    mockFetchOnce({
      data: { id: "u1", org_id: "o1", email: "a@b.com", display_name: "A", status: "active", mfa_enabled: false },
    });
    const organizations = createOrganizationsApi(new ApiClient({ baseUrl: "http://api.test" }));

    const member = await organizations.getMember("o1", "u1");

    expect(member.email).toBe("a@b.com");
  });
});
