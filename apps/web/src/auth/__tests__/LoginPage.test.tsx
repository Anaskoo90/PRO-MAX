import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/apiClient", () => ({
  api: {
    auth: {
      login: vi.fn(),
      verifyMfaChallenge: vi.fn(),
      getMyProfile: vi.fn(),
      logout: vi.fn(),
    },
  },
  setAccessToken: vi.fn(),
}));

import { ApiRequestError } from "@guilddesk/api-client";
import { api } from "../../api/apiClient";
import { AuthProvider } from "../AuthContext";
import { LoginPage } from "../LoginPage";

beforeEach(() => {
  localStorage.clear();
  vi.mocked(api.auth.login).mockReset();
  vi.mocked(api.auth.verifyMfaChallenge).mockReset();
  vi.mocked(api.auth.getMyProfile).mockReset();
});

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>Dashboard home</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function fillCredentials(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/^organization$/i), "acme");
  await user.type(screen.getByLabelText(/email/i), "a@b.com");
  await user.type(screen.getByLabelText(/password/i), "secret");
  await user.click(screen.getByRole("button", { name: /sign in/i }));
}

describe("LoginPage", () => {
  it("signs in and reaches the dashboard when no MFA is required", async () => {
    const user = userEvent.setup();
    vi.mocked(api.auth.login).mockResolvedValue({
      kind: "tokens",
      tokens: { access_token: "a", refresh_token: "r", token_type: "Bearer", expires_in_seconds: 900 },
    });
    vi.mocked(api.auth.getMyProfile).mockResolvedValue({
      id: "u1",
      org_id: "o1",
      email: "a@b.com",
      display_name: "A",
      status: "active",
      mfa_enabled: false,
    });

    renderLoginPage();
    await fillCredentials(user);

    expect(await screen.findByText("Dashboard home")).toBeInTheDocument();
    expect(api.auth.login).toHaveBeenCalledWith({ org_slug: "acme", email: "a@b.com", password: "secret" });
  });

  it("shows the MFA challenge step and completes it when a second factor is required", async () => {
    const user = userEvent.setup();
    vi.mocked(api.auth.login).mockResolvedValue({
      kind: "mfa_challenge",
      challenge: { mfa_challenge_user_id: "user-1", available_factors: ["totp"] },
    });
    vi.mocked(api.auth.verifyMfaChallenge).mockResolvedValue({
      access_token: "a",
      refresh_token: "r",
      token_type: "Bearer",
      expires_in_seconds: 900,
    });
    vi.mocked(api.auth.getMyProfile).mockResolvedValue({
      id: "u1",
      org_id: "o1",
      email: "a@b.com",
      display_name: "A",
      status: "active",
      mfa_enabled: true,
    });

    renderLoginPage();
    await fillCredentials(user);

    expect(await screen.findByText(/verify your identity/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/verification code/i), "123456");
    await user.click(screen.getByRole("button", { name: /^verify$/i }));

    expect(await screen.findByText("Dashboard home")).toBeInTheDocument();
    expect(api.auth.verifyMfaChallenge).toHaveBeenCalledWith({ user_id: "user-1", code: "123456" });
  });

  it("shows the backend's error message when login fails", async () => {
    const user = userEvent.setup();
    vi.mocked(api.auth.login).mockRejectedValue(
      new ApiRequestError(401, {
        code: "UNAUTHORIZED",
        message: "Invalid email or password",
        correlation_id: null,
        details: [],
      }),
    );

    renderLoginPage();
    await fillCredentials(user);

    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument();
  });
});
