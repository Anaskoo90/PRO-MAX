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
    organizations: { get: vi.fn(), update: vi.fn(), updateSettings: vi.fn() },
    auth: {
      getMyProfile: vi.fn(),
      startTotpEnrollment: vi.fn(),
      confirmTotpEnrollment: vi.fn(),
      disableMfa: vi.fn(),
      listSessions: vi.fn(),
      revokeSession: vi.fn(),
    },
  },
}));

import { api } from "../../api/apiClient";
import { SettingsPage } from "../SettingsPage";

const SAMPLE_ORG = {
  id: "org-1", name: "Acme Guild", slug: "acme-guild", owner_user_id: "u1", status: "active", settings: {},
  description: null, logo_url: null,
};

const SAMPLE_SESSION = {
  id: "s1", device_label: "Chrome on macOS", ip_address: "203.0.113.4",
  created_at: "2026-01-01T00:00:00Z", expires_at: "2026-01-08T00:00:00Z", is_current: false,
};

beforeEach(() => {
  vi.mocked(api.organizations.get).mockReset();
  vi.mocked(api.organizations.update).mockReset();
  vi.mocked(api.auth.getMyProfile).mockReset();
  vi.mocked(api.auth.startTotpEnrollment).mockReset();
  vi.mocked(api.auth.confirmTotpEnrollment).mockReset();
  vi.mocked(api.auth.disableMfa).mockReset();
  vi.mocked(api.auth.listSessions).mockReset();
  vi.mocked(api.auth.revokeSession).mockReset();
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

  it("shows MFA as disabled and lets the user start enrollment", async () => {
    const user = userEvent.setup();
    vi.mocked(api.organizations.get).mockResolvedValue(SAMPLE_ORG);
    vi.mocked(api.auth.getMyProfile).mockResolvedValue({
      id: "u1", org_id: "org-1", email: "a@b.com", display_name: "A", status: "active", mfa_enabled: false,
    });
    vi.mocked(api.auth.listSessions).mockResolvedValue([SAMPLE_SESSION]);
    vi.mocked(api.auth.startTotpEnrollment).mockResolvedValue({
      factor_id: "f1", secret: "JBSWY3DPEHPK3PXP", provisioning_uri: "otpauth://totp/GuildDesk",
    });

    render(<SettingsPage />);
    await screen.findByDisplayValue("Acme Guild");
    await user.click(screen.getByRole("button", { name: "Security" }));

    expect(await screen.findByText("disabled")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enable two-factor authentication" }));

    expect(await screen.findByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
  });

  it("confirms TOTP enrollment with a code and shows recovery codes", async () => {
    const user = userEvent.setup();
    vi.mocked(api.organizations.get).mockResolvedValue(SAMPLE_ORG);
    vi.mocked(api.auth.getMyProfile).mockResolvedValue({
      id: "u1", org_id: "org-1", email: "a@b.com", display_name: "A", status: "active", mfa_enabled: false,
    });
    vi.mocked(api.auth.listSessions).mockResolvedValue([]);
    vi.mocked(api.auth.startTotpEnrollment).mockResolvedValue({
      factor_id: "f1", secret: "JBSWY3DPEHPK3PXP", provisioning_uri: "otpauth://totp/GuildDesk",
    });
    vi.mocked(api.auth.confirmTotpEnrollment).mockResolvedValue({ recovery_codes: ["AAAA-1111", "BBBB-2222"] });

    render(<SettingsPage />);
    await screen.findByDisplayValue("Acme Guild");
    await user.click(screen.getByRole("button", { name: "Security" }));
    await user.click(await screen.findByRole("button", { name: "Enable two-factor authentication" }));
    await user.type(screen.getByLabelText(/6-digit code/i), "123456");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("AAAA-1111")).toBeInTheDocument();
    expect(api.auth.confirmTotpEnrollment).toHaveBeenCalledWith("f1", "123456");
  });

  it("shows MFA as enabled and lets the user disable it after confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(api.organizations.get).mockResolvedValue(SAMPLE_ORG);
    vi.mocked(api.auth.getMyProfile).mockResolvedValue({
      id: "u1", org_id: "org-1", email: "a@b.com", display_name: "A", status: "active", mfa_enabled: true,
    });
    vi.mocked(api.auth.listSessions).mockResolvedValue([]);
    vi.mocked(api.auth.disableMfa).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<SettingsPage />);
    await screen.findByDisplayValue("Acme Guild");
    await user.click(screen.getByRole("button", { name: "Security" }));

    expect(await screen.findByText("enabled")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Disable two-factor authentication" }));

    await waitFor(() => expect(api.auth.disableMfa).toHaveBeenCalled());
    expect(await screen.findByText("disabled")).toBeInTheDocument();
  });

  it("lists active sessions and revokes one after confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(api.organizations.get).mockResolvedValue(SAMPLE_ORG);
    vi.mocked(api.auth.getMyProfile).mockResolvedValue({
      id: "u1", org_id: "org-1", email: "a@b.com", display_name: "A", status: "active", mfa_enabled: false,
    });
    vi.mocked(api.auth.listSessions).mockResolvedValue([SAMPLE_SESSION]);
    vi.mocked(api.auth.revokeSession).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<SettingsPage />);
    await screen.findByDisplayValue("Acme Guild");
    await user.click(screen.getByRole("button", { name: "Security" }));

    expect(await screen.findByText("Chrome on macOS")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Revoke" }));

    await waitFor(() => expect(api.auth.revokeSession).toHaveBeenCalledWith("s1"));
    expect(screen.queryByText("Chrome on macOS")).not.toBeInTheDocument();
  });

  it("shows an empty state when there are no active sessions", async () => {
    const user = userEvent.setup();
    vi.mocked(api.organizations.get).mockResolvedValue(SAMPLE_ORG);
    vi.mocked(api.auth.getMyProfile).mockResolvedValue({
      id: "u1", org_id: "org-1", email: "a@b.com", display_name: "A", status: "active", mfa_enabled: false,
    });
    vi.mocked(api.auth.listSessions).mockResolvedValue([]);

    render(<SettingsPage />);
    await screen.findByDisplayValue("Acme Guild");
    await user.click(screen.getByRole("button", { name: "Security" }));

    expect(await screen.findByText("No active sessions.")).toBeInTheDocument();
  });
});
