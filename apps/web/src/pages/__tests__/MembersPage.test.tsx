import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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
  api: { organizations: { searchMembers: vi.fn() } },
}));

import { api } from "../../api/apiClient";
import { MembersPage } from "../MembersPage";

const SAMPLE_MEMBER = {
  id: "m1", org_id: "org-1", email: "alice@example.com", display_name: "Alice", status: "active", mfa_enabled: false,
};

beforeEach(() => {
  vi.mocked(api.organizations.searchMembers).mockReset();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <MembersPage />
    </MemoryRouter>,
  );
}

describe("MembersPage", () => {
  it("renders members returned from searchMembers", async () => {
    vi.mocked(api.organizations.searchMembers).mockResolvedValue({
      data: [SAMPLE_MEMBER], page: 1, page_size: 20, total: 1, total_pages: 1,
    });

    renderPage();

    expect(await screen.findByText("Alice")).toBeInTheDocument();
  });

  it("shows an empty state when no members match", async () => {
    vi.mocked(api.organizations.searchMembers).mockResolvedValue({
      data: [], page: 1, page_size: 20, total: 0, total_pages: 0,
    });

    renderPage();

    expect(await screen.findByText(/no members match/i)).toBeInTheDocument();
  });

  it("debounces the search box and re-fetches with the query", async () => {
    const user = userEvent.setup();
    vi.mocked(api.organizations.searchMembers).mockResolvedValue({
      data: [SAMPLE_MEMBER], page: 1, page_size: 20, total: 1, total_pages: 1,
    });

    renderPage();
    await screen.findByText("Alice");

    await user.type(screen.getByLabelText(/search/i), "alice");

    await waitFor(
      () => {
        expect(api.organizations.searchMembers).toHaveBeenLastCalledWith("org-1", {
          page: 1, page_size: 20, q: "alice", status: undefined,
        });
      },
      { timeout: 2000 },
    );
  });

  it("filters by status", async () => {
    const user = userEvent.setup();
    vi.mocked(api.organizations.searchMembers).mockResolvedValue({
      data: [SAMPLE_MEMBER], page: 1, page_size: 20, total: 1, total_pages: 1,
    });

    renderPage();
    await screen.findByText("Alice");

    await user.selectOptions(screen.getByLabelText(/status/i), "active");

    await waitFor(() => {
      expect(api.organizations.searchMembers).toHaveBeenLastCalledWith("org-1", {
        page: 1, page_size: 20, q: undefined, status: "active",
      });
    });
  });
});
