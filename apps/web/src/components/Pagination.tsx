import styles from "./Pagination.module.css";

interface PaginationProps {
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, totalPages, total, onPageChange }: PaginationProps) {
  return (
    <div className={styles.pagination}>
      <button disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        Previous
      </button>
      <span className={styles.summary}>
        Page {page} of {Math.max(totalPages, 1)} · {total} total
      </span>
      <button disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
        Next
      </button>
    </div>
  );
}
