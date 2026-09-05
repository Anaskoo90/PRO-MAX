import { render, screen, waitFor, within } from "@testing-library/react";
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
    roles: {
      getPermissionMatrix: vi.fn(),
      listForMember: vi.fn(),
      assignToUser: vi.fn(),
      revokeFromUser: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      grantPermission: vi.fn(),
      revokePermission: vi.fn(),
    },
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
  vi.mocked(api.roles.create).mockReset();
  vi.mocked(api.roles.update).mockReset();
  vi.mocked(api.roles.delete).mockReset();
  vi.mocked(api.roles.grantPermission).mockReset();
  vi.mocked(api.roles.revokePermission).mockReset();
  vi.mocked(api.organizations.searchMembers).mockReset();
});

describe("RolesPage", () => {
  it("renders the permission matrix with role columns and check marks", async () => {
    vi.mocked(api.roles.getPermissionMatrix).mockResolvedValue(SAMPLE_MATRIX);

    render(<RolesPage />);

    const table = await screen.findByRole("table");
    expect(within(table).getByText("member")).toBeInTheDocument();
    expect(within(table).getByText("support")).toBeInTheDocument();
    expect(within(table).getByText("read")).toBeInTheDocument();
    expect(within(table).getByText("assign")).toBeInTheDocument();
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
    await screen.findByRole("table");

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

  it("creates a new role and reloads the matrix", async () => {
    const user = userEvent.setup();
    vi.mocked(api.roles.getPermissionMatrix).mockResolvedValue(SAMPLE_MATRIX);
    vi.mocked(api.roles.create).mockResolvedValue({
      id: "r3", org_id: "org-1", name: "Billing", description: "", is_system_role: false, parent_role_id: null, permission_ids: [],
    });

    render(<RolesPage />);
    await screen.findByRole("table");

    await user.type(screen.getByLabelText("New role name"), "Billing");
    await user.click(screen.getByRole("button", { name: "Create role" }));

    await waitFor(() => {
      expect(api.roles.create).toHaveBeenCalledWith("Billing", "");
    });
    // The matrix is reloaded after a successful create.
    expect(api.roles.getPermissionMatrix).toHaveBeenCalledTimes(2);
  });

  it("does not offer rename/delete for a system role, only for a custom role", async () => {
    vi.mocked(api.roles.getPermissionMatrix).mockResolvedValue(SAMPLE_MATRIX);

    render(<RolesPage />);
    await screen.findByRole("table");

    const items = screen.getAllByRole("listitem");
    const systemRoleItem = items.find((item) => item.textContent?.includes("member"));
    const customRoleItem = items.find((item) => item.textContent?.includes("support"));

    expect(systemRoleItem).toBeDefined();
    expect(customRoleItem).toBeDefined();
    // Scope queries to each role's own row rather than the whole page.
    const { getByRole: getByRoleInSystemItem, queryByRole: queryByRoleInSystemItem } = within(systemRoleItem!);
    const { getByRole: getByRoleInCustomItem } = within(customRoleItem!);

    expect(queryByRoleInSystemItem("button", { name: "Rename" })).not.toBeInTheDocument();
    expect(getByRoleInSystemItem("button", { name: "Edit permissions" })).toBeInTheDocument();
    expect(getByRoleInCustomItem("button", { name: "Rename" })).toBeInTheDocument();
    expect(getByRoleInCustomItem("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("renames a custom role on Enter", async () => {
    const user = userEvent.setup();
    vi.mocked(api.roles.getPermissionMatrix).mockResolvedValue(SAMPLE_MATRIX);
    vi.mocked(api.roles.update).mockResolvedValue({ ...SAMPLE_MATRIX.roles[1], name: "Support Lead" });

    render(<RolesPage />);
    await screen.findByRole("table");

    const customRoleItem = screen.getAllByRole("listitem").find((item) => item.textContent?.includes("support"))!;
    await user.click(within(customRoleItem).getByRole("button", { name: "Rename" }));

    const input = within(customRoleItem).getByLabelText("Rename support");
    await user.clear(input);
    await user.type(input, "Support Lead{Enter}");

    await waitFor(() => {
      expect(api.roles.update).toHaveBeenCalledWith("r2", "Support Lead");
    });
  });

  it("deletes a custom role after confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(api.roles.getPermissionMatrix).mockResolvedValue(SAMPLE_MATRIX);
    vi.mocked(api.roles.delete).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<RolesPage />);
    await screen.findByRole("table");

    const customRoleItem = screen.getAllByRole("listitem").find((item) => item.textContent?.includes("support"))!;
    await user.click(within(customRoleItem).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(api.roles.delete).toHaveBeenCalledWith("r2");
    });
  });

  it("does not delete a role when the confirmation is declined", async () => {
    const user = userEvent.setup();
    vi.mocked(api.roles.getPermissionMatrix).mockResolvedValue(SAMPLE_MATRIX);
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<RolesPage />);
    await screen.findByRole("table");

    const customRoleItem = screen.getAllByRole("listitem").find((item) => item.textContent?.includes("support"))!;
    await user.click(within(customRoleItem).getByRole("button", { name: "Delete" }));

    expect(api.roles.delete).not.toHaveBeenCalled();
  });

  it("grants a permission to a custom role when its checkbox is toggled on", async () => {
    const user = userEvent.setup();
    const matrixWithPartialGrant = {
      ...SAMPLE_MATRIX,
      roles: [SAMPLE_MATRIX.roles[0], { ...SAMPLE_MATRIX.roles[1], permission_ids: ["p1"] }],
    };
    vi.mocked(api.roles.getPermissionMatrix).mockResolvedValue(matrixWithPartialGrant);
    vi.mocked(api.roles.grantPermission).mockResolvedValue({ ...matrixWithPartialGrant.roles[1], permission_ids: ["p1", "p2"] });

    render(<RolesPage />);
    await screen.findByRole("table");

    const customRoleItem = screen.getAllByRole("listitem").find((item) => item.textContent?.includes("support"))!;
    await user.click(within(customRoleItem).getByRole("button", { name: "Edit permissions" }));

    // support only has p1 granted here, so p2's checkbox is the unchecked one.
    const checkboxes = within(customRoleItem).getAllByRole("checkbox");
    const uncheckedBox = checkboxes.find((box) => !(box as HTMLInputElement).checked)!;
    await user.click(uncheckedBox);

    await waitFor(() => {
      expect(api.roles.grantPermission).toHaveBeenCalledWith("r2", "p2");
    });
  });

  it("disables permission checkboxes for a system role", async () => {
    const user = userEvent.setup();
    vi.mocked(api.roles.getPermissionMatrix).mockResolvedValue(SAMPLE_MATRIX);

    render(<RolesPage />);
    await screen.findByRole("table");

    const systemRoleItem = screen.getAllByRole("listitem").find((item) => item.textContent?.includes("member"))!;
    await user.click(within(systemRoleItem).getByRole("button", { name: "Edit permissions" }));

    for (const checkbox of within(systemRoleItem).getAllByRole("checkbox")) {
      expect(checkbox).toBeDisabled();
    }
  });
});
