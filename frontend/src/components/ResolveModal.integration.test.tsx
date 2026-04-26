import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ResolveModal } from "./ResolveModal";
import { mockIncident } from "@/test/fixtures";
import { API_BASE_URL } from "@/lib/api";

const server = setupServer(
  http.post(`${API_BASE_URL}/incidents/:incident_id/resolve`, () => {
    return HttpResponse.json({
      incident_id: mockIncident.incident_id,
      status: "resolved",
      resolved_at: new Date().toISOString(),
      message: "Incident resolved successfully",
    });
  }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("ResolveModal", () => {
  it("renders with the incident summary pre-filled", () => {
    render(
      <ResolveModal
        incident={mockIncident}
        open={true}
        onOpenChange={vi.fn()}
        onResolved={vi.fn()}
      />,
    );
    const textarea = screen.getByRole("textbox", { name: /resolution notes/i });
    expect((textarea as HTMLTextAreaElement).value).toBe(mockIncident.summary);
  });

  it("renders the title", () => {
    render(
      <ResolveModal
        incident={mockIncident}
        open={true}
        onOpenChange={vi.fn()}
        onResolved={vi.fn()}
      />,
    );
    expect(screen.getByText("Mark Incident as Resolved")).toBeInTheDocument();
  });

  it("calls onResolved and onOpenChange after successful submission", async () => {
    const onResolved = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <ResolveModal
        incident={mockIncident}
        open={true}
        onOpenChange={onOpenChange}
        onResolved={onResolved}
      />,
    );

    fireEvent.click(screen.getByText("Mark as Resolved"));

    await waitFor(() => {
      expect(onResolved).toHaveBeenCalledOnce();
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it("shows error message on API failure", async () => {
    server.use(
      http.post(`${API_BASE_URL}/incidents/:incident_id/resolve`, () => {
        return HttpResponse.json({ detail: "storage_failed" }, { status: 503 });
      }),
    );

    render(
      <ResolveModal
        incident={mockIncident}
        open={true}
        onOpenChange={vi.fn()}
        onResolved={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("Mark as Resolved"));

    await waitFor(() => {
      expect(screen.getByText(/Failed to resolve incident/i)).toBeInTheDocument();
    });
  });

  it("does not render when open is false", () => {
    render(
      <ResolveModal
        incident={mockIncident}
        open={false}
        onOpenChange={vi.fn()}
        onResolved={vi.fn()}
      />,
    );
    expect(screen.queryByText("Mark Incident as Resolved")).not.toBeInTheDocument();
  });
});
