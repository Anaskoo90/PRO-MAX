import type { ReactNode } from "react";
import styles from "./AsyncState.module.css";

/** One shared shape for the three states every dashboard page's async data
 * can be in — loading, errored, or successfully loaded but empty — so each
 * page doesn't invent its own wording/markup for the same three cases. */

export function LoadingState({ label }: { label: string }) {
  return (
    <p className={styles.loading} role="status">
      {label}
    </p>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className={styles.error} role="alert">
      <p>{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className={styles.retryButton}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className={styles.empty}>
      <p>{message}</p>
      {action}
    </div>
  );
}
