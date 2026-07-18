import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Sparkles } from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import {
  analyzeQizhengYearly,
  type QizhengYearlyItem,
  type QizhengYearlyResult,
} from "../api/client";
import ChartLoader from "../components/ChartLoader";
import {
  SectionCard,
  EmptyState,
  ToggleGroup,
  PageHeader,
  ErrorPanel,
  InfoCard,
} from "../components/ui";

function formatAge(age: number): string {
  const years = Math.floor(age);
  const months = Math.round((age - years) * 12);
  if (months === 0) return `${years}岁`;
  return `${years}岁${months}个月`;
}

function parseBirthYear(birthDate?: string): number {
  if (!birthDate) return 0;
  const year = Number(birthDate.split("-")[0]);
  return Number.isNaN(year) ? 0 : year;
}

function groupByPalace(years: QizhengYearlyItem[]): Array<{
  palace: string;
  years: QizhengYearlyItem[];
}> {
  const order: string[] = [];
  const map = new Map<string, QizhengYearlyItem[]>();
  for (const y of years) {
    const key = y.active_palace || "未分宫";
    if (!map.has(key)) {
      map.set(key, []);
      order.push(key);
    }
    map.get(key)!.push(y);
  }
  return order.map((palace) => ({ palace, years: map.get(palace)! }));
}

const DIGNITY_OPTIONS: { value: "default" | "yang"; label: string }[] = [
  { value: "default", label: "默认庙旺表" },
  { value: "yang", label: "杨国正派" },
];

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

