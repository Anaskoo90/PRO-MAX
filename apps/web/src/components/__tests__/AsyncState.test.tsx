import { render, screen } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EmptyState, ErrorState, LoadingState } from "../AsyncState";

describe("LoadingState", () => {
  it("renders the given label as a status region", () => {
    render(<LoadingState label="Loading members…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading members…");
  });
});

describe("ErrorState", () => {
  it("renders the message as an alert", () => {
    render(<ErrorState message="Failed to load members." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Failed to load members.");
  });

  it("does not render a retry button when onRetry is omitted", () => {
    render(<ErrorState message="Failed." />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("calls onRetry when the retry button is clicked", () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Failed." onRetry={onRetry} />);

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("EmptyState", () => {
  it("renders the message", () => {
    render(<EmptyState message="No members match these filters." />);
    expect(screen.getByText("No members match these filters.")).toBeInTheDocument();
  });

  it("renders the optional action alongside the message", () => {
    render(<EmptyState message="No roles yet." action={<button>Create role</button>} />);
    expect(screen.getByRole("button", { name: "Create role" })).toBeInTheDocument();
  });
});
