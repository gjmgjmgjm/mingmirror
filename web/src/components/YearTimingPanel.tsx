import type { YearTimingSurface } from "../api/client";
import { SectionCard } from "./ui";

const MODE_BADGE: Record<string, { label: string; className: string }> = {
  hard_shortlist: {
    label: "结构应期",
    className: "bg-jade/15 text-jade dark:bg-jade/20",
  },
  soft_hint: {
    label: "参考候选",
    className: "bg-gold/15 text-gold dark:bg-gold/20",
  },
  trend_only: {
    label: "仅趋势",
    className: "bg-ink-200/80 text-ink-600 dark:bg-ink-700 dark:text-ink-300",
  },
  unavailable: {
    label: "不可用",
    className: "bg-ink-100 text-ink-500 dark:bg-ink-800 dark:text-ink-400",
  },
};

/**
 * Product honesty panel for year/应期: never asserts a single year.
 * Optionally shows 六亲流年象征取样 bridged from liuqin_dossier.
 */
export default function YearTimingPanel({
  surface,
  delay = 160,
}: {
  surface?: YearTimingSurface | null;
  delay?: number;
}) {
  if (!surface || surface.display_mode === "unavailable") {
    return null;
  }

  const bridge = surface.meta?.liuqin_bridge;
  const bridgeSamples = bridge?.samples || [];
  const hasBridge = bridgeSamples.length > 0;

  // Hide empty trend for generic questions with no year intent / no bridge.
  if (
    surface.display_mode === "trend_only" &&
    !surface.product_copy &&
    !(surface.candidates && surface.candidates.length) &&
    !hasBridge
  ) {
    return null;
  }

  // Still hide pure empty trend_only without useful copy/bridge
  if (
    surface.display_mode === "trend_only" &&
    !hasBridge &&
    !(surface.candidates && surface.candidates.length) &&
    !surface.product_copy
  ) {
    return null;
  }

  const badge = MODE_BADGE[surface.display_mode] || MODE_BADGE.trend_only;
  const cands = surface.candidates || [];
  const showTable =
    (surface.display_mode === "hard_shortlist" ||
      surface.display_mode === "soft_hint") &&
    cands.length > 0;

  return (
    <SectionCard
      title={
        <span className="inline-flex items-center gap-2">
          {surface.product_title || "结构应期"}
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}
          >
            {badge.label}
          </span>
          {hasBridge ? (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300">
              六亲联动
            </span>
          ) : null}
        </span>
      }
      delay={delay}
    >
      {surface.product_copy && (
        <p className="mb-3 text-sm leading-relaxed text-ink-600 dark:text-ink-300">
          {surface.product_copy}
        </p>
      )}

      {showTable && (
        <div className="overflow-x-auto rounded-lg border border-ink-200/60 dark:border-ink-600/40">
          <table className="w-full min-w-[320px] text-left text-sm">
            <thead className="bg-ink-100/60 text-xs text-ink-500 dark:bg-ink-800/60 dark:text-ink-400">
              <tr>
                <th className="px-3 py-2 font-medium">候选</th>
                <th className="px-3 py-2 font-medium">干支</th>
                <th className="px-3 py-2 font-medium">分</th>
                <th className="px-3 py-2 font-medium">置信</th>
                <th className="px-3 py-2 font-medium">信号</th>
              </tr>
            </thead>
            <tbody>
              {cands.map((c, i) => (
                <tr
                  key={`${c.year}-${c.option_letter}-${i}`}
                  className={`border-t border-ink-200/40 dark:border-ink-600/30 ${
                    c.liuqin_overlap
                      ? "bg-amber-500/5 dark:bg-amber-500/10"
                      : ""
                  }`}
                >
                  <td className="px-3 py-2 font-medium text-ink-800 dark:text-ink-100">
                    {c.option_letter ? `${c.option_letter} ` : ""}
                    {c.year || "—"}
                    {c.liuqin_overlap ? (
                      <span className="ml-1 text-[10px] font-normal text-amber-700 dark:text-amber-300">
                        六亲重合
                      </span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-ink-700 dark:text-ink-200">
                    {c.gan_zhi || "—"}
                  </td>
                  <td className="px-3 py-2 tabular-nums text-ink-600 dark:text-ink-300">
                    {typeof c.score === "number" ? c.score.toFixed(2) : "—"}
                  </td>
                  <td className="px-3 py-2 text-ink-600 dark:text-ink-300">
                    {c.confidence || "—"}
                  </td>
                  <td className="px-3 py-2 text-xs text-ink-500 dark:text-ink-400">
                    {(c.reasons || []).slice(0, 3).join("；") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {surface.display_mode === "trend_only" && !showTable && (
        <p className="rounded-lg border border-dashed border-ink-300/50 bg-ink-50/50 px-3 py-2 text-sm text-ink-600 dark:border-ink-600/40 dark:bg-ink-900/30 dark:text-ink-300">
          不展示具体公历年。请结合大运流年与上方领域分析理解趋势，勿当作「必在某年」的断言。
        </p>
      )}

      {hasBridge && (
        <div className="mt-3">
          <p className="mb-1.5 text-xs font-medium text-ink-500 dark:text-ink-400">
            六亲流年象征取样
            <span className="ml-1 font-normal text-ink-400">
              （与细断联动 · 非断言）
            </span>
          </p>
          <div className="flex flex-wrap gap-2">
            {bridgeSamples.slice(0, 8).map((s, i) => {
              const overlapped =
                s.year != null &&
                (bridge?.overlap_years || []).includes(Number(s.year));
              return (
                <span
                  key={i}
                  className={`rounded-lg px-2.5 py-1 text-xs ${
                    overlapped
                      ? "bg-jade/15 text-ink-700 dark:bg-jade/20 dark:text-ink-200"
                      : "bg-amber-500/10 text-ink-700 dark:bg-amber-500/15 dark:text-ink-200"
                  }`}
                  title={s.note}
                >
                  <span className="font-semibold text-amber-700 dark:text-amber-300">
                    {s.member_label} {s.year}年 {s.pillar}
                  </span>
                  {s.age != null && (
                    <span className="ml-1 text-ink-400">约{s.age}岁</span>
                  )}
                  {overlapped && (
                    <span className="ml-1 text-jade">· 应期重合</span>
                  )}
                </span>
              );
            })}
          </div>
          {bridge?.honesty && (
            <p className="mt-2 text-[11px] leading-relaxed text-ink-400">
              {bridge.honesty}
            </p>
          )}
        </div>
      )}

      {surface.disclaimer && (
        <p className="mt-3 text-xs leading-relaxed text-ink-500 dark:text-ink-400">
          {surface.disclaimer}
        </p>
      )}
    </SectionCard>
  );
}
