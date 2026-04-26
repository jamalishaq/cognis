import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders Open with amber styling for open status", () => {
    render(<StatusBadge status="open" />);
    const badge = screen.getByText("Open");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("amber");
  });

  it("renders Resolved with green styling for resolved status", () => {
    render(<StatusBadge status="resolved" />);
    const badge = screen.getByText("Resolved");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("green");
  });
});
