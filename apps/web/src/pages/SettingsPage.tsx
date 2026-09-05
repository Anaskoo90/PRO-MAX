import { useEffect, useState, type FormEvent } from "react";
import { ApiRequestError, type Organization, type Session, type TotpEnrollment } from "@guilddesk/api-client";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/apiClient";
import { EmptyState, ErrorState, LoadingState } from "../components/AsyncState";
import styles from "./SettingsPage.module.css";

type SectionId = "general" | "security";

const SECTIONS: { id: SectionId; label: string }[] = [
  { id: "general", label: "General" },
  { id: "security", label: "Security" },
];

export function SettingsPage() {
  const { user } = useAuth();
  const orgId = user?.org_id;
  const [activeSection, setActiveSection] = useState<SectionId>("general");
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // --- Security tab: MFA -------------------------------------------------
  const [mfaEnabled, setMfaEnabled] = useState<boolean | null>(null);
  const [isLoadingMfaStatus, setIsLoadingMfaStatus] = useState(true);
  const [mfaStatusError, setMfaStatusError] = useState<string | null>(null);
  const [enrollment, setEnrollment] = useState<TotpEnrollment | null>(null);
  const [enrollmentCode, setEnrollmentCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [mfaActionError, setMfaActionError] = useState<string | null>(null);
  const [isMfaActionPending, setIsMfaActionPending] = useState(false);

  // --- Security tab: sessions ---------------------------------------------
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [revokingSessionId, setRevokingSessionId] = useState<string | null>(null);

  useEffect(() => {
    if (!orgId) return;
    let cancelled = false;
    setIsLoading(true);
    setLoadError(null);

    api.organizations
      .get(orgId)
      .then((org) => {
        if (cancelled) return;
        setOrganization(org);
        setName(org.name);
        setSlug(org.slug);
        setDescription(org.description ?? "");
        setLogoUrl(org.logo_url ?? "");
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(err instanceof ApiRequestError ? err.message : "Failed to load organization.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [orgId]);

  function loadMfaStatus(): void {
    setIsLoadingMfaStatus(true);
    setMfaStatusError(null);
    api.auth
      .getMyProfile()
      .then((profile) => setMfaEnabled(profile.mfa_enabled))
      .catch((err: unknown) => {
        setMfaStatusError(err instanceof ApiRequestError ? err.message : "Failed to load MFA status.");
      })
      .finally(() => setIsLoadingMfaStatus(false));
  }

  function loadSessions(): void {
    setIsLoadingSessions(true);
    setSessionsError(null);
    api.auth
      .listSessions()
      .then((result) => setSessions(result))
      .catch((err: unknown) => {
        setSessionsError(err instanceof ApiRequestError ? err.message : "Failed to load active sessions.");
      })
      .finally(() => setIsLoadingSessions(false));
  }

  useEffect(() => {
    if (activeSection !== "security") return;
    loadMfaStatus();
    loadSessions();
    // Re-run whenever the Security tab is opened, so returning to it after
    // enabling/disabling MFA elsewhere (or in another tab) shows current state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSection]);

  async function handleStartEnrollment(): Promise<void> {
    setMfaActionError(null);
    setIsMfaActionPending(true);
    try {
      const result = await api.auth.startTotpEnrollment();
      setEnrollment(result);
    } catch (err) {
      setMfaActionError(err instanceof ApiRequestError ? err.message : "Couldn't start MFA enrollment.");
    } finally {
      setIsMfaActionPending(false);
    }
  }

  async function handleConfirmEnrollment(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!enrollment || !enrollmentCode.trim()) return;
    setMfaActionError(null);
    setIsMfaActionPending(true);
    try {
      const codes = await api.auth.confirmTotpEnrollment(enrollment.factor_id, enrollmentCode.trim());
      setRecoveryCodes(codes.recovery_codes);
      setEnrollment(null);
      setEnrollmentCode("");
      setMfaEnabled(true);
    } catch (err) {
      setMfaActionError(err instanceof ApiRequestError ? err.message : "That code didn't work — try again.");
    } finally {
      setIsMfaActionPending(false);
    }
  }

  async function handleDisableMfa(): Promise<void> {
    if (!window.confirm("Turn off two-factor authentication for your account?")) return;
    setMfaActionError(null);
    setIsMfaActionPending(true);
    try {
      await api.auth.disableMfa();
      setMfaEnabled(false);
      setRecoveryCodes(null);
    } catch (err) {
      setMfaActionError(err instanceof ApiRequestError ? err.message : "Couldn't disable MFA.");
    } finally {
      setIsMfaActionPending(false);
    }
  }

  async function handleRevokeSession(session: Session): Promise<void> {
    if (!window.confirm("Sign out this session? The device using it will be signed out immediately.")) return;
    setSessionsError(null);
    setRevokingSessionId(session.id);
    try {
      await api.auth.revokeSession(session.id);
      setSessions((prev) => (prev ? prev.filter((s) => s.id !== session.id) : prev));
    } catch (err) {
      setSessionsError(err instanceof ApiRequestError ? err.message : "Couldn't revoke that session.");
    } finally {
      setRevokingSessionId(null);
    }
  }

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!orgId) return;
    setSaveError(null);
    setSaveSuccess(false);
    setIsSaving(true);
    try {
      const updated = await api.organizations.update(orgId, {
        name: name.trim(),
        slug: slug.trim(),
        description,
        logo_url: logoUrl,
      });
      setOrganization(updated);
      setSaveSuccess(true);
    } catch (err) {
      setSaveError(err instanceof ApiRequestError ? err.message : "Failed to save changes.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div>
      <h1>Organization Settings</h1>
      <div className={styles.layout}>
        <nav className={styles.sectionNav}>
          {SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              className={activeSection === section.id ? styles.sectionActive : styles.section}
              onClick={() => setActiveSection(section.id)}
            >
              {section.label}
            </button>
          ))}
        </nav>
        <div className={styles.content}>
          {loadError && <ErrorState message={loadError} />}

          {activeSection === "general" &&
            (isLoading ? (
              <LoadingState label="Loading organization…" />
            ) : (
              organization && (
                <form className={styles.form} onSubmit={handleSubmit}>
                  <label className={styles.field}>
                    Name
                    <input value={name} onChange={(event) => setName(event.target.value)} required />
                  </label>
                  <label className={styles.field}>
                    Slug
                    <input value={slug} onChange={(event) => setSlug(event.target.value)} required />
                  </label>
                  <p className={styles.hint}>Used to sign in — changing it changes what members type at login.</p>
                  <label className={styles.field}>
                    Description
                    <textarea
                      value={description}
                      onChange={(event) => setDescription(event.target.value)}
                      rows={3}
                    />
                  </label>
                  <label className={styles.field}>
                    Logo URL
                    <input
                      type="url"
                      value={logoUrl}
                      onChange={(event) => setLogoUrl(event.target.value)}
                      placeholder="https://…"
                    />
                  </label>
                  <p className={styles.hint}>
                    GuildDesk links to an image you host elsewhere — uploading a logo file directly isn't supported yet.
                  </p>
                  <p className={styles.readOnlyRow}>
                    Status: <strong>{organization.status}</strong>
                  </p>
                  {saveError && <ErrorState message={saveError} />}
                  {saveSuccess && <p className={styles.success}>Saved.</p>}
                  <button type="submit" disabled={isSaving}>
                    {isSaving ? "Saving…" : "Save changes"}
                  </button>
                </form>
              )
            ))}

          {activeSection === "security" && (
            <div className={styles.securityLayout}>
              <section className={styles.securitySection}>
                <h2>Two-factor authentication</h2>
                {mfaStatusError ? (
                  <ErrorState message={mfaStatusError} onRetry={loadMfaStatus} />
                ) : isLoadingMfaStatus ? (
                  <LoadingState label="Loading MFA status…" />
                ) : recoveryCodes ? (
                  <div>
                    <p className={styles.success}>Two-factor authentication is now enabled.</p>
                    <p>Save these recovery codes somewhere safe — each one can be used once if you lose access to your authenticator app.</p>
                    <ul className={styles.recoveryCodeList}>
                      {recoveryCodes.map((code) => (
                        <li key={code}>{code}</li>
                      ))}
                    </ul>
                    <button type="button" onClick={() => setRecoveryCodes(null)}>
                      Done
                    </button>
                  </div>
                ) : enrollment ? (
                  <form className={styles.form} onSubmit={(event) => void handleConfirmEnrollment(event)}>
                    <p>Scan this into your authenticator app, or enter the code manually:</p>
                    <p className={styles.secretCode}>{enrollment.secret}</p>
                    <label className={styles.field}>
                      Enter the 6-digit code from your app
                      <input
                        value={enrollmentCode}
                        onChange={(event) => setEnrollmentCode(event.target.value)}
                        inputMode="numeric"
                        autoFocus
                        required
                      />
                    </label>
                    {mfaActionError && <ErrorState message={mfaActionError} />}
                    <div className={styles.inlineActions}>
                      <button type="submit" disabled={isMfaActionPending || !enrollmentCode.trim()}>
                        {isMfaActionPending ? "Confirming…" : "Confirm"}
                      </button>
                      <button type="button" onClick={() => setEnrollment(null)} disabled={isMfaActionPending}>
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : mfaEnabled ? (
                  <div>
                    <p>Two-factor authentication is currently <strong>enabled</strong> for your account.</p>
                    {mfaActionError && <ErrorState message={mfaActionError} />}
                    <button type="button" onClick={() => void handleDisableMfa()} disabled={isMfaActionPending}>
                      {isMfaActionPending ? "Disabling…" : "Disable two-factor authentication"}
                    </button>
                  </div>
                ) : (
                  <div>
                    <p>Two-factor authentication is currently <strong>disabled</strong> for your account.</p>
                    {mfaActionError && <ErrorState message={mfaActionError} />}
                    <button type="button" onClick={() => void handleStartEnrollment()} disabled={isMfaActionPending}>
                      {isMfaActionPending ? "Starting…" : "Enable two-factor authentication"}
                    </button>
                  </div>
                )}
              </section>

              <section className={styles.securitySection}>
                <h2>Active sessions</h2>
                {sessionsError ? (
                  <ErrorState message={sessionsError} onRetry={loadSessions} />
                ) : isLoadingSessions ? (
                  <LoadingState label="Loading active sessions…" />
                ) : !sessions || sessions.length === 0 ? (
                  <EmptyState message="No active sessions." />
                ) : (
                  <ul className={styles.sessionList}>
                    {sessions.map((session) => (
                      <li key={session.id} className={styles.sessionItem}>
                        <div>
                          <p className={styles.sessionDevice}>{session.device_label || "Unknown device"}</p>
                          <p className={styles.sessionMeta}>
                            {session.ip_address} · signed in {new Date(session.created_at).toLocaleString()}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => void handleRevokeSession(session)}
                          disabled={revokingSessionId === session.id}
                        >
                          {revokingSessionId === session.id ? "Revoking…" : "Revoke"}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <p className={styles.hint}>
                  Sessions aren't currently flagged as "this device" — if you're unsure which one you're using, sign
                  out from the General tab instead of guessing here.
                </p>
              </section>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
