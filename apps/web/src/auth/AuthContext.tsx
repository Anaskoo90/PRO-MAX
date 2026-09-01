import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { UserProfile } from "@guilddesk/api-client";
import { api, setAccessToken } from "../api/apiClient";

const STORAGE_KEY = "guilddesk.auth.session";

interface StoredSession {
  accessToken: string;
  refreshToken: string;
}

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthState {
  status: AuthStatus;
  user: UserProfile | null;
}

export interface LoginOutcome {
  requiresMfa: boolean;
  mfaChallengeUserId?: string;
}

interface AuthContextValue extends AuthState {
  login(orgSlug: string, email: string, password: string): Promise<LoginOutcome>;
  completeMfaChallenge(userId: string, code: string): Promise<void>;
  logout(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredSession(): StoredSession | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredSession;
  } catch {
    return null;
  }
}

function writeStoredSession(session: StoredSession | null): void {
  if (session) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });
  const [refreshToken, setRefreshToken] = useState<string | null>(null);

  const establishSession = useCallback(async (accessToken: string, newRefreshToken: string): Promise<void> => {
    setAccessToken(accessToken);
    setRefreshToken(newRefreshToken);
    writeStoredSession({ accessToken, refreshToken: newRefreshToken });
    const user = await api.auth.getMyProfile();
    setState({ status: "authenticated", user });
  }, []);

  useEffect(() => {
    const stored = readStoredSession();
    if (!stored) {
      setState({ status: "anonymous", user: null });
      return;
    }
    setAccessToken(stored.accessToken);
    setRefreshToken(stored.refreshToken);
    api.auth
      .getMyProfile()
      .then((user) => setState({ status: "authenticated", user }))
      .catch(() => {
        // The stored access token is no longer valid (expired, revoked) — a
        // refresh-on-startup flow is a later-phase concern, not part of
        // Phase 2A's foundation, so this just falls back to signed-out.
        setAccessToken(null);
        writeStoredSession(null);
        setState({ status: "anonymous", user: null });
      });
  }, []);

  const login = useCallback(
    async (orgSlug: string, email: string, password: string): Promise<LoginOutcome> => {
      const result = await api.auth.login({ org_slug: orgSlug, email, password });
      if (result.kind === "mfa_challenge") {
        return { requiresMfa: true, mfaChallengeUserId: result.challenge.mfa_challenge_user_id };
      }
      await establishSession(result.tokens.access_token, result.tokens.refresh_token);
      return { requiresMfa: false };
    },
    [establishSession],
  );

  const completeMfaChallenge = useCallback(
    async (userId: string, code: string): Promise<void> => {
      const tokens = await api.auth.verifyMfaChallenge({ user_id: userId, code });
      await establishSession(tokens.access_token, tokens.refresh_token);
    },
    [establishSession],
  );

  const logout = useCallback(async (): Promise<void> => {
    if (refreshToken) {
      try {
        await api.auth.logout(refreshToken);
      } catch {
        // A stale/already-revoked refresh token is fine to ignore here —
        // the goal of logout is a signed-out local state either way.
      }
    }
    setAccessToken(null);
    setRefreshToken(null);
    writeStoredSession(null);
    setState({ status: "anonymous", user: null });
  }, [refreshToken]);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, login, completeMfaChallenge, logout }),
    [state, login, completeMfaChallenge, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
