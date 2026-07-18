/**
 * Product funnel tracking + device id.
 * Best-effort POST to /api/v1/product/track; never blocks UX.
 */

import { API_PREFIX } from "../api/client";

const DEVICE_KEY = "mingmirror_device_id_v1";

export type FunnelEvent =
  | "page_home"
  | "chart_created"
  | "report_viewed"
  | "package_export"
  | "package_export_blocked"
  | "calibrate_run"
  | "event_added"
  | "council_run"
  | "compatibility_run"
  | "pricing_view"
  | "pro_activated"
  | "credit_purchased";

export function getDeviceId(): string {
  try {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) {
      id =
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `dev-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch {
    return "anonymous";
  }
}

export function track(
  event: FunnelEvent | string,
  props?: Record<string, unknown>,
  chartId?: string
): void {
  const body = {
    event,
    device_id: getDeviceId(),
    chart_id: chartId || "",
    props: props || {},
  };
  try {
    // fire-and-forget; keepalive for unload
    void fetch(`${API_PREFIX}/product/track`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    // ignore
  }
}
