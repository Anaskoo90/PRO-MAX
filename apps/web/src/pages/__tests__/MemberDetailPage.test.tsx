import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
    organizations: { getMember: vi.fn() },
    roles: { listForMember: vi.fn() },
  },
}));

import { api } from "../../api/apiClient";
import { MemberDetailPage } from "../MemberDetailPage";

beforeEach(() => {
  vi.mocked(api.organizations.getMember).mockReset();
  vi.mocked(api.roles.listForMember).mockReset();
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/members/m1"]}>
      <Routes>
        <Route path="/members/:userId" element={<MemberDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("MemberDetailPage", () => {
  it("shows the member's profile and assigned roles", async () => {
    vi.mocked(api.organizations.getMember).mockResolvedValue({
      id: "m1", org_id: "org-1", email: "alice@example.com", display_name: "Alice", status: "active", mfa_enabled: true,
    });
    vi.mocked(api.roles.listForMember).mockResolvedValue([
      { id: "r1", org_id: null, name: "member", description: "", is_system_role: true, parent_role_id: null, permission_ids: [] },
    ]);

    renderPage();

    expect(await screen.findByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByText("member")).toBeInTheDocument();
  });

  it("shows a no-roles message when the member has no roles assigned", async () => {
    vi.mocked(api.organizations.getMember).mockResolvedValue({
      id: "m1", org_id: "org-1", email: "alice@example.com", display_name: "Alice", status: "active", mfa_enabled: false,
    });
    vi.mocked(api.roles.listForMember).mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText(/no roles assigned/i)).toBeInTheDocument();
  });

  it("shows an error message when loading fails", async () => {
    vi.mocked(api.organizations.getMember).mockRejectedValue(new Error("boom"));
    vi.mocked(api.roles.listForMember).mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("Failed to load this member.")).toBeInTheDocument();
  });
});
