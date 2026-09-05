import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../src/client";
import { createInvitationsApi } from "../src/invitations";

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

const SAMPLE_INVITATION = {
  id: "i1",
  org_id: "o1",
  email: "new.hire@example.com",
  role_id: "r1",
  invited_by_user_id: "u1",
  status: "pending",
  created_at: "2026-01-01T00:00:00Z",
  expires_at: "2026-01-08T00:00:00Z",
};

describe("invitations api", () => {
  it("unwraps the DataResponse envelope for listPending", async () => {
    mockFetchOnce({ data: [SAMPLE_INVITATION] });
    const invitations = createInvitationsApi(new ApiClient({ baseUrl: "http://api.test" }));

    const result = await invitations.listPending("o1");

    expect(result).toHaveLength(1);
    expect(result[0].email).toBe("new.hire@example.com");
  });

  it("appends page and page_size query params when listing pending invitations", async () => {
    const fetchMock = mockFetchOnce({ data: [] });
    const invitations = createInvitationsApi(new ApiClient({ baseUrl: "http://api.test" }));

    await invitations.listPending("o1", { page: 2, page_size: 10 });

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe("http://api.test/api/v1/organizations/o1/invitations?page=2&page_size=10");
  });

  it("posts email and role_id when creating an invitation", async () => {
    const fetchMock = mockFetchOnce({ data: SAMPLE_INVITATION }, 201);
    const invitations = createInvitationsApi(new ApiClient({ baseUrl: "http://api.test" }));

    const invitation = await invitations.create("o1", "new.hire@example.com", "r1");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/organizations/o1/invitations");
    expect(JSON.parse(init.body as string)).toEqual({ email: "new.hire@example.com", role_id: "r1" });
    expect(invitation.id).toBe("i1");
  });

  it("sends a DELETE request when revoking an invitation", async () => {
    const fetchMock = mockFetchOnce(undefined, 204);
    const invitations = createInvitationsApi(new ApiClient({ baseUrl: "http://api.test" }));

    await invitations.revoke("o1", "i1");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/organizations/o1/invitations/i1");
    expect(init.method).toBe("DELETE");
  });
});
