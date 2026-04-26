import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { IncidentBrief } from "./IncidentBrief";
import { mockIncident } from "@/test/fixtures";

describe("IncidentBrief", () => {
  it("renders the incident title and ID", () => {
    render(<IncidentBrief incident={mockIncident} />);
    expect(screen.getByText(mockIncident.title)).toBeInTheDocument();
    expect(screen.getByText(mockIncident.incident_id)).toBeInTheDocument();
  });

  it("renders affected service and severity", () => {
    render(<IncidentBrief incident={mockIncident} />);
    expect(screen.getByText(mockIncident.affected_service)).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
  });

  it("renders the hypothesis summary", () => {
    render(<IncidentBrief incident={mockIncident} />);
    expect(screen.getByText(mockIncident.summary)).toBeInTheDocument();
  });

  it("renders recommended actions", () => {
    render(<IncidentBrief incident={mockIncident} />);
    for (const action of mockIncident.recommended_actions) {
      expect(screen.getByText(action)).toBeInTheDocument();
    }
  });

  it("renders status badge", () => {
    render(<IncidentBrief incident={mockIncident} />);
    expect(screen.getByText("Open")).toBeInTheDocument();
  });

  it("does not render recommended actions section when list is empty", () => {
    render(<IncidentBrief incident={{ ...mockIncident, recommended_actions: [] }} />);
    expect(screen.queryByText("Recommended Actions")).not.toBeInTheDocument();
  });
});
