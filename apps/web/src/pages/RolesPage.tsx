import { Fragment, useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiRequestError, type PermissionMatrix, type Role, type UserProfile } from "@guilddesk/api-client";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/apiClient";
import { EmptyState, ErrorState, LoadingState } from "../components/AsyncState";
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
  const [isLoadingMatrix, setIsLoadingMatrix] = useState(true);
  const [matrixError, setMatrixError] = useState<string | null>(null);

  const [memberQuery, setMemberQuery] = useState("");
  const [memberResults, setMemberResults] = useState<UserProfile[]>([]);
  const [selectedMember, setSelectedMember] = useState<UserProfile | null>(null);
  const [memberRoleIds, setMemberRoleIds] = useState<Set<string> | null>(null);
  const [assignError, setAssignError] = useState<string | null>(null);
  const [pendingRoleId, setPendingRoleId] = useState<string | null>(null);

  const [newRoleName, setNewRoleName] = useState("");
  const [newRoleDescription, setNewRoleDescription] = useState("");
  const [isCreatingRole, setIsCreatingRole] = useState(false);
  const [createRoleError, setCreateRoleError] = useState<string | null>(null);

  const [editingRoleId, setEditingRoleId] = useState<string | null>(null);
  const [editingRoleName, setEditingRoleName] = useState("");
  const [roleActionError, setRoleActionError] = useState<string | null>(null);
  const [pendingRoleAction, setPendingRoleAction] = useState<string | null>(null);
  const [expandedRoleId, setExpandedRoleId] = useState<string | null>(null);

  const loadMatrix = useCallback(() => {
    if (!orgId) return;
    setIsLoadingMatrix(true);
    setMatrixError(null);
    return api.roles
      .getPermissionMatrix(orgId)
      .then((result) => setMatrix(result))
      .catch((err: unknown) => {
        setMatrixError(err instanceof ApiRequestError ? err.message : "Failed to load roles.");
      })
      .finally(() => setIsLoadingMatrix(false));
  }, [orgId]);

  useEffect(() => {
    void loadMatrix();
  }, [loadMatrix]);

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

  async function handleCreateRole(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!newRoleName.trim()) return;
    setIsCreatingRole(true);
    setCreateRoleError(null);
    try {
      await api.roles.create(newRoleName.trim(), newRoleDescription.trim());
      setNewRoleName("");
      setNewRoleDescription("");
      await loadMatrix();
    } catch (err) {
      setCreateRoleError(err instanceof ApiRequestError ? err.message : "Couldn't create that role.");
    } finally {
      setIsCreatingRole(false);
    }
  }

  function startEditingRole(role: Role): void {
    setEditingRoleId(role.id);
    setEditingRoleName(role.name);
    setRoleActionError(null);
  }

  async function saveRoleName(role: Role): Promise<void> {
    if (!editingRoleName.trim() || editingRoleName === role.name) {
      setEditingRoleId(null);
      return;
    }
    setPendingRoleAction(role.id);
    setRoleActionError(null);
    try {
      await api.roles.update(role.id, editingRoleName.trim());
      setEditingRoleId(null);
      await loadMatrix();
    } catch (err) {
      setRoleActionError(err instanceof ApiRequestError ? err.message : "Couldn't rename that role.");
    } finally {
      setPendingRoleAction(null);
    }
  }

  async function handleDeleteRole(role: Role): Promise<void> {
    if (!window.confirm(`Delete the "${role.name}" role? This cannot be undone.`)) return;
    setPendingRoleAction(role.id);
    setRoleActionError(null);
    try {
      await api.roles.delete(role.id);
      await loadMatrix();
    } catch (err) {
      setRoleActionError(err instanceof ApiRequestError ? err.message : "Couldn't delete that role.");
    } finally {
      setPendingRoleAction(null);
    }
  }

  async function togglePermission(role: Role, permissionId: string, isCurrentlyGranted: boolean): Promise<void> {
    setPendingRoleAction(`${role.id}:${permissionId}`);
    setRoleActionError(null);
    try {
      if (isCurrentlyGranted) {
        await api.roles.revokePermission(role.id, permissionId);
      } else {
        await api.roles.grantPermission(role.id, permissionId);
      }
      await loadMatrix();
    } catch (err) {
      setRoleActionError(err instanceof ApiRequestError ? err.message : "That permission change couldn't be saved.");
    } finally {
      setPendingRoleAction(null);
    }
  }


  const groups = matrix ? groupPermissionsByResource(matrix.permissions) : [];

  return (
    <div>
      <h1>Roles &amp; Permissions</h1>

      <section className={styles.section}>
        <h2>Permission matrix</h2>
        {matrixError ? (
          <ErrorState message={matrixError} onRetry={() => void loadMatrix()} />
        ) : isLoadingMatrix ? (
          <LoadingState label="Loading roles…" />
        ) : !matrix || matrix.roles.length === 0 ? (
          <EmptyState message="No roles yet." />
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
        <h2>Manage roles</h2>

        <form className={styles.createRoleForm} onSubmit={(event) => void handleCreateRole(event)}>
          <input
            type="text"
            value={newRoleName}
            onChange={(event) => setNewRoleName(event.target.value)}
            placeholder="New role name"
            aria-label="New role name"
            required
          />
          <input
            type="text"
            value={newRoleDescription}
            onChange={(event) => setNewRoleDescription(event.target.value)}
            placeholder="Description (optional)"
            aria-label="New role description"
          />
          <button type="submit" disabled={isCreatingRole || !newRoleName.trim()}>
            {isCreatingRole ? "Creating…" : "Create role"}
          </button>
        </form>
        {createRoleError && <ErrorState message={createRoleError} />}
        {roleActionError && <ErrorState message={roleActionError} />}

        {matrix && matrix.roles.length > 0 && (
          <ul className={styles.roleAdminList}>
            {matrix.roles.map((role) => {
              const isEditing = editingRoleId === role.id;
              const isExpanded = expandedRoleId === role.id;
              const isBusy = pendingRoleAction === role.id;
              return (
                <li key={role.id} className={styles.roleAdminItem}>
                  <div className={styles.roleAdminRow}>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editingRoleName}
                        onChange={(event) => setEditingRoleName(event.target.value)}
                        onBlur={() => void saveRoleName(role)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") void saveRoleName(role);
                          if (event.key === "Escape") setEditingRoleId(null);
                        }}
                        autoFocus
                        aria-label={`Rename ${role.name}`}
                      />
                    ) : (
                      <span className={styles.roleAdminName}>
                        {role.name}
                        {role.is_system_role && <span className={styles.systemBadge}>System</span>}
                      </span>
                    )}

                    <div className={styles.roleAdminActions}>
                      <button
                        type="button"
                        onClick={() => setExpandedRoleId(isExpanded ? null : role.id)}
                      >
                        {isExpanded ? "Hide permissions" : "Edit permissions"}
                      </button>
                      {!role.is_system_role && (
                        <>
                          <button type="button" disabled={isBusy} onClick={() => startEditingRole(role)}>
                            Rename
                          </button>
                          <button
                            type="button"
                            disabled={isBusy}
                            className={styles.dangerButton}
                            onClick={() => void handleDeleteRole(role)}
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {isExpanded && matrix && (
                    <ul className={styles.permissionToggleList}>
                      {matrix.permissions.map((permission) => {
                        const isGranted = role.permission_ids.includes(permission.id);
                        const isTogglePending = pendingRoleAction === `${role.id}:${permission.id}`;
                        return (
                          <li key={permission.id}>
                            <label>
                              <input
                                type="checkbox"
                                checked={isGranted}
                                disabled={role.is_system_role || isTogglePending}
                                onChange={() => void togglePermission(role, permission.id, isGranted)}
                              />
                              {permission.resource}:{permission.action}
                            </label>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
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
            {assignError && <ErrorState message={assignError} />}
            {memberRoleIds === null || !matrix ? (
              <LoadingState label="Loading this member's roles…" />
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
