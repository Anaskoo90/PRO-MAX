import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: { id: "u1", org_id: "org-1", email: "a@b.com", display_name: "A", status: "active", mfa_enabled: false },
    login: vi.fn(),
    completeMfaChallenge: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock("../../api/apiClient", () => ({
  api: {
    roles: { getPermissionMatrix: vi.fn(), listForMember: vi.fn(), assignToUser: vi.fn(), revokeFromUser: vi.fn() },
    organizations: { searchMembers: vi.fn() },
  },
}));

import { api } from "../../api/apiClient";
import { RolesPage } from "../RolesPage";

const SAMPLE_MATRIX = {
  permissions: [
    { id: "p1", resource: "role", action: "read", description: "View roles" },
    { id: "p2", resource: "role", action: "assign", description: "Assign a role" },
  ],
  roles: [
    { id: "r1", org_id: null, name: "member", description: "Baseline", is_system_role: true, parent_role_id: null, permission_ids: ["p1"] },
    { id: "r2", org_id: "org-1", name: "support", description: "Support staff", is_system_role: false, parent_role_id: null, permission_ids: ["p1", "p2"] },
  ],
};

beforeEach(() => {
  vi.mocked(api.roles.getPermissionMatrix).mockReset();
  vi.mocked(api.roles.listForMember).mockReset();
  vi.mocked(api.roles.assignToUser).mockReset();
  vi.mocked(api.roles.revokeFromUser).mockReset();
  vi.mocked(api.organizations.searchMembers).mockReset();
});

describe("RolesPage", () => {
  it("renders the permission matrix with role columns and check marks", async () => {
    vi.mocked(api.roles.getPermissionMatrix).mockResolvedValue(SAMPLE_MATRIX);

    render(<RolesPage />);

    expect(await screen.findByText("member")).toBeInTheDocument();
    expect(screen.getByText("support")).toBeInTheDocument();
    expect(screen.getByText("read")).toBeInTheDocument();
    expect(screen.getByText("assign")).toBeInTheDocument();
  });

  it("searches for a member and toggles a role assignment on and off", async () => {
    const user = userEvent.setup();
    vi.mocked(api.roles.getPermissionMatrix).mockResolvedValue(SAMPLE_MATRIX);
    vi.mocked(api.organizations.searchMembers).mockResolvedValue({
      data: [{ id: "m1", org_id: "org-1", email: "alice@example.com", display_name: "Alice", status: "active", mfa_enabled: false }],
      page: 1, page_size: 5, total: 1, total_pages: 1,
    });
    vi.mocked(api.roles.listForMember).mockResolvedValue([SAMPLE_MATRIX.roles[0]]);
    vi.mocked(api.roles.assignToUser).mockResolvedValue(undefined);

    render(<RolesPage />);
    await screen.findByText("member");

    await user.type(screen.getByPlaceholderText(/search members/i), "alice");
    const memberOption = await screen.findByRole("button", { name: /alice — alice@example.com/i });
    await user.click(memberOption);

    expect(await screen.findByText(/managing roles for/i)).toBeInTheDocument();
    const checkboxes = await screen.findAllByRole("checkbox");
    expect(checkboxes[0]).toBeChecked(); // member role, already assigned
    expect(checkboxes[1]).not.toBeChecked(); // support role, not yet assigned

    await user.click(checkboxes[1]);

    await waitFor(() => {
      expect(api.roles.assignToUser).toHaveBeenCalledWith("m1", "r2");
    });
  });
});
