import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiRequestError, type UserProfile } from "@guilddesk/api-client";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/apiClient";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import styles from "./MembersPage.module.css";

const PAGE_SIZE = 20;

const STATUS_OPTIONS = ["all", "active", "pending_verification", "suspended", "deactivated"] as const;
type StatusFilter = (typeof STATUS_OPTIONS)[number];

const STATUS_LABELS: Record<StatusFilter, string> = {
  all: "All",
  active: "Active",
  pending_verification: "Pending verification",
  suspended: "Suspended",
  deactivated: "Deactivated",
};

export function MembersPage() {
  const { user } = useAuth();
  const orgId = user?.org_id;
  const [members, setMembers] = useState<UserProfile[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!orgId) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    const handle = setTimeout(() => {
      api.organizations
        .searchMembers(orgId, {
          page, page_size: PAGE_SIZE, q: query.trim() || undefined, status: status === "all" ? undefined : status,
        })
        .then((result) => {
          if (cancelled) return;
          setMembers(result.data);
          setTotal(result.total);
          setTotalPages(result.total_pages);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setError(err instanceof ApiRequestError ? err.message : "Failed to load members.");
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false);
        });
    }, 250); // debounce the search box so every keystroke doesn't fire a request

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [orgId, page, query, status]);

  function handleQueryChange(next: string): void {
    setQuery(next);
    setPage(1);
  }

  function handleStatusChange(next: StatusFilter): void {
    setStatus(next);
    setPage(1);
  }

  return (
    <div>
      <h1>Members</h1>
      <div className={styles.toolbar}>
        <label className={styles.filterField}>
          Search
          <input
            type="search"
            value={query}
            onChange={(event) => handleQueryChange(event.target.value)}
            placeholder="Name or email"
          />
        </label>
        <label className={styles.filterField}>
          Status
          <select value={status} onChange={(event) => handleStatusChange(event.target.value as StatusFilter)}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {STATUS_LABELS[option]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {isLoading ? (
        <p>Loading members…</p>
      ) : members.length === 0 ? (
        <p>No members match these filters.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Status</th>
              <th>MFA</th>
            </tr>
          </thead>
          <tbody>
            {members.map((member) => (
              <tr key={member.id}>
                <td>
                  <Link to={`/members/${member.id}`}>{member.display_name}</Link>
                </td>
                <td>{member.email}</td>
                <td>
                  <StatusBadge status={member.status} />
                </td>
                <td>{member.mfa_enabled ? "Enabled" : "Off"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Pagination page={page} totalPages={totalPages} total={total} onPageChange={setPage} />
    </div>
  );
}
