import styles from "./StatusBadge.module.css";

const LABELS: Record<string, string> = {
  open: "Open",
  claimed: "Claimed",
  closed: "Closed",
  active: "Active",
  pending_verification: "Pending verification",
  suspended: "Suspended",
  deactivated: "Deactivated",
};

export function StatusBadge({ status }: { status: string }) {
  const className = [styles.badge, styles[status]].filter(Boolean).join(" ");
  return <span className={className}>{LABELS[status] ?? status}</span>;
}
