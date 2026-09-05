import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/apiClient", () => ({
  api: {
    auth: {
      getMyProfile: vi.fn(),
      refresh: vi.fn(),
    },
  },
  setAccessToken: vi.fn(),
}));

import { api } from "../../api/apiClient";
import { AuthProvider } from "../AuthContext";
import { ProtectedRoute } from "../ProtectedRoute";

const STORAGE_KEY = "guilddesk.auth.session";

beforeEach(() => {
  localStorage.clear();
  vi.mocked(api.auth.getMyProfile).mockReset();
  vi.mocked(api.auth.refresh).mockReset();
});

function renderProtected() {
  return render(
    <MemoryRouter initialEntries={["/protected"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>Login page</div>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/protected" element={<div>Secret content</div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  it("redirects to /login when there is no stored session", async () => {
    renderProtected();

    expect(await screen.findByText("Login page")).toBeInTheDocument();
  });

  it("renders the protected content when the stored session is still valid", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ accessToken: "a", refreshToken: "r" }));
    vi.mocked(api.auth.getMyProfile).mockResolvedValue({
      id: "u1",
      org_id: "o1",
      email: "a@b.com",
      display_name: "A",
      status: "active",
      mfa_enabled: false,
    });

    renderProtected();

    expect(await screen.findByText("Secret content")).toBeInTheDocument();
  });

  it("recovers the session via refresh when the access token is expired but the refresh token is still valid", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ accessToken: "stale", refreshToken: "still-good" }));
    vi.mocked(api.auth.getMyProfile)
      .mockRejectedValueOnce(new Error("401"))
      .mockResolvedValueOnce({
        id: "u1",
        org_id: "o1",
        email: "a@b.com",
        display_name: "A",
        status: "active",
        mfa_enabled: false,
      });
    vi.mocked(api.auth.refresh).mockResolvedValue({
      access_token: "fresh",
      refresh_token: "fresh-refresh",
      token_type: "Bearer",
      expires_in_seconds: 900,
    });

    renderProtected();

    // The session must be recovered, not discarded: this is the regression
    // test for the bootstrap bug where a valid refresh token was never
    // tried before signing the user out on page reload.
    expect(await screen.findByText("Secret content")).toBeInTheDocument();
    expect(api.auth.refresh).toHaveBeenCalledWith("still-good");
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}")).toEqual({
      accessToken: "fresh",
      refreshToken: "fresh-refresh",
    });
  });

  it("redirects to /login and clears storage when both the access token and the refresh token are no longer valid", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ accessToken: "stale", refreshToken: "also-stale" }));
    vi.mocked(api.auth.getMyProfile).mockRejectedValue(new Error("401"));
    vi.mocked(api.auth.refresh).mockRejectedValue(new Error("refresh token expired"));

    renderProtected();

    expect(await screen.findByText("Login page")).toBeInTheDocument();
    expect(api.auth.refresh).toHaveBeenCalledWith("also-stale");
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
