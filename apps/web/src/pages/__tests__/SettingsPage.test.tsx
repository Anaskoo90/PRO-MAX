import { render, screen } from "@testing-library/react";
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
    organizations: { get: vi.fn(), update: vi.fn(), updateSettings: vi.fn() },
  },
}));

import { api } from "../../api/apiClient";
import { SettingsPage } from "../SettingsPage";

const SAMPLE_ORG = {
  id: "org-1", name: "Acme Guild", slug: "acme-guild", owner_user_id: "u1", status: "active", settings: {},
  description: null, logo_url: null,
};

beforeEach(() => {
  vi.mocked(api.organizations.get).mockReset();
  vi.mocked(api.organizations.update).mockReset();
});

describe("SettingsPage", () => {
  it("populates the General form with the organization's current profile", async () => {
    vi.mocked(api.organizations.get).mockResolvedValue(SAMPLE_ORG);

    render(<SettingsPage />);

    expect(await screen.findByDisplayValue("Acme Guild")).toBeInTheDocument();
    expect(screen.getByDisplayValue("acme-guild")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("saves edited name, slug, description, and logo URL", async () => {
    const user = userEvent.setup();
    vi.mocked(api.organizations.get).mockResolvedValue(SAMPLE_ORG);
    vi.mocked(api.organizations.update).mockResolvedValue({
      ...SAMPLE_ORG, name: "Acme Corp", slug: "acme-corp", description: "Widgets", logo_url: "https://x/logo.png",
    });

    render(<SettingsPage />);
    await screen.findByDisplayValue("Acme Guild");

    await user.clear(screen.getByLabelText(/^name$/i));
    await user.type(screen.getByLabelText(/^name$/i), "Acme Corp");
    await user.clear(screen.getByLabelText(/^slug$/i));
    await user.type(screen.getByLabelText(/^slug$/i), "acme-corp");
    await user.type(screen.getByLabelText(/description/i), "Widgets");
    await user.type(screen.getByLabelText(/logo url/i), "https://x/logo.png");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(api.organizations.update).toHaveBeenCalledWith("org-1", {
      name: "Acme Corp", slug: "acme-corp", description: "Widgets", logo_url: "https://x/logo.png",
    });
  });

  it("shows an error message when saving fails", async () => {
    const user = userEvent.setup();
    vi.mocked(api.organizations.get).mockResolvedValue(SAMPLE_ORG);
    vi.mocked(api.organizations.update).mockRejectedValue(new Error("boom"));

    render(<SettingsPage />);
    await screen.findByDisplayValue("Acme Guild");

    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText("Failed to save changes.")).toBeInTheDocument();
  });

  it("shows a coming-soon placeholder for the Security section", async () => {
    const user = userEvent.setup();
    vi.mocked(api.organizations.get).mockResolvedValue(SAMPLE_ORG);

    render(<SettingsPage />);
    await screen.findByDisplayValue("Acme Guild");

    await user.click(screen.getByRole("button", { name: "Security" }));

    expect(await screen.findByText(/coming soon/i)).toBeInTheDocument();
  });
});
