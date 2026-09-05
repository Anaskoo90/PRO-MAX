import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: { id: "u1", org_id: "org-1", email: "a@b.com", display_name: "Ada", status: "active", mfa_enabled: false },
    login: vi.fn(),
    completeMfaChallenge: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock("../../api/apiClient", () => ({
  api: {
    tickets: { search: vi.fn() },
    organizations: { searchMembers: vi.fn() },
  },
}));

import { api } from "../../api/apiClient";
import { DashboardHomePage } from "../DashboardHomePage";

function renderPage() {
  return render(
    <MemoryRouter>
      <DashboardHomePage />
    </MemoryRouter>,
  );
}

const SAMPLE_TICKET = {
  id: "t1", ticket_number: 42, title: "Can't log in", status: "open", discord_channel_id: "c1",
  opener_discord_user_id: "1", claimed_by_discord_user_id: null, created_at: "2026-01-01T00:00:00Z",
  closed_at: null,
};

beforeEach(() => {
  vi.mocked(api.tickets.search).mockReset();
  vi.mocked(api.organizations.searchMembers).mockReset();
});

describe("DashboardHomePage", () => {
  it("greets the signed-in user by name", async () => {
    vi.mocked(api.tickets.search).mockResolvedValue({ data: [], page: 1, page_size: 5, total: 0, total_pages: 0 });
    vi.mocked(api.organizations.searchMembers).mockResolvedValue({
      data: [], page: 1, page_size: 1, total: 0, total_pages: 0,
    });

    renderPage();

    expect(await screen.findByRole("heading", { name: "Welcome, Ada" })).toBeInTheDocument();
  });

  it("shows open/claimed ticket counts and member count from the existing search endpoints", async () => {
    vi.mocked(api.tickets.search).mockImplementation((_orgId, params) => {
      if (params?.status === "open") {
        return Promise.resolve({ data: [], page: 1, page_size: 1, total: 3, total_pages: 3 });
      }
      if (params?.status === "claimed") {
        return Promise.resolve({ data: [], page: 1, page_size: 1, total: 2, total_pages: 2 });
      }
      return Promise.resolve({ data: [SAMPLE_TICKET], page: 1, page_size: 5, total: 5, total_pages: 1 });
    });
    vi.mocked(api.organizations.searchMembers).mockResolvedValue({
      data: [], page: 1, page_size: 1, total: 12, total_pages: 12,
    });

    renderPage();

    expect(await screen.findByText("3")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Open tickets")).toBeInTheDocument();
    expect(screen.getByText("Claimed tickets")).toBeInTheDocument();
    expect(screen.getByText("Members")).toBeInTheDocument();
  });

  it("lists recent tickets returned by the sorted ticket search", async () => {
    vi.mocked(api.tickets.search).mockImplementation((_orgId, params) => {
      if (params?.sort === "-created_at") {
        return Promise.resolve({ data: [SAMPLE_TICKET], page: 1, page_size: 5, total: 1, total_pages: 1 });
      }
      return Promise.resolve({ data: [], page: 1, page_size: 1, total: 0, total_pages: 0 });
    });
    vi.mocked(api.organizations.searchMembers).mockResolvedValue({
      data: [], page: 1, page_size: 1, total: 0, total_pages: 0,
    });

    renderPage();

    expect(await screen.findByText("#42 Can't log in")).toBeInTheDocument();
  });

  it("shows an empty hint when there are no recent tickets", async () => {
    vi.mocked(api.tickets.search).mockResolvedValue({ data: [], page: 1, page_size: 5, total: 0, total_pages: 0 });
    vi.mocked(api.organizations.searchMembers).mockResolvedValue({
      data: [], page: 1, page_size: 1, total: 0, total_pages: 0,
    });

    renderPage();

    expect(await screen.findByText("No tickets yet.")).toBeInTheDocument();
  });

  it("shows an error state when loading the dashboard data fails", async () => {
    vi.mocked(api.tickets.search).mockRejectedValue(new Error("boom"));
    vi.mocked(api.organizations.searchMembers).mockResolvedValue({
      data: [], page: 1, page_size: 1, total: 0, total_pages: 0,
    });

    renderPage();

    expect(await screen.findByText("Failed to load dashboard data.")).toBeInTheDocument();
  });
});
