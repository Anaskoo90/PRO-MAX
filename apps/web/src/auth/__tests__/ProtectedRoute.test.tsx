import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/apiClient", () => ({
  api: {
    auth: {
      getMyProfile: vi.fn(),
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

  it("redirects to /login when the stored access token is no longer valid", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ accessToken: "stale", refreshToken: "r" }));
    vi.mocked(api.auth.getMyProfile).mockRejectedValue(new Error("401"));

    renderProtected();

    expect(await screen.findByText("Login page")).toBeInTheDocument();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
