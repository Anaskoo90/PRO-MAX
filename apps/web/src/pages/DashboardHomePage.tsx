import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiRequestError, type TicketListItem } from "@guilddesk/api-client";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/apiClient";
import { ErrorState, LoadingState } from "../components/AsyncState";
import styles from "./DashboardHomePage.module.css";

interface Summary {
  openTicketCount: number;
  claimedTicketCount: number;
  memberCount: number;
  recentTickets: TicketListItem[];
}

export function DashboardHomePage() {
  const { user } = useAuth();
  const orgId = user?.org_id;
  const [summary, setSummary] = useState<Summary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!orgId) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    // No dashboard-summary endpoint exists on the backend — this composes
    // the existing ticket search and member search endpoints instead of
    // inventing a new one, per Phase 2B scope (use existing APIs only).
    Promise.all([
      api.tickets.search(orgId, { status: "open", page_size: 1 }),
      api.tickets.search(orgId, { status: "claimed", page_size: 1 }),
      api.organizations.searchMembers(orgId, { page_size: 1 }),
      api.tickets.search(orgId, { sort: "-created_at", page_size: 5 }),
    ])
      .then(([openTickets, claimedTickets, members, recent]) => {
        if (cancelled) return;
        setSummary({
          openTicketCount: openTickets.total,
          claimedTicketCount: claimedTickets.total,
          memberCount: members.total,
          recentTickets: recent.data,
        });
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : "Failed to load dashboard data.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [orgId]);

  return (
    <div>
      <h1>Welcome{user ? `, ${user.display_name}` : ""}</h1>

      {error && <ErrorState message={error} />}

      {isLoading ? (
        <LoadingState label="Loading dashboard…" />
      ) : (
        summary && (
          <>
            <div className={styles.statGrid}>
              <Link to="/tickets" className={styles.statCard}>
                <span className={styles.statValue}>{summary.openTicketCount}</span>
                <span className={styles.statLabel}>Open tickets</span>
              </Link>
              <Link to="/tickets" className={styles.statCard}>
                <span className={styles.statValue}>{summary.claimedTicketCount}</span>
                <span className={styles.statLabel}>Claimed tickets</span>
              </Link>
              <Link to="/members" className={styles.statCard}>
                <span className={styles.statValue}>{summary.memberCount}</span>
                <span className={styles.statLabel}>Members</span>
              </Link>
            </div>

            <section className={styles.recentSection}>
              <h2>Recent tickets</h2>
              {summary.recentTickets.length === 0 ? (
                <p className={styles.emptyHint}>No tickets yet.</p>
              ) : (
                <ul className={styles.recentList}>
                  {summary.recentTickets.map((ticket) => (
                    <li key={ticket.id} className={styles.recentItem}>
                      <span className={styles.recentTitle}>
                        #{ticket.ticket_number} {ticket.title}
                      </span>
                      <span className={styles.recentStatus}>{ticket.status}</span>
                    </li>
                  ))}
                </ul>
              )}
              <Link to="/tickets" className={styles.viewAllLink}>
                View all tickets →
              </Link>
            </section>
          </>
        )
      )}
    </div>
  );
}
