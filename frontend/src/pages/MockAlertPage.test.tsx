import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { MockAlertPage } from "./MockAlertPage";

const renderPage = () => render(<MemoryRouter><MockAlertPage /></MemoryRouter>);

const GRAFANA_PAYLOAD = {
  alerts: [
    {
      status: "firing",
      labels: {
        alertname: "HighLatency",
        severity: "critical",
        service: "payments-api",
        namespace: "production",
        instance: "payments-api-7d9f8b-xk2p",
      },
      annotations: {
        description:
          "p99 latency for payments-api has exceeded 2000ms for the past 5 minutes",
        summary: "High latency detected on payments-api",
      },
      startsAt: "2026-04-23T10:15:00Z",
      endsAt: "0001-01-01T00:00:00Z",
      generatorURL: "http://grafana.internal/alerting/payments-latency",
    },
  ],
  version: "4",
  groupKey: "{}:{alertname=HighLatency}",
  status: "firing",
  receiver: "cognis-webhook",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("MockAlertPage", () => {
  it("renders correctly with Grafana selected by default", () => {
    renderPage();

    expect(screen.getByText(/Cognis Mock Alert Firing/)).toBeInTheDocument();
    expect(screen.getByLabelText("Alert Source")).toHaveValue("grafana");
    expect(
      screen.getByRole("button", { name: "Fire Alert" })
    ).toBeInTheDocument();
  });

  it("calls fetch with the correct Grafana payload on submit", async () => {
    const user = userEvent.setup();
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ incident_id: "INC-20260423-001" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    renderPage();
    await user.click(screen.getByRole("button", { name: "Fire Alert" }));

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/analyse$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(GRAFANA_PAYLOAD);
  });

  it("displays incident_id prominently with a copy button on success", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ incident_id: "INC-20260423-001" }),
      })
    );

    renderPage();
    await user.click(screen.getByRole("button", { name: "Fire Alert" }));

    await waitFor(() => {
      expect(screen.getByText("INC-20260423-001")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
  });

  it("displays error message with status code and detail on failure", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: vi.fn().mockResolvedValue({ detail: "validation error" }),
      })
    );

    renderPage();
    await user.click(screen.getByRole("button", { name: "Fire Alert" }));

    await waitFor(() => {
      expect(screen.getByText("422: validation error")).toBeInTheDocument();
    });
  });
});
