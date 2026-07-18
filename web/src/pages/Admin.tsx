import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  BarChart3,
  CreditCard,
  KeyRound,
  RefreshCw,
  Users,
  Wallet,
} from "lucide-react";
import { API_PREFIX } from "../api/client";
import { PageHeader, SectionCard, CloudDivider, ErrorPanel } from "../components/ui";

const TOKEN_KEY = "mingmirror_admin_token_v1";

const FUNNEL_LABELS: Record<string, string> = {
  page_home: "打开首页",
  chart_created: "生成命盘",
  demo_chart_loaded: "加载演示盘",
  report_viewed: "查看命书",
  package_export: "导出交付包",
  package_export_blocked: "导出被拦",
  calibrate_run: "运行校准",
  event_added: "添加事件",
  council_run: "召集议会",
  compatibility_run: "合婚分析",
  pricing_view: "打开套餐",
  pro_activated: "开通完整版",
  credit_purchased: "购买次数",
  checkout_completed: "收银台成交",
  payment_webhook: "支付回调",
  admin_grant: "运营授权",
};

interface Overview {
  funnel: {
    days: number;
    counts: Record<string, number>;
    rates: { export_per_chart: number; calibrate_per_chart: number };
    extra?: Record<string, number>;
  };
  payments_summary?: {
    days?: number;
    order_count: number;
    revenue_cents: number;
    revenue_yuan: number;
    pro_orders: number;
    credit_orders: number;
  };
  recent_payments?: Array<{
    id: string;
    provider: string;
    external_id: string;
    device_id: string;
    product: string;
    amount_cents: number;
    status: string;
    created_at: number;
  }>;
  recent_events: Array<{
    id: string;
    event: string;
    device_id: string;
    chart_id: string;
    created_at: number;
  }>;
  entitlements: Array<{
    device_id: string;
    plan: string;
    package_credits: number;
    expires_at_iso?: string | null;
  }>;
  charts: Array<{
    id: string;
    bazi: string;
    label: string;
    gender: string;
    updated_at: number;
  }>;
  admin_auth_required: boolean;
  demo_code_configured?: boolean;
  webhook_secret_configured?: boolean;
}

function loadToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

function yuan(cents: number): string {
  return `¥${(cents / 100).toFixed(2)}`;
}

