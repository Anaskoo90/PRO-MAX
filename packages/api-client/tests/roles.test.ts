import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../src/client";
import { createRolesApi } from "../src/roles";

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

describe("roles api", () => {
  it("unwraps the DataResponse envelope for listForOrg", async () => {
    mockFetchOnce({
      data: [
        { id: "r1", org_id: null, name: "member", description: "Baseline", is_system_role: true, parent_role_id: null, permission_ids: ["p1"] },
      ],
    });
    const roles = createRolesApi(new ApiClient({ baseUrl: "http://api.test" }));

    const result = await roles.listForOrg("o1");

    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("member");
  });

  it("unwraps the DataResponse envelope for getPermissionMatrix", async () => {
    mockFetchOnce({
      data: {
        permissions: [{ id: "p1", resource: "role", action: "read", description: "View roles" }],
        roles: [
          { id: "r1", org_id: null, name: "member", description: "Baseline", is_system_role: true, parent_role_id: null, permission_ids: ["p1"] },
        ],
      },
    });
    const roles = createRolesApi(new ApiClient({ baseUrl: "http://api.test" }));

    const matrix = await roles.getPermissionMatrix("o1");

    expect(matrix.permissions).toHaveLength(1);
    expect(matrix.roles[0].permission_ids).toEqual(["p1"]);
  });

  it("unwraps the DataResponse envelope for listForMember", async () => {
    mockFetchOnce({
      data: [
        { id: "r1", org_id: null, name: "member", description: "Baseline", is_system_role: true, parent_role_id: null, permission_ids: ["p1"] },
      ],
    });
    const roles = createRolesApi(new ApiClient({ baseUrl: "http://api.test" }));

    const result = await roles.listForMember("o1", "u1");

    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("member");
  });

  it("posts user_id and role_id to /roles/assign", async () => {
    const fetchMock = mockFetchOnce(undefined, 204);
    const roles = createRolesApi(new ApiClient({ baseUrl: "http://api.test" }));

    await roles.assignToUser("u1", "r1");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/roles/assign");
    expect(JSON.parse(init.body as string)).toEqual({ user_id: "u1", role_id: "r1" });
  });

  it("posts user_id and role_id to /roles/revoke", async () => {
    const fetchMock = mockFetchOnce(undefined, 204);
    const roles = createRolesApi(new ApiClient({ baseUrl: "http://api.test" }));

    await roles.revokeFromUser("u1", "r1");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/roles/revoke");
    expect(JSON.parse(init.body as string)).toEqual({ user_id: "u1", role_id: "r1" });
  });
});
