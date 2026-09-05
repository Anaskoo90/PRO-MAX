import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiRequestError, type Role, type UserProfile } from "@guilddesk/api-client";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/apiClient";
import { ErrorState, LoadingState } from "../components/AsyncState";
import { StatusBadge } from "../components/StatusBadge";
import styles from "./MemberDetailPage.module.css";

export function MemberDetailPage() {
  const { user } = useAuth();
  const { userId } = useParams<{ userId: string }>();
  const [member, setMember] = useState<UserProfile | null>(null);
  const [roles, setRoles] = useState<Role[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!user || !userId) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    Promise.all([api.organizations.getMember(user.org_id, userId), api.roles.listForMember(user.org_id, userId)])
      .then(([memberResult, rolesResult]) => {
        if (cancelled) return;
        setMember(memberResult);
        setRoles(rolesResult);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiRequestError ? err.message : "Failed to load this member.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [user, userId]);

  return (
    <div>
      <Link to="/members" className={styles.backLink}>
        ← Back to members
      </Link>
      <h1>Member details</h1>

      {error && <ErrorState message={error} />}

      {isLoading ? (
        <LoadingState label="Loading member…" />
      ) : (
        member && (
          <div className={styles.card}>
            <dl className={styles.detailList}>
              <dt>Name</dt>
              <dd>{member.display_name}</dd>
              <dt>Email</dt>
              <dd>{member.email}</dd>
              <dt>Status</dt>
              <dd>
                <StatusBadge status={member.status} />
              </dd>
              <dt>Multi-factor authentication</dt>
              <dd>{member.mfa_enabled ? "Enabled" : "Not enabled"}</dd>
              <dt>Roles</dt>
              <dd>
                {roles && roles.length > 0 ? (
                  <ul className={styles.roleList}>
                    {roles.map((role) => (
                      <li key={role.id}>{role.name}</li>
                    ))}
                  </ul>
                ) : (
                  <span className={styles.noRoles}>No roles assigned</span>
                )}
              </dd>
            </dl>
            <p className={styles.hint}>
              To assign or remove roles for this member, use the <Link to="/roles">Roles</Link> page.
            </p>
          </div>
        )
      )}
    </div>
  );
}