function YearlyDetailCard({
  y,
  isNow,
}: {
  y: QizhengYearlyItem;
  isNow: boolean;
}) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        isNow
          ? "border-gold bg-gold/10"
          : "border-ink-300/20 bg-ink-100/40 dark:border-ink-500/20 dark:bg-ink-800/40"
      }`}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold text-ink-800 dark:text-ink-100">
            {y.year}年
          </span>
          {isNow && (
            <span className="rounded bg-gold px-1.5 py-0.5 text-[10px] text-white">
              今年
            </span>
          )}
        </div>
        <span className="rounded-lg bg-vermilion/10 px-2 py-0.5 text-sm font-bold text-vermilion dark:bg-vermilion/20">
          {y.pillar}
        </span>
      </div>

      {(y.active_palace || y.palace_lord) && (
        <div className="mb-2 flex flex-wrap gap-2 text-[11px] text-ink-500">
          {y.active_palace && (
            <span className="rounded bg-ink-200/50 px-1.5 py-0.5 dark:bg-ink-700/50">
              大限{y.active_palace}
            </span>
          )}
          {y.palace_lord && (
            <span className="rounded bg-ink-200/50 px-1.5 py-0.5 dark:bg-ink-700/50">
              宫主{y.palace_lord}
              {y.strongest_star?.strength
                ? `·${y.strongest_star.strength}`
                : ""}
            </span>
          )}
          {y.palace_lord_relation && (
            <span className="rounded bg-ink-200/50 px-1.5 py-0.5 dark:bg-ink-700/50">
              {y.palace_lord_relation}
            </span>
          )}
        </div>
      )}

      <p className="mb-2 text-sm font-medium text-ink-700 dark:text-ink-200">
        {y.overview}
      </p>
      {y.star_impact && (
        <p className="mb-2 text-xs leading-relaxed text-ink-500 dark:text-ink-400">
          {y.star_impact}
        </p>
      )}
      {y.taishui_impact && (
        <p className="mb-2 text-xs text-gold">{y.taishui_impact}</p>
      )}
      <ul className="space-y-1 text-xs text-ink-600 dark:text-ink-300">
        <li>事业：{y.career}</li>
        <li>财运：{y.wealth}</li>
        <li>感情：{y.marriage}</li>
        <li>健康：{y.health}</li>
      </ul>
      {(y.four_remainder_note || y.pattern_note) && (
        <p className="mt-2 text-[11px] text-ink-400">
          {[y.four_remainder_note, y.pattern_note].filter(Boolean).join(" · ")}
        </p>
      )}
      {y.caution && (
        <p className="mt-2 text-xs text-vermilion">注意：{y.caution}</p>
      )}
    </div>
  );
}

export default function QizhengYearly() {
  const { chart } = useChart();
  const [mode, setMode] = useState<"10y" | "lifetime">("10y");
  const [dignityTable, setDignityTable] = useState<"default" | "yang">("default");
  const [result, setResult] = useState<QizhengYearlyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedYear, setExpandedYear] = useState<number | null>(null);
  const [openPalace, setOpenPalace] = useState<string | null>(null);

  const birthYear = parseBirthYear(chart?.birthDate);
  const hasBirthInfo = Boolean(chart?.gender && birthYear > 0);
  const currentYear = new Date().getFullYear();

  const runAnalyze = useCallback(
    async (nextMode: "10y" | "lifetime", nextDignity: "default" | "yang") => {
      if (!chart) return;
      setLoading(true);
      setError(null);
      try {
        const data = await analyzeQizhengYearly(
          chart.bazi,
          chart.gender || "male",
          birthYear || currentYear,
          nextMode,
          nextDignity
        );
        setResult(data.result || null);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "七政大运流年分析失败";
        setError(message);
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [chart, birthYear, currentYear]
  );

  // Auto-load structural yearly on mount / chart / mode / dignity change
  useEffect(() => {
    if (!chart) return;
    void runAnalyze(mode, dignityTable);
  }, [chart?.bazi, chart?.gender, chart?.birthDate, mode, dignityTable, runAnalyze]);

  const structural = result?.structural_summary;
  const yearly = result?.yearly_analysis || [];
  const dayun = result?.dayun_summary || [];
  const palaceGroups = useMemo(() => groupByPalace(yearly), [yearly]);

  // Default open palace group containing current year (lifetime mode)
  useEffect(() => {
    if (mode !== "lifetime" || yearly.length === 0) return;
    const hit = yearly.find((y) => y.year === currentYear);
    if (hit?.active_palace) {
      setOpenPalace(hit.active_palace);
      setExpandedYear(currentYear);
    } else {
      setOpenPalace(palaceGroups[0]?.palace ?? null);
    }
  }, [mode, yearly, currentYear, palaceGroups]);

  if (!chart) {
    return (
      <EmptyState
        title="暂无命盘"
        description="请先在首页输入八字信息，然后再进行七政大运流年精排。"
        action={
          <Link to="/" className="btn-primary inline-flex">
            前往首页
          </Link>
        }
      />
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <SectionCard>
        <PageHeader
          title="七政大运流年"
          subtitle="大限宫位 × 流年干支 × 宫主星庙旺（结构层优先，AI 可选增强）"
          action={
            <div className="flex flex-wrap items-center gap-3">
              <Link to="/qizheng" className="btn-secondary text-sm">
                返回命盘
              </Link>
              <select
                value={dignityTable}
                onChange={(e) =>
                  setDignityTable(e.target.value as "default" | "yang")
                }
                className="input text-sm"
              >
                {DIGNITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <ToggleGroup
                options={[
                  { value: "10y", label: "未来10年" },
                  { value: "lifetime", label: "看到80岁" },
                ]}
                value={mode}
                onChange={setMode}
              />
            </div>
          }
        />

        {!hasBirthInfo && (
          <div className="mb-4 flex items-start gap-3 rounded-xl bg-gold/10 p-4 text-sm text-gold dark:bg-gold/20">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              当前缺少准确的出生年份或性别，大运与流年按近似计算。如需精确排盘，请返回首页重新输入。
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void runAnalyze(mode, dignityTable)}
            disabled={loading}
            className="btn-primary btn-shimmer disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <span className="relative mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                <span className="relative">精排中</span>
              </>
            ) : (
              <>
                <Sparkles className="relative mr-2 h-4 w-4" />
                <span className="relative">重新生成</span>
              </>
            )}
          </button>
          {result?.trust && (
            <span className="rounded-lg bg-ink-200/60 px-2.5 py-1 text-xs text-ink-600 dark:bg-ink-700/60 dark:text-ink-300">
              可信度标签 · {result.trust}
              {result.confidence
                ? ` · 置信 ${CONFIDENCE_LABELS[result.confidence] || result.confidence}`
                : ""}
              {result._rule_based ? " · 规则结构层" : ""}
            </span>
          )}
        </div>
        {result?.note && (
          <p className="mt-3 text-xs leading-relaxed text-ink-400">{result.note}</p>
        )}
      </SectionCard>

      {loading && !result && <ChartLoader />}

      {error && <ErrorPanel title="分析出错">{error}</ErrorPanel>}

      {result?.error && <ErrorPanel>{result.error}</ErrorPanel>}

      {result && !result.error && (
        <div className="space-y-6">
          {structural && (
            <SectionCard title="结构摘要" delay={0} borderLeft="gold">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <InfoCard label="日主" value={structural.day_master || "—"} />
                <InfoCard label="命宫" value={structural.life_palace || "—"} />
                <InfoCard label="身宫" value={structural.body_palace || "—"} />
                <InfoCard label="身主" value={structural.body_lord || "—"} />
                <InfoCard
                  label="五行局"
                  value={structural.five_element_pattern || "—"}
                />
                <InfoCard
                  label="范围"
                  value={`${structural.dayun_count ?? dayun.length} 步大限 · ${
                    structural.liunian_count ?? yearly.length
                  } 流年`}
                />
              </div>
              {(structural.patterns || []).length > 0 && (
                <p className="mt-3 text-xs text-ink-500">
                  格局提示：{(structural.patterns || []).join(" · ")}
                </p>
              )}
            </SectionCard>
          )}

          {dayun.length > 0 && (
            <SectionCard title="大运主题" delay={80}>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {dayun.map((d, idx) => (
                  <div
                    key={`${d.pillar}-${idx}`}
                    className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40"
                  >
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="text-lg font-bold text-vermilion">
                        {d.pillar}
                      </span>
                      <span className="text-xs text-ink-500 dark:text-ink-400">
                        {formatAge(d.start_age)} - {formatAge(d.end_age)}
                      </span>
                    </div>
                    {d.palace && (
                      <p className="mb-1 text-xs text-gold">大限宫 · {d.palace}</p>
                    )}
                    <p className="mb-1 text-sm font-medium text-ink-700 dark:text-ink-200">
                      {d.theme}
                    </p>
                    <p className="text-xs text-ink-500 dark:text-ink-400">
                      {d.focus}
                    </p>
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {yearly.length > 0 && mode === "10y" && (
            <SectionCard title="逐年流年（十年）" delay={160}>
              <p className="mb-3 text-xs text-ink-400">
                每流年标注：所在大限宫、宫主星庙旺、太岁与宫支关系；事业/财运/感情/健康为规则层提示。
              </p>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {yearly.map((y) => (
                  <YearlyDetailCard
                    key={y.year}
                    y={y}
                    isNow={y.year === currentYear}
                  />
                ))}
              </div>
            </SectionCard>
          )}

          {yearly.length > 0 && mode === "lifetime" && (
            <SectionCard title="一生流年（按大限宫压缩）" delay={160}>
              <p className="mb-3 text-xs text-ink-400">
                共 {yearly.length} 年，按大限宫分组折叠；点击年份展开详情。默认展开含「今年」的宫位。
              </p>
              <div className="space-y-3">
                {palaceGroups.map((g) => {
                  const open = openPalace === g.palace;
                  const y0 = g.years[0]?.year;
                  const y1 = g.years[g.years.length - 1]?.year;
                  return (
                    <div
                      key={g.palace}
                      className="rounded-xl border border-ink-300/20 dark:border-ink-600/30"
                    >
                      <button
                        type="button"
                        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left hover:bg-ink-100/40 dark:hover:bg-ink-800/40"
                        onClick={() =>
                          setOpenPalace(open ? null : g.palace)
                        }
                      >
                        <span className="font-medium text-ink-800 dark:text-ink-100">
                          {g.palace}
                          <span className="ml-2 text-xs font-normal text-ink-400">
                            {y0}–{y1} · {g.years.length} 年
                          </span>
                        </span>
                        <span className="text-xs text-ink-400">
                          {open ? "收起" : "展开"}
                        </span>
                      </button>
                      {open && (
                        <div className="border-t border-ink-300/20 px-3 pb-3 dark:border-ink-600/30">
                          <div className="overflow-x-auto">
                            <table className="mt-2 w-full min-w-[28rem] text-left text-xs">
                              <thead>
                                <tr className="text-ink-400">
                                  <th className="py-1 pr-2 font-normal">年</th>
                                  <th className="py-1 pr-2 font-normal">年柱</th>
                                  <th className="py-1 pr-2 font-normal">太岁</th>
                                  <th className="py-1 font-normal">概要</th>
                                </tr>
                              </thead>
                              <tbody>
                                {g.years.map((y) => {
                                  const isNow = y.year === currentYear;
                                  const selected = expandedYear === y.year;
                                  return (
                                    <tr
                                      key={y.year}
                                      className={`cursor-pointer border-t border-ink-300/10 ${
                                        isNow
                                          ? "bg-gold/10"
                                          : selected
                                            ? "bg-vermilion/5"
                                            : "hover:bg-ink-100/50 dark:hover:bg-ink-800/50"
                                      }`}
                                      onClick={() =>
                                        setExpandedYear(
                                          selected ? null : y.year
                                        )
                                      }
                                    >
                                      <td className="py-1.5 pr-2 font-medium text-ink-700 dark:text-ink-200">
                                        {y.year}
                                        {isNow && (
                                          <span className="ml-1 text-[10px] text-gold">
                                            今
                                          </span>
                                        )}
                                      </td>
                                      <td className="py-1.5 pr-2 text-vermilion">
                                        {y.pillar}
                                      </td>
                                      <td className="py-1.5 pr-2 text-ink-500">
                                        {(y.taishui_impact || "").slice(0, 18) ||
                                          "—"}
                                      </td>
                                      <td className="py-1.5 text-ink-500">
                                        {(y.overview || "").slice(0, 36)}
                                        {(y.overview || "").length > 36
                                          ? "…"
                                          : ""}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                          {expandedYear != null &&
                            g.years.some((y) => y.year === expandedYear) && (
                              <div className="mt-3">
                                <YearlyDetailCard
                                  y={
                                    g.years.find(
                                      (y) => y.year === expandedYear
                                    )!
                                  }
                                  isNow={expandedYear === currentYear}
                                />
                              </div>
                            )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </SectionCard>
          )}

          {result.overall_guidance && (
            <SectionCard title="综合建议" delay={240}>
              <div className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-gold/10 blur-2xl" />
              <p className="leading-relaxed text-ink-700 dark:text-ink-200">
                {result.overall_guidance}
              </p>
            </SectionCard>
          )}

          {(() => {
            const techMarkers = [
              "AI ",
              "规则化兜底",
              "无法解析",
              "已切换兜底",
              "服务暂时不可用",
              "原始输出",
            ];
            const visibleCaveats =
              result.caveats?.filter(
                (c) => !techMarkers.some((m) => c.includes(m))
              ) || [];
            return visibleCaveats.length > 0 ? (
              <SectionCard title="注意事项" borderLeft="gold" delay={300}>
                <ul className="list-inside list-disc space-y-1 text-sm text-ink-600 dark:text-ink-300">
                  {visibleCaveats.map((c, idx) => (
                    <li key={idx}>{c}</li>
                  ))}
                </ul>
              </SectionCard>
            ) : null;
          })()}
        </div>
      )}
    </div>
  );
}
