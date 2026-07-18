import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, CreditCard, Sparkles } from "lucide-react";
import {
  activateProDemo,
  buyPackageCredit,
  checkoutProduct,
  fetchMyPayments,
  getDeviceId,
  getEntitlement,
  refreshEntitlementFromServer,
  PLAN_COPY,
  type Entitlement,
  type PaymentRecord,
} from "../lib/entitlements";
import { track } from "../lib/analytics";
import { PageHeader, SectionCard, CloudDivider } from "../components/ui";

function yuan(cents: number): string {
  return `¥${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 2)}`;
}

export default function Pricing() {
  const [ent, setEnt] = useState<Entitlement>(() => getEntitlement());
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const deviceId = getDeviceId();

  const reloadPayments = useCallback(async () => {
    setPayments(await fetchMyPayments(12));
  }, []);

  useEffect(() => {
    track("pricing_view");
    const sync = () => setEnt(getEntitlement());
    window.addEventListener("mingmirror-entitlement", sync);
    void refreshEntitlementFromServer().then(setEnt);
    void reloadPayments();
    return () => window.removeEventListener("mingmirror-entitlement", sync);
  }, [reloadPayments]);

  const onCheckoutPro = async () => {
    setBusy("checkout-pro");
    setError(null);
    setFlash(null);
    try {
      const result = await checkoutProduct("pro", { days: 30, amount_cents: 9900 });
      setEnt(result.entitlement);
      setFlash(
        result.duplicate
          ? "订单已处理过（幂等），权益未重复发放。"
          : `收银台成功：完整版 30 天 · 订单 ${result.external_id?.slice(0, 12)}… · ${yuan(result.amount_cents || 9900)}（演示渠道）`
      );
      await reloadPayments();
    } catch (e) {
      // fall back to demo code activation if checkout endpoint unavailable
      try {
        const next = await activateProDemo(30);
        setEnt(next);
        setFlash("已用演示码激活完整版 30 天（收银台不可用时的降级路径）。");
      } catch {
        setError(e instanceof Error ? e.message : "开通失败");
      }
    } finally {
      setBusy(null);
    }
  };

  const onCheckoutPackage = async () => {
    setBusy("checkout-pkg");
    setError(null);
    setFlash(null);
    try {
      const result = await checkoutProduct("package", {
        credits: 1,
        amount_cents: 1900,
      });
      setEnt(result.entitlement);
      setFlash(
        result.duplicate
          ? "订单已处理过（幂等）。"
          : `收银台成功：+1 次交付包 · 当前额度 ${result.entitlement.packageCredits} · ${yuan(result.amount_cents || 1900)}`
      );
      await reloadPayments();
    } catch (e) {
      try {
        const next = await buyPackageCredit(1);
        setEnt(next);
        setFlash(`已增加 1 次交付包额度（当前 ${next.packageCredits} 次，演示降级）。`);
        await reloadPayments();
      } catch {
        setError(e instanceof Error ? e.message : "购买失败");
      }
    } finally {
      setBusy(null);
    }
  };

  const onProDemoCode = async () => {
    setBusy("demo-pro");
    setError(null);
    try {
      const next = await activateProDemo(30);
      setEnt(next);
      setFlash("演示码 demo-pro 已激活完整版 30 天。");
    } catch (e) {
      setError(e instanceof Error ? e.message : "激活失败");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        title="套餐与权益"
        subtitle="服务端权益为真源：收银台入账 → 账本幂等 → 开通完整版/次数"
      />
      <CloudDivider variant="gold" />

      <SectionCard>
        <p className="text-sm text-ink-600 dark:text-ink-300">
          当前：
          <span className="ml-1 font-medium text-gold">
            {ent.plan === "pro" ? PLAN_COPY.pro.name : PLAN_COPY.free.name}
          </span>
          {ent.plan === "pro" && ent.expiresAt && (
            <span className="ml-2 text-xs text-ink-400">
              至 {new Date(ent.expiresAt).toLocaleDateString()}
            </span>
          )}
          <span className="ml-2 text-xs text-ink-400">
            交付包额度 {ent.plan === "pro" ? "完整版不限" : `${ent.packageCredits} 次`}
          </span>
          {ent.fromServer && (
            <span className="ml-2 rounded bg-jade/15 px-1.5 py-0.5 text-[10px] text-jade">
              服务端同步
            </span>
          )}
        </p>
        <p className="mt-2 font-mono text-[11px] text-ink-400">
          device_id · {deviceId.slice(0, 18)}…
        </p>
        {flash && <p className="mt-2 text-xs text-jade">{flash}</p>}
        {error && <p className="mt-2 text-xs text-vermilion">{error}</p>}
        <p className="mt-2 text-[11px] text-ink-400">
          演示渠道走 <code className="text-ink-500">POST /product/checkout</code>
          （账本+权益）；生产网关用 webhook 幂等履约，见运营看板。
        </p>
      </SectionCard>

      <div className="grid gap-4 md:grid-cols-2">
        <SectionCard
          title={PLAN_COPY.free.name}
          borderLeft="ink"
          className={ent.plan === "free" ? "ring-1 ring-ink-300/40" : ""}
        >
          <p className="mb-3 text-2xl font-display text-ink-700 dark:text-ink-200">
            {yuan(1900)}
            <span className="ml-1 text-xs font-sans text-ink-400">/ 次交付包</span>
          </p>
          <ul className="mb-4 space-y-2 text-sm text-ink-600 dark:text-ink-300">
            {PLAN_COPY.free.features.map((f) => (
              <li key={f} className="flex items-start gap-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-ink-400" />
                {f}
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => void onCheckoutPackage()}
            disabled={busy !== null}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-ink-300/40 bg-ink-100/50 py-2.5 text-sm font-medium text-ink-700 transition hover:bg-ink-200/60 disabled:opacity-50 dark:border-ink-600 dark:bg-ink-800 dark:text-ink-200"
          >
            <CreditCard className="h-4 w-4" />
            {busy === "checkout-pkg" ? "支付中…" : "收银台 · 购买 1 次"}
          </button>
        </SectionCard>

        <SectionCard
          title={
            <>
              <Sparkles className="mr-1.5 inline h-4 w-4 text-gold" />
              {PLAN_COPY.pro.name}
            </>
          }
          borderLeft="gold"
          className={ent.plan === "pro" ? "ring-1 ring-gold/40" : ""}
        >
          <p className="mb-3 text-2xl font-display text-gold">
            {yuan(9900)}
            <span className="ml-1 text-xs font-sans text-ink-400">/ 30 天</span>
          </p>
          <ul className="mb-4 space-y-2 text-sm text-ink-600 dark:text-ink-300">
            {PLAN_COPY.pro.features.map((f) => (
              <li key={f} className="flex items-start gap-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                {f}
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => void onCheckoutPro()}
            disabled={busy !== null}
            className="btn-primary flex w-full items-center justify-center gap-2 disabled:opacity-50"
          >
            <CreditCard className="h-4 w-4" />
            {busy === "checkout-pro" ? "支付中…" : "收银台 · 开通 30 天"}
          </button>
          <button
            type="button"
            onClick={() => void onProDemoCode()}
            disabled={busy !== null}
            className="mt-2 w-full text-center text-[11px] text-ink-400 underline hover:text-vermilion disabled:opacity-50"
          >
            或使用演示码 demo-pro（无账本）
          </button>
        </SectionCard>
      </div>

      <SectionCard title="我的订单（服务端账本）">
        {payments.length === 0 ? (
          <p className="text-sm text-ink-400">暂无支付记录。走上方收银台后会出现在这里。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-ink-300/20 text-ink-400">
                  <th className="py-2 pr-2">时间</th>
                  <th className="py-2 pr-2">商品</th>
                  <th className="py-2 pr-2">金额</th>
                  <th className="py-2 pr-2">状态</th>
                  <th className="py-2">订单号</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr
                    key={p.id}
                    className="border-b border-ink-300/10 text-ink-600 dark:text-ink-300"
                  >
                    <td className="py-2 pr-2 whitespace-nowrap">
                      {p.created_at
                        ? new Date(p.created_at * 1000).toLocaleString()
                        : "—"}
                    </td>
                    <td className="py-2 pr-2">{p.product}</td>
                    <td className="py-2 pr-2">{yuan(p.amount_cents)}</td>
                    <td className="py-2 pr-2 text-jade">{p.status}</td>
                    <td className="py-2 font-mono text-[10px] text-ink-400">
                      {p.external_id?.slice(0, 18)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <p className="text-center text-xs text-ink-400">
        <Link to="/" className="text-vermilion underline">
          返回人生主页
        </Link>
        {" · "}
        <Link to="/admin" className="text-ink-500 underline">
          运营看板
        </Link>
        {" · "}
        结构层免费可见；交付包按权益开放
      </p>
    </div>
  );
}
