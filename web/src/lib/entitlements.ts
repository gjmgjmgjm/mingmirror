/**
 * Product entitlement: prefer server, fall back to localStorage.
 */

import { API_PREFIX } from "../api/client";
import { getDeviceId, track } from "./analytics";

export type PlanId = "free" | "pro";

export interface Entitlement {
  plan: PlanId;
  /** ISO date or empty = no expiry */
  expiresAt: string;
  /** Single-shot credits for full package export (pro has unlimited) */
  packageCredits: number;
  /** true when loaded from server */
  fromServer?: boolean;
}

const KEY = "mingmirror_entitlement_v1";

const DEFAULT_FREE: Entitlement = {
  plan: "free",
  expiresAt: "",
  packageCredits: 0,
};

function fromServerPayload(data: {
  plan?: string;
  expires_at_iso?: string | null;
  expires_at?: number;
  package_credits?: number;
}): Entitlement {
  const plan: PlanId = data.plan === "pro" ? "pro" : "free";
  let expiresAt = "";
  if (data.expires_at_iso) expiresAt = data.expires_at_iso;
  else if (data.expires_at && data.expires_at > 0) {
    expiresAt = new Date(data.expires_at * 1000).toISOString();
  }
  return {
    plan,
    expiresAt,
    packageCredits: Number(data.package_credits) || 0,
    fromServer: true,
  };
}

export function getEntitlement(): Entitlement {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_FREE };
    const data = JSON.parse(raw) as Entitlement;
    if (data.plan === "pro" && data.expiresAt) {
      if (new Date(data.expiresAt).getTime() < Date.now()) {
        const free = { ...DEFAULT_FREE };
        setEntitlementLocal(free);
        return free;
      }
    }
    return {
      plan: data.plan === "pro" ? "pro" : "free",
      expiresAt: data.expiresAt || "",
      packageCredits: Number(data.packageCredits) || 0,
      fromServer: data.fromServer,
    };
  } catch {
    return { ...DEFAULT_FREE };
  }
}

function setEntitlementLocal(ent: Entitlement): void {
  localStorage.setItem(KEY, JSON.stringify(ent));
  window.dispatchEvent(new Event("mingmirror-entitlement"));
}

export function setEntitlement(ent: Entitlement): void {
  setEntitlementLocal(ent);
}

/** Pull server entitlement and cache locally (Bearer → user: scope). */
export async function refreshEntitlementFromServer(): Promise<Entitlement> {
  const deviceId = getDeviceId();
  try {
    let authHdrs: Record<string, string> = {};
    try {
      const { authHeaders } = await import("./auth");
      authHdrs = authHeaders();
    } catch {
      authHdrs = {};
    }
    const res = await fetch(
      `${API_PREFIX}/product/entitlement?device_id=${encodeURIComponent(deviceId)}`,
      {
        headers: {
          Accept: "application/json",
          ...authHdrs,
        },
      }
    );
    if (!res.ok) return getEntitlement();
    const data = await res.json();
    const ent = fromServerPayload(data);
    setEntitlementLocal(ent);
    return ent;
  } catch {
    return getEntitlement();
  }
}

const DEMO_CODE = "demo-pro";

/** Activate pro via server (demo code). Falls back to local if API down. */
export async function activateProDemo(days = 30): Promise<Entitlement> {
  const deviceId = getDeviceId();
  try {
    let authHdrs: Record<string, string> = {};
    try {
      const { authHeaders } = await import("./auth");
      authHdrs = authHeaders();
    } catch {
      authHdrs = {};
    }
    const res = await fetch(`${API_PREFIX}/product/entitlement/activate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...authHdrs,
      },
      body: JSON.stringify({
        device_id: deviceId,
        action: "pro",
        code: DEMO_CODE,
        days,
      }),
    });
    if (res.ok) {
      const body = await res.json();
      const ent = fromServerPayload(body.entitlement || body);
      setEntitlementLocal(ent);
      track("pro_activated", { days });
      return ent;
    }
  } catch {
    // fall through
  }
  // offline demo
  const expires = new Date();
  expires.setDate(expires.getDate() + days);
  const ent: Entitlement = {
    plan: "pro",
    expiresAt: expires.toISOString(),
    packageCredits: 99,
  };
  setEntitlementLocal(ent);
  track("pro_activated", { days, offline: true });
  return ent;
}

export async function buyPackageCredit(n = 1): Promise<Entitlement> {
  const deviceId = getDeviceId();
  try {
    let authHdrs: Record<string, string> = {};
    try {
      const { authHeaders } = await import("./auth");
      authHdrs = authHeaders();
    } catch {
      authHdrs = {};
    }
    const res = await fetch(`${API_PREFIX}/product/entitlement/activate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...authHdrs,
      },
      body: JSON.stringify({
        device_id: deviceId,
        action: "credit",
        code: DEMO_CODE,
        credits: n,
      }),
    });
    if (res.ok) {
      const body = await res.json();
      const ent = fromServerPayload(body.entitlement || body);
      setEntitlementLocal(ent);
      track("credit_purchased", { credits: n });
      return ent;
    }
  } catch {
    // fall through
  }
  const cur = getEntitlement();
  const ent: Entitlement = {
    ...cur,
    packageCredits: (cur.packageCredits || 0) + n,
  };
  setEntitlementLocal(ent);
  track("credit_purchased", { credits: n, offline: true });
  return ent;
}

