import { Fragment, useEffect, useState } from "react";
import { ApiRequestError, type PermissionMatrix, type Role, type UserProfile } from "@guilddesk/api-client";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/apiClient";
import styles from "./RolesPage.module.css";

interface PermissionGroup {
  resource: string;
  permissions: PermissionMatrix["permissions"];
}

function groupPermissionsByResource(permissions: PermissionMatrix["permissions"]): PermissionGroup[] {
  const byResource = new Map<string, PermissionMatrix["permissions"]>();
  for (const permission of permissions) {
    const group = byResource.get(permission.resource) ?? [];
    group.push(permission);
    byResource.set(permission.resource, group);
  }
  return Array.from(byResource.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([resource, perms]) => ({ resource, permissions: perms }));
}

export function RolesPage() {
  const { user } = useAuth();
  const orgId = user?.org_id;
  const [matrix, setMatrix] = useState<PermissionMatrix | null>(null);
  const [matrixError, setMatrixError] = useState<string | null>(null);

  const [memberQuery, setMemberQuery] = useState("");
  const [memberResults, setMemberResults] = useState<UserProfile[]>([]);
  const [selectedMember, setSelectedMember] = useState<UserProfile | null>(null);
  const [memberRoleIds, setMemberRoleIds] = useState<Set<string> | null>(null);
  const [assignError, setAssignError] = useState<string | null>(null);
  const [pendingRoleId, setPendingRoleId] = useState<string | null>(null);

  useEffect(() => {
    if (!orgId) return;
    let cancelled = false;
    api.roles
      .getPermissionMatrix(orgId)
      .then((result) => {
        if (!cancelled) setMatrix(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setMatrixError(err instanceof ApiRequestError ? err.message : "Failed to load roles.");
      });
    return () => {
      cancelled = true;
    };
  }, [orgId]);

  useEffect(() => {
    if (!orgId || memberQuery.trim().length < 2) {
      setMemberResults([]);
      return;
    }
    let cancelled = false;
    const handle = setTimeout(() => {
      api.organizations
        .searchMembers(orgId, { q: memberQuery.trim(), page_size: 5 })
        .then((result) => {
          if (!cancelled) setMemberResults(result.data);
        })
        .catch(() => undefined);
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [orgId, memberQuery]);

  function selectMember(member: UserProfile): void {
    if (!orgId) return;
    setSelectedMember(member);
    setMemberResults([]);
    setMemberQuery("");
    setMemberRoleIds(null);
    setAssignError(null);
    api.roles
      .listForMember(orgId, member.id)
      .then((roles) => setMemberRoleIds(new Set(roles.map((r) => r.id))))
      .catch((err: unknown) => setAssignError(err instanceof ApiRequestError ? err.message : "Failed to load this member's roles."));
  }

  async function toggleRole(role: Role, isCurrentlyAssigned: boolean): Promise<void> {
    if (!selectedMember) return;
    setAssignError(null);
    setPendingRoleId(role.id);
    try {
      if (isCurrentlyAssigned) {
        await api.roles.revokeFromUser(selectedMember.id, role.id);
        setMemberRoleIds((prev) => {
          const next = new Set(prev);
          next.delete(role.id);
          return next;
        });
      } else {
        await api.roles.assignToUser(selectedMember.id, role.id);
        setMemberRoleIds((prev) => new Set(prev).add(role.id));
      }
    } catch (err) {
      setAssignError(err instanceof ApiRequestError ? err.message : "That change couldn't be saved.");
    } finally {
      setPendingRoleId(null);
    }
  }

  const groups = matrix ? groupPermissionsByResource(matrix.permissions) : [];

  return (
    <div>
      <h1>Roles &amp; Permissions</h1>

      <section className={styles.section}>
        <h2>Permission matrix</h2>
        {matrixError && <p className={styles.error}>{matrixError}</p>}
        {!matrix ? (
          <p>Loading…</p>
        ) : (
          <div className={styles.matrixScroll}>
            <table className={styles.matrix}>
              <thead>
                <tr>
                  <th>Permission</th>
                  {matrix.roles.map((role) => (
                    <th key={role.id}>{role.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <Fragment key={group.resource}>
                    <tr className={styles.groupRow}>
                      <th colSpan={matrix.roles.length + 1}>{group.resource}</th>
                    </tr>
                    {group.permissions.map((permission) => (
                      <tr key={permission.id}>
                        <td>{permission.action}</td>
                        {matrix.roles.map((role) => (
                          <td key={role.id} className={styles.matrixCell}>
                            {role.permission_ids.includes(permission.id) ? "✓" : ""}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className={styles.section}>
        <h2>Assign or remove a member's roles</h2>
        <div className={styles.memberPicker}>
          <input
            type="search"
            value={memberQuery}
            onChange={(event) => setMemberQuery(event.target.value)}
            placeholder="Search members by name or email…"
          />
          {memberResults.length > 0 && (
            <ul className={styles.memberResults}>
              {memberResults.map((member) => (
                <li key={member.id}>
                  <button type="button" onClick={() => selectMember(member)}>
                    {member.display_name} — {member.email}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {selectedMember && (
          <div className={styles.memberRoles}>
            <p>
              Managing roles for <strong>{selectedMember.display_name}</strong> ({selectedMember.email})
            </p>
            {assignError && <p className={styles.error}>{assignError}</p>}
            {memberRoleIds === null || !matrix ? (
              <p>Loading…</p>
            ) : (
              <ul className={styles.roleToggleList}>
                {matrix.roles.map((role) => {
                  const isAssigned = memberRoleIds.has(role.id);
                  return (
                    <li key={role.id}>
                      <label>
                        <input
                          type="checkbox"
                          checked={isAssigned}
                          disabled={pendingRoleId === role.id}
                          onChange={() => void toggleRole(role, isAssigned)}
                        />
                        {role.name}
                      </label>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
