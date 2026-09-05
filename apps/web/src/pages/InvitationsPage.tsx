import { useEffect, useState, type FormEvent } from "react";
import { ApiRequestError, type Invitation, type Role } from "@guilddesk/api-client";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/apiClient";
import { EmptyState, ErrorState, LoadingState } from "../components/AsyncState";
import styles from "./InvitationsPage.module.css";

export function InvitationsPage() {
  const { user } = useAuth();
  const orgId = user?.org_id;

  const [invitations, setInvitations] = useState<Invitation[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [roles, setRoles] = useState<Role[]>([]);

  const [email, setEmail] = useState("");
  const [roleId, setRoleId] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  function loadInvitations(): void {
    if (!orgId) return;
    setIsLoading(true);
    setLoadError(null);
    api.invitations
      .listPending(orgId)
      .then((result) => setInvitations(result))
      .catch((err: unknown) => {
        setLoadError(err instanceof ApiRequestError ? err.message : "Failed to load invitations.");
      })
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    loadInvitations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  useEffect(() => {
    if (!orgId) return;
    api.roles
      .listForOrg(orgId)
      .then((result) => {
        setRoles(result);
        if (result.length > 0) setRoleId((current) => current || result[0].id);
      })
      .catch(() => undefined); // the role picker degrading to empty isn't worth a page-level error
  }, [orgId]);

  async function handleCreate(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!orgId || !email.trim() || !roleId) return;
    setCreateError(null);
    setIsCreating(true);
    try {
      await api.invitations.create(orgId, email.trim(), roleId);
      setEmail("");
      loadInvitations();
    } catch (err) {
      setCreateError(err instanceof ApiRequestError ? err.message : "Couldn't send that invitation.");
    } finally {
      setIsCreating(false);
    }
  }

  async function handleRevoke(invitation: Invitation): Promise<void> {
    if (!orgId) return;
    if (!window.confirm(`Revoke the invitation sent to ${invitation.email}?`)) return;
    setRevokeError(null);
    setRevokingId(invitation.id);
    try {
      await api.invitations.revoke(orgId, invitation.id);
      setInvitations((prev) => (prev ? prev.filter((i) => i.id !== invitation.id) : prev));
    } catch (err) {
      setRevokeError(err instanceof ApiRequestError ? err.message : "Couldn't revoke that invitation.");
    } finally {
      setRevokingId(null);
    }
  }

  function roleName(id: string): string {
    return roles.find((r) => r.id === id)?.name ?? id;
  }

  return (
    <div>
      <h1>Invitations</h1>

      <form className={styles.createForm} onSubmit={(event) => void handleCreate(event)}>
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="person@example.com"
          aria-label="Email to invite"
          required
        />
        <select value={roleId} onChange={(event) => setRoleId(event.target.value)} aria-label="Role for invitation">
          {roles.length === 0 && <option value="">No roles available</option>}
          {roles.map((role) => (
            <option key={role.id} value={role.id}>
              {role.name}
            </option>
          ))}
        </select>
        <button type="submit" disabled={isCreating || !email.trim() || !roleId}>
          {isCreating ? "Sending…" : "Send invitation"}
        </button>
      </form>
      {createError && <ErrorState message={createError} />}
      {revokeError && <ErrorState message={revokeError} />}

      {loadError ? (
        <ErrorState message={loadError} onRetry={loadInvitations} />
      ) : isLoading ? (
        <LoadingState label="Loading invitations…" />
      ) : !invitations || invitations.length === 0 ? (
        <EmptyState message="No pending invitations." />
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Expires</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {invitations.map((invitation) => (
              <tr key={invitation.id}>
                <td>{invitation.email}</td>
                <td>{roleName(invitation.role_id)}</td>
                <td>{invitation.status}</td>
                <td>{new Date(invitation.expires_at).toLocaleDateString()}</td>
                <td>
                  <button
                    type="button"
                    onClick={() => void handleRevoke(invitation)}
                    disabled={revokingId === invitation.id}
                  >
                    {revokingId === invitation.id ? "Revoking…" : "Revoke"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