export default function Admin() {
  const [token, setToken] = useState(loadToken);
  const [days, setDays] = useState(7);
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [grantDevice, setGrantDevice] = useState("");
  const [grantAction, setGrantAction] = useState<"pro" | "credit">("pro");
  const [grantDays, setGrantDays] = useState(30);
  const [grantCredits, setGrantCredits] = useState(1);
  const [grantMsg, setGrantMsg] = useState<string | null>(null);
  const [granting, setGranting] = useState(false);

  const saveToken = (t: string) => {
    setToken(t);
    try {
      localStorage.setItem(TOKEN_KEY, t);
    } catch {
      /* ignore */
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = `${API_PREFIX}/admin/overview?days=${days}`;
      const res = await fetch(url, {
        headers: {
          Accept: "application/json",
          ...(token ? { "X-Admin-Token": token } : {}),
        },
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
      }
      setData((await res.json()) as Overview);
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [days, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const doGrant = async () => {
    if (!grantDevice.trim()) {
      setGrantMsg("请填写 device_id");
      return;
    }
    setGranting(true);
    setGrantMsg(null);
    try {
      const res = await fetch(`${API_PREFIX}/admin/entitlement/grant`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...(token ? { "X-Admin-Token": token } : {}),
        },
        body: JSON.stringify({
          device_id: grantDevice.trim(),
          action: grantAction,
          days: grantDays,
          credits: grantCredits,
        }),
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const body = await res.json();
      setGrantMsg(
        `已授权 ${grantAction === "pro" ? "完整版" : "次数"} → plan=${body.entitlement?.plan} credits=${body.entitlement?.package_credits}`
      );
      await load();
    } catch (e) {
      setGrantMsg(e instanceof Error ? e.message : "授权失败");
    } finally {
      setGranting(false);
    }
  };

  const counts = data?.funnel?.counts || {};
  const maxCount = Math.max(1, ...Object.values(counts));
  const pay = data?.payments_summary;
  const payments = data?.recent_payments || [];

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <PageHeader
        title="运营看板"
        subtitle="漏斗 · 收款 · 权益 · 命盘（需 MINGMIRROR_ADMIN_TOKEN 时请填写管理密钥）"
      />
      <CloudDivider variant="gold" />

      <SectionCard>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[200px] flex-1">
            <label className="mb-1 flex items-center gap-1 text-xs text-ink-500">
              <KeyRound className="h-3.5 w-3.5" />
              管理密钥（X-Admin-Token）
            </label>
            <input
              type="password"
              value={token}
              onChange={(e) => saveToken(e.target.value)}
              placeholder="未设置服务端 token 时可留空"
              className="input w-full"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-500">天数</label>
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="input"
            >
              {[1, 7, 14, 30].map((d) => (
                <option key={d} value={d}>
                  近 {d} 天
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="btn-primary inline-flex items-center gap-1.5"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
        </div>
        {data && (
          <p className="mt-2 text-[11px] text-ink-400">
            鉴权 {data.admin_auth_required ? "已启用" : "开发模式（未设 token）"}
            {" · "}
            Webhook 密钥 {data.webhook_secret_configured ? "已配置" : "未配置（演示开放）"}
            {" · "}
            演示码 {data.demo_code_configured ? "已配置" : "—"}
          </p>
        )}
      </SectionCard>

      {error && <ErrorPanel title="加载失败">{error}</ErrorPanel>}

      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-600/30 dark:bg-ink-800/40">
              <div className="text-xs text-ink-400">命盘生成</div>
              <div className="mt-1 font-display text-3xl text-ink-800 dark:text-ink-100">
                {counts.chart_created || 0}
              </div>
            </div>
            <div className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-600/30 dark:bg-ink-800/40">
              <div className="text-xs text-ink-400">导出交付包</div>
              <div className="mt-1 font-display text-3xl text-jade">
                {counts.package_export || 0}
              </div>
              <div className="text-[11px] text-ink-400">
                转化率{" "}
                {((data.funnel.rates?.export_per_chart || 0) * 100).toFixed(1)}%
              </div>
            </div>
            <div className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-600/30 dark:bg-ink-800/40">
              <div className="flex items-center gap-1 text-xs text-ink-400">
                <Wallet className="h-3.5 w-3.5" />
                收款金额
              </div>
              <div className="mt-1 font-display text-3xl text-gold">
                {pay ? yuan(pay.revenue_cents) : "¥0.00"}
              </div>
              <div className="text-[11px] text-ink-400">
                {pay?.order_count || 0} 笔 · Pro {pay?.pro_orders || 0} · 次数{" "}
                {pay?.credit_orders || 0}
              </div>
            </div>
            <div className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-600/30 dark:bg-ink-800/40">
              <div className="text-xs text-ink-400">收银台 / 校准</div>
              <div className="mt-1 font-display text-3xl text-vermilion">
                {counts.checkout_completed || 0}
              </div>
              <div className="text-[11px] text-ink-400">
                校准 {counts.calibrate_run || 0} · 演示盘{" "}
                {counts.demo_chart_loaded || 0}
              </div>
            </div>
          </div>

          <SectionCard
            title={
              <>
                <BarChart3 className="mr-1.5 inline h-4 w-4 text-gold" />
                漏斗（近 {data.funnel.days} 天）
              </>
            }
            borderLeft="gold"
          >
            <div className="space-y-2">
              {Object.entries(data.funnel.counts).map(([key, n]) => (
                <div key={key}>
                  <div className="mb-0.5 flex justify-between text-xs">
                    <span className="text-ink-600 dark:text-ink-300">
                      {FUNNEL_LABELS[key] || key}
                    </span>
                    <span className="text-ink-500">{n}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-ink-100 dark:bg-ink-800">
                    <div
                      className="h-full rounded-full bg-gold/80"
                      style={{ width: `${Math.round((n / maxCount) * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard
            title={
              <>
                <CreditCard className="mr-1.5 inline h-4 w-4 text-jade" />
                最近收款
              </>
            }
            borderLeft="jade"
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-ink-300/20 text-ink-400">
                    <th className="py-2 pr-2">时间</th>
                    <th className="py-2 pr-2">商品</th>
                    <th className="py-2 pr-2">金额</th>
                    <th className="py-2 pr-2">设备</th>
                    <th className="py-2">订单</th>
                  </tr>
                </thead>
                <tbody>
                  {payments.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-3 text-ink-400">
                        暂无收款（可在套餐页走收银台）
                      </td>
                    </tr>
                  )}
                  {payments.map((p) => (
                    <tr
                      key={p.id}
                      className="border-b border-ink-300/10 text-ink-600 dark:text-ink-300"
                    >
                      <td className="py-2 pr-2 whitespace-nowrap">
                        {p.created_at
                          ? new Date(p.created_at * 1000).toLocaleString()
                          : ""}
                      </td>
                      <td className="py-2 pr-2">{p.product}</td>
                      <td className="py-2 pr-2 text-gold">
                        {yuan(p.amount_cents)}
                      </td>
                      <td className="py-2 pr-2 font-mono text-[10px]">
                        {p.device_id?.slice(0, 14)}
                      </td>
                      <td className="py-2 font-mono text-[10px] text-ink-400">
                        {p.external_id?.slice(0, 16)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard title="运营手动授权" borderLeft="vermilion">
            <div className="flex flex-wrap items-end gap-3">
              <label className="text-xs text-ink-500">
                device_id
                <input
                  className="input mt-1 w-48 text-sm"
                  value={grantDevice}
                  onChange={(e) => setGrantDevice(e.target.value)}
                  placeholder="粘贴设备 ID"
                />
              </label>
              <label className="text-xs text-ink-500">
                动作
                <select
                  className="input mt-1 text-sm"
                  value={grantAction}
                  onChange={(e) =>
                    setGrantAction(e.target.value as "pro" | "credit")
                  }
                >
                  <option value="pro">完整版</option>
                  <option value="credit">交付包次数</option>
                </select>
              </label>
              {grantAction === "pro" ? (
                <label className="text-xs text-ink-500">
                  天数
                  <input
                    type="number"
                    className="input mt-1 w-20 text-sm"
                    value={grantDays}
                    min={1}
                    max={365}
                    onChange={(e) => setGrantDays(Number(e.target.value) || 30)}
                  />
                </label>
              ) : (
                <label className="text-xs text-ink-500">
                  次数
                  <input
                    type="number"
                    className="input mt-1 w-20 text-sm"
                    value={grantCredits}
                    min={1}
                    max={50}
                    onChange={(e) =>
                      setGrantCredits(Number(e.target.value) || 1)
                    }
                  />
                </label>
              )}
              <button
                type="button"
                className="btn-primary text-sm"
                disabled={granting}
                onClick={() => void doGrant()}
              >
                {granting ? "授权中…" : "授权"}
              </button>
            </div>
            {grantMsg && (
              <p className="mt-2 text-xs text-ink-500">{grantMsg}</p>
            )}
          </SectionCard>

          <div className="grid gap-4 lg:grid-cols-2">
            <SectionCard
              title={
                <>
                  <Activity className="mr-1.5 inline h-4 w-4 text-vermilion" />
                  最近事件
                </>
              }
            >
              <div className="max-h-72 space-y-2 overflow-y-auto text-xs">
                {data.recent_events.length === 0 && (
                  <p className="text-ink-400">暂无埋点</p>
                )}
                {data.recent_events.map((e) => (
                  <div
                    key={e.id}
                    className="rounded-lg border border-ink-300/15 bg-ink-100/30 px-2 py-1.5 dark:border-ink-600/20 dark:bg-ink-800/30"
                  >
                    <div className="flex justify-between gap-2">
                      <span className="font-medium text-ink-700 dark:text-ink-200">
                        {FUNNEL_LABELS[e.event] || e.event}
                      </span>
                      <span className="shrink-0 text-ink-400">
                        {e.created_at
                          ? new Date(e.created_at * 1000).toLocaleString()
                          : ""}
                      </span>
                    </div>
                    <div className="truncate text-ink-400">
                      {e.device_id?.slice(0, 12) || "—"}
                      {e.chart_id ? ` · ${e.chart_id.slice(0, 12)}` : ""}
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>

            <SectionCard
              title={
                <>
                  <Users className="mr-1.5 inline h-4 w-4 text-jade" />
                  权益设备
                </>
              }
            >
              <div className="max-h-72 space-y-2 overflow-y-auto text-xs">
                {data.entitlements.length === 0 && (
                  <p className="text-ink-400">尚无开通记录</p>
                )}
                {data.entitlements.map((ent) => (
                  <div
                    key={ent.device_id}
                    className="rounded-lg border border-ink-300/15 bg-ink-100/30 px-2 py-1.5 dark:border-ink-600/20 dark:bg-ink-800/30"
                  >
                    <div className="flex justify-between">
                      <span className="font-medium text-ink-700 dark:text-ink-200">
                        {ent.plan === "pro" ? "完整版" : "体验版"}
                      </span>
                      <span className="text-ink-400">
                        额度 {ent.package_credits}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="truncate text-left text-ink-400 hover:text-vermilion"
                      title="填入授权框"
                      onClick={() => setGrantDevice(ent.device_id)}
                    >
                      {ent.device_id}
                    </button>
                    {ent.expires_at_iso && (
                      <div className="text-ink-400">
                        至 {new Date(ent.expires_at_iso).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </SectionCard>
          </div>

          <SectionCard title="最近命盘">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-ink-300/20 text-ink-400">
                    <th className="py-2 pr-2">标签</th>
                    <th className="py-2 pr-2">八字</th>
                    <th className="py-2 pr-2">性别</th>
                    <th className="py-2">更新</th>
                  </tr>
                </thead>
                <tbody>
                  {data.charts.length === 0 && (
                    <tr>
                      <td colSpan={4} className="py-3 text-ink-400">
                        暂无命盘
                      </td>
                    </tr>
                  )}
                  {data.charts.map((c) => (
                    <tr
                      key={c.id}
                      className="border-b border-ink-300/10 text-ink-600 dark:text-ink-300"
                    >
                      <td className="py-2 pr-2">{c.label || "—"}</td>
                      <td className="py-2 pr-2 font-mono">{c.bazi}</td>
                      <td className="py-2 pr-2">
                        {c.gender === "female" ? "女" : "男"}
                      </td>
                      <td className="py-2">
                        {c.updated_at
                          ? new Date(c.updated_at * 1000).toLocaleString()
                          : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </>
      )}

      <p className="text-center text-xs text-ink-400">
        <Link to="/" className="text-vermilion underline">
          返回首页
        </Link>
        {" · "}
        <Link to="/pricing" className="text-ink-500 underline">
          套餐收银台
        </Link>
        {" · "}
        POST /api/v1/product/checkout · webhook · grant
      </p>
    </div>
  );
}
