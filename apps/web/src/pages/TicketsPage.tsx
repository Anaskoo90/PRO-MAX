import { useEffect, useState } from "react";
import { ApiRequestError, type TicketListItem } from "@guilddesk/api-client";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/apiClient";
import { EmptyState, ErrorState, LoadingState } from "../components/AsyncState";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import styles from "./TicketsPage.module.css";

const PAGE_SIZE = 20;

const STATUS_OPTIONS = ["all", "open", "claimed", "closed"] as const;
type StatusFilter = (typeof STATUS_OPTIONS)[number];

const SORT_OPTIONS: { label: string; value: string }[] = [
  { label: "Newest first", value: "-created_at" },
  { label: "Oldest first", value: "created_at" },
  { label: "Ticket # (ascending)", value: "ticket_number" },
  { label: "Ticket # (descending)", value: "-ticket_number" },
];

export function TicketsPage() {
  const { user } = useAuth();
  const orgId = user?.org_id;
  const [tickets, setTickets] = useState<TicketListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [sort, setSort] = useState(SORT_OPTIONS[0].value);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!orgId) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    api.tickets
      .search(orgId, {
        page,
        page_size: PAGE_SIZE,
        status: status === "all" ? undefined : status,
        sort,
      })
      .then((result) => {
        if (cancelled) return;
        setTickets(result.data);
        setTotal(result.total);
        setTotalPages(result.total_pages);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiRequestError ? err.message : "Failed to load tickets.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [orgId, page, status, sort, reloadToken]);

  function handleStatusChange(next: StatusFilter): void {
    setStatus(next);
    setPage(1);
  }

  function handleSortChange(next: string): void {
    setSort(next);
    setPage(1);
  }

  return (
    <div>
      <h1>Tickets</h1>
      <div className={styles.toolbar}>
        <label className={styles.filterField}>
          Status
          <select value={status} onChange={(event) => handleStatusChange(event.target.value as StatusFilter)}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option === "all" ? "All" : option[0].toUpperCase() + option.slice(1)}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.filterField}>
          Sort by
          <select value={sort} onChange={(event) => handleSortChange(event.target.value)}>
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <ErrorState message={error} onRetry={() => setReloadToken((n) => n + 1)} />}

      {isLoading ? (
        <LoadingState label="Loading tickets…" />
      ) : tickets.length === 0 ? (
        <EmptyState message="No tickets match these filters." />
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>#</th>
              <th>Title</th>
              <th>Status</th>
              <th>Claimed by</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((ticket) => (
              <tr key={ticket.id}>
                <td>{ticket.ticket_number}</td>
                <td>{ticket.title}</td>
                <td>
                  <StatusBadge status={ticket.status} />
                </td>
                <td>{ticket.claimed_by_discord_user_id ?? "—"}</td>
                <td>{new Date(ticket.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Pagination page={page} totalPages={totalPages} total={total} onPageChange={setPage} />
    </div>
  );
}