export interface CheckoutResult {
  ok: boolean;
  duplicate?: boolean;
  payment_id?: string;
  external_id?: string;
  provider?: string;
  product?: string;
  amount_cents?: number;
  currency?: string;
  entitlement: Entitlement;
}

/** Closed-loop checkout (demo provider → ledger → entitlement). */
export async function checkoutProduct(
  product: "pro" | "package",
  opts?: { days?: number; credits?: number; amount_cents?: number }
): Promise<CheckoutResult> {
  const deviceId = getDeviceId();
  const res = await fetch(`${API_PREFIX}/product/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      device_id: deviceId,
      product,
      provider: "demo",
      days: opts?.days ?? 30,
      credits: opts?.credits ?? 1,
      amount_cents: opts?.amount_cents ?? 0,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`收银台失败 HTTP ${res.status}: ${text}`);
  }
  const body = await res.json();
  const ent = fromServerPayload(body.entitlement || {});
  setEntitlementLocal(ent);
  track("checkout_completed", {
    product,
    payment_id: body.payment_id,
    amount_cents: body.amount_cents,
  });
  return {
    ok: Boolean(body.ok),
    duplicate: body.duplicate,
    payment_id: body.payment_id,
    external_id: body.external_id,
    provider: body.provider,
    product: body.product,
    amount_cents: body.amount_cents,
    currency: body.currency,
    entitlement: ent,
  };
}

export interface PaymentRecord {
  id: string;
  provider: string;
  external_id: string;
  product: string;
  amount_cents: number;
  currency: string;
  status: string;
  created_at: number;
  created_at_iso?: string;
}

export async function fetchMyPayments(limit = 10): Promise<PaymentRecord[]> {
  const deviceId = getDeviceId();
  try {
    const res = await fetch(
      `${API_PREFIX}/product/payments?device_id=${encodeURIComponent(deviceId)}&limit=${limit}`,
      { headers: { Accept: "application/json" } }
    );
    if (!res.ok) return [];
    const body = await res.json();
    return (body.items || []) as PaymentRecord[];
  } catch {
    return [];
  }
}

export { DEMO_CODE, getDeviceId };

export function canExportFullPackage(ent?: Entitlement): boolean {
  const e = ent || getEntitlement();
  if (e.plan === "pro") return true;
  return (e.packageCredits || 0) > 0;
}

/**
 * Consume one credit. Prefers server; updates local cache.
 * Returns false if blocked.
 */
export async function consumePackageCreditAsync(): Promise<boolean> {
  const deviceId = getDeviceId();
  try {
    const res = await fetch(`${API_PREFIX}/product/entitlement/consume`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ device_id: deviceId }),
    });
    if (res.ok) {
      const body = await res.json();
      if (body.entitlement) {
        setEntitlementLocal(fromServerPayload(body.entitlement));
      }
      if (body.ok) {
        track("package_export", { reason: body.reason });
        return true;
      }
      track("package_export_blocked", { reason: body.reason });
      return false;
    }
  } catch {
    // offline local consume
  }
  const e = getEntitlement();
  if (e.plan === "pro") {
    track("package_export", { reason: "pro_local" });
    return true;
  }
  if ((e.packageCredits || 0) <= 0) {
    track("package_export_blocked", { reason: "no_credits_local" });
    return false;
  }
  setEntitlementLocal({ ...e, packageCredits: e.packageCredits - 1 });
  track("package_export", { reason: "credit_local" });
  return true;
}

/** Sync helper for call sites that still use sync API (best-effort local). */
export function consumePackageCredit(): boolean {
  const e = getEntitlement();
  if (e.plan === "pro") return true;
  if ((e.packageCredits || 0) <= 0) return false;
  // Kick async server consume; optimistically decrement
  void consumePackageCreditAsync();
  return true;
}

export const PLAN_COPY = {
  free: {
    name: "体验版",
    features: ["四柱排盘与结构层", "今日运势", "有限择日浏览", "校准记录"],
  },
  pro: {
    name: "完整版",
    features: [
      "标准命书交付包（打印 PDF）",
      "流年 / 议会 / 合婚共同择日",
      "事件校准权重写回",
      "优先功能更新",
    ],
  },
} as const;
