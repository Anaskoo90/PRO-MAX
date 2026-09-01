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
  api: { tickets: { search: vi.fn() } },
}));

import { api } from "../../api/apiClient";
import { TicketsPage } from "../TicketsPage";

const SAMPLE_TICKET = {
  id: "t1",
  ticket_number: 1,
  title: "Need help",
  status: "open",
  discord_channel_id: "c1",
  opener_discord_user_id: "1",
  claimed_by_discord_user_id: null,
  created_at: "2026-01-01T00:00:00Z",
  closed_at: null,
};

beforeEach(() => {
  vi.mocked(api.tickets.search).mockReset();
});

describe("TicketsPage", () => {
  it("renders tickets returned from the search API", async () => {
    vi.mocked(api.tickets.search).mockResolvedValue({
      data: [SAMPLE_TICKET],
      page: 1,
      page_size: 20,
      total: 1,
      total_pages: 1,
    });

    render(<TicketsPage />);

    expect(await screen.findByText("Need help")).toBeInTheDocument();
    expect(api.tickets.search).toHaveBeenCalledWith("org-1", {
      page: 1,
      page_size: 20,
      status: undefined,
      sort: "-created_at",
    });
  });

  it("shows an empty state when there are no matching tickets", async () => {
    vi.mocked(api.tickets.search).mockResolvedValue({ data: [], page: 1, page_size: 20, total: 0, total_pages: 0 });

    render(<TicketsPage />);

    expect(await screen.findByText(/no tickets match/i)).toBeInTheDocument();
  });

  it("re-fetches with the new status filter and resets back to page 1", async () => {
    const user = userEvent.setup();
    vi.mocked(api.tickets.search).mockResolvedValue({
      data: [SAMPLE_TICKET],
      page: 1,
      page_size: 20,
      total: 1,
      total_pages: 1,
    });

    render(<TicketsPage />);
    await screen.findByText("Need help");

    await user.selectOptions(screen.getByLabelText(/status/i), "open");

    await waitFor(() => {
      expect(api.tickets.search).toHaveBeenLastCalledWith("org-1", {
        page: 1,
        page_size: 20,
        status: "open",
        sort: "-created_at",
      });
    });
  });

  it("disables Previous on the first page and fetches page 2 on Next", async () => {
    const user = userEvent.setup();
    vi.mocked(api.tickets.search).mockResolvedValue({
      data: [SAMPLE_TICKET],
      page: 1,
      page_size: 20,
      total: 40,
      total_pages: 2,
    });

    render(<TicketsPage />);
    await screen.findByText("Need help");

    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => {
      expect(api.tickets.search).toHaveBeenLastCalledWith("org-1", {
        page: 2,
        page_size: 20,
        status: undefined,
        sort: "-created_at",
      });
    });
  });
});
