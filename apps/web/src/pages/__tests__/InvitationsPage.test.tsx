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
    invitations: { listPending: vi.fn(), create: vi.fn(), revoke: vi.fn() },
    roles: { listForOrg: vi.fn() },
  },
}));

import { api } from "../../api/apiClient";
import { InvitationsPage } from "../InvitationsPage";

const SAMPLE_INVITATION = {
  id: "i1", org_id: "org-1", email: "new.hire@example.com", role_id: "r1", invited_by_user_id: "u1",
  status: "pending", created_at: "2026-01-01T00:00:00Z", expires_at: "2026-01-08T00:00:00Z",
};

const SAMPLE_ROLES = [
  { id: "r1", org_id: "org-1", name: "Support", description: "", is_system_role: false, parent_role_id: null, permission_ids: [] },
];

beforeEach(() => {
  vi.mocked(api.invitations.listPending).mockReset();
  vi.mocked(api.invitations.create).mockReset();
  vi.mocked(api.invitations.revoke).mockReset();
  vi.mocked(api.roles.listForOrg).mockReset();
  vi.mocked(api.roles.listForOrg).mockResolvedValue(SAMPLE_ROLES);
});

describe("InvitationsPage", () => {
  it("renders pending invitations with their role name resolved", async () => {
    vi.mocked(api.invitations.listPending).mockResolvedValue([SAMPLE_INVITATION]);

    render(<InvitationsPage />);

    const table = await screen.findByRole("table");
    expect(within(table).getByText("new.hire@example.com")).toBeInTheDocument();
    expect(within(table).getByText("Support")).toBeInTheDocument();
  });

  it("shows an empty state when there are no pending invitations", async () => {
    vi.mocked(api.invitations.listPending).mockResolvedValue([]);

    render(<InvitationsPage />);

    expect(await screen.findByText("No pending invitations.")).toBeInTheDocument();
  });

  it("shows an error state with retry when loading invitations fails", async () => {
    vi.mocked(api.invitations.listPending).mockRejectedValueOnce(new Error("boom"));
    vi.mocked(api.invitations.listPending).mockResolvedValueOnce([SAMPLE_INVITATION]);

    render(<InvitationsPage />);

    expect(await screen.findByText("Failed to load invitations.")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("new.hire@example.com")).toBeInTheDocument();
  });

  it("creates a new invitation and reloads the list", async () => {
    const user = userEvent.setup();
    vi.mocked(api.invitations.listPending).mockResolvedValueOnce([]).mockResolvedValueOnce([SAMPLE_INVITATION]);
    vi.mocked(api.invitations.create).mockResolvedValue(SAMPLE_INVITATION);

    render(<InvitationsPage />);
    await screen.findByText("No pending invitations.");

    await user.type(screen.getByLabelText("Email to invite"), "new.hire@example.com");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));

    await waitFor(() => {
      expect(api.invitations.create).toHaveBeenCalledWith("org-1", "new.hire@example.com", "r1");
    });
    expect(await screen.findByText("new.hire@example.com")).toBeInTheDocument();
  });

  it("shows an error when creating an invitation fails", async () => {
    const user = userEvent.setup();
    vi.mocked(api.invitations.listPending).mockResolvedValue([]);
    vi.mocked(api.invitations.create).mockRejectedValue(new Error("boom"));

    render(<InvitationsPage />);
    await screen.findByText("No pending invitations.");

    await user.type(screen.getByLabelText("Email to invite"), "new.hire@example.com");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));

    expect(await screen.findByText("Couldn't send that invitation.")).toBeInTheDocument();
  });

  it("revokes an invitation after confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(api.invitations.listPending).mockResolvedValue([SAMPLE_INVITATION]);
    vi.mocked(api.invitations.revoke).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<InvitationsPage />);
    await screen.findByText("new.hire@example.com");

    await user.click(screen.getByRole("button", { name: "Revoke" }));

    await waitFor(() => {
      expect(api.invitations.revoke).toHaveBeenCalledWith("org-1", "i1");
    });
    expect(screen.queryByText("new.hire@example.com")).not.toBeInTheDocument();
  });

  it("does not revoke when the confirmation is declined", async () => {
    const user = userEvent.setup();
    vi.mocked(api.invitations.listPending).mockResolvedValue([SAMPLE_INVITATION]);
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<InvitationsPage />);
    await screen.findByText("new.hire@example.com");

    await user.click(screen.getByRole("button", { name: "Revoke" }));

    expect(api.invitations.revoke).not.toHaveBeenCalled();
  });
});
