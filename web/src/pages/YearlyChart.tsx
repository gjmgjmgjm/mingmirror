import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, AlertCircle } from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import {
  analyzeYearly,
  fetchBaziTimeline,
  type BaziTimelineResponse,
} from "../api/client";
import ChartLoader from "../components/ChartLoader";
import {
  SectionCard,
  EmptyState,
  ToggleGroup,
  PageHeader,
  ErrorPanel,
} from "../components/ui";

function formatAge(age: number): string {
  const years = Math.floor(age);
  const months = Math.round((age - years) * 12);
  if (months === 0) return `${years}岁`;
  return `${years}岁${months}个月`;
}

interface YearlyItem {
  year: number;
  pillar: string;
  overview: string;
  key_event: string;
  career: string;
  wealth: string;
  marriage: string;
  health: string;
  caution: string;
}

interface DayunSummary {
  pillar: string;
  start_age: number;
  end_age: number;
  theme: string;
  focus: string;
}

interface YearlyResult {
  dayun_summary?: DayunSummary[];
  yearly_analysis?: YearlyItem[];
  liuqin_analysis?:
    | string
    | {
        father?: { star?: string; character?: string; ability?: string; health?: string; relationship?: string };
        mother?: { star?: string; character?: string; ability?: string; health?: string; relationship?: string };
        spouse?: {
          palace?: string;
          star?: string;
          character?: string;
          ability?: string;
          health?: string;
          appearance?: string;
          relationship?: string;
        };
        children?: { overview?: string; sons?: string; daughters?: string; relationship?: string };
        siblings?: { brothers?: string; sisters?: string; relationship?: string };
        family_relations?: string;
      };
  milestones?: Array<{
    year: number;
    age: number;
    type: string;
    description: string;
  }>;
  overall_guidance?: string;
  caveats?: string[];
  error?: string;
}

const SPAN_OPTIONS = [5, 10, 15, 20] as const;

function groupByDayun(
  years: YearlyItem[],
  dayun: DayunSummary[],
  birthYear: number
): Array<{ key: string; label: string; years: YearlyItem[] }> {
  if (!years.length) return [];
  if (!dayun.length || !birthYear) {
    // fallback: decade buckets
    const order: string[] = [];
    const map = new Map<string, YearlyItem[]>();
    for (const y of years) {
      const decade = `${Math.floor(y.year / 10) * 10}s`;
      if (!map.has(decade)) {
        map.set(decade, []);
        order.push(decade);
      }
      map.get(decade)!.push(y);
    }
    return order.map((key) => ({
      key,
      label: `${key} 年代`,
      years: map.get(key)!,
    }));
  }
  const order: string[] = [];
  const map = new Map<string, YearlyItem[]>();
  const unmatched: YearlyItem[] = [];
  for (const y of years) {
    const age = y.year - birthYear;
    const d =
      dayun.find((x) => age >= x.start_age && age < x.end_age) ||
      dayun.find((x) => age >= x.start_age && age <= x.end_age);
    if (!d) {
      unmatched.push(y);
      continue;
    }
    const key = `${d.pillar}-${d.start_age}`;
    if (!map.has(key)) {
      map.set(key, []);
      order.push(key);
    }
    map.get(key)!.push(y);
  }
  const groups = order.map((key) => {
    const rows = map.get(key)!;
    const d = dayun.find(
      (x) => `${x.pillar}-${x.start_age}` === key
    );
    return {
      key,
      label: d
        ? `${d.pillar}大运（${formatAge(d.start_age)}–${formatAge(d.end_age)}）`
        : key,
      years: rows,
    };
  });
  if (unmatched.length) {
    groups.push({ key: "other", label: "其他", years: unmatched });
  }
  return groups;
}

function YearDetailCard({ y, isNow }: { y: YearlyItem; isNow: boolean }) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        isNow
          ? "border-gold bg-gold/10"
          : "border-ink-300/20 bg-ink-100/40 dark:border-ink-500/20 dark:bg-ink-800/40"
      }`}
    >
      <div className="mb-2 flex items-center justify-between">
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
      {y.key_event && (
        <div className="mb-2 rounded-lg bg-gold/10 px-2 py-1 text-xs font-medium text-gold dark:bg-gold/20">
          {y.key_event}
        </div>
      )}
      <p className="mb-2 text-sm font-medium text-ink-700 dark:text-ink-200">
        {y.overview}
      </p>
      <ul className="space-y-1 text-xs text-ink-600 dark:text-ink-300">
        <li>事业：{y.career}</li>
        <li>财运：{y.wealth}</li>
        <li>感情：{y.marriage}</li>
        <li>健康：{y.health}</li>
      </ul>
      {y.caution && (
        <p className="mt-2 text-xs text-vermilion">注意：{y.caution}</p>
      )}
    </div>
  );
}

export default function YearlyChart() {
  const { chart } = useChart();
  const currentYear = new Date().getFullYear();
  const [mode, setMode] = useState<"10y" | "20y" | "lifetime" | "custom">("10y");
  const [startYear, setStartYear] = useState(currentYear);
  const [spanYears, setSpanYears] =
    useState<(typeof SPAN_OPTIONS)[number]>(10);
  const [timeline, setTimeline] = useState<BaziTimelineResponse | null>(null);
  const [result, setResult] = useState<YearlyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedYear, setExpandedYear] = useState<number | null>(null);
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  const hasBirthInfo = Boolean(
    chart?.birthDate && chart.gender && chart.birthTime
  );
  const birthYear = chart?.birthDate
    ? Number(chart.birthDate.split("-")[0]) || 0
    : 0;

  const runAnalyze = useCallback(async () => {
    if (!chart) return;
    setLoading(true);
    setError(null);
    try {
      const custom = mode === "custom";
      const apiMode =
        mode === "custom" ? "10y" : mode === "lifetime" ? "lifetime" : mode;
      const data = await analyzeYearly(
        chart.bazi,
        chart.gender,
        chart.birthDate || "",
        chart.birthTime || "00:00",
        chart.calendarType || "solar",
        apiMode,
        custom
          ? { start_year: startYear, years: spanYears }
          : mode === "10y"
            ? { start_year: startYear, years: 10 }
            : mode === "20y"
              ? { start_year: startYear, years: 20 }
              : undefined
      );
      setResult((data.result as YearlyResult) || null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "流年分析失败";
      setError(message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [chart, mode, startYear, spanYears]);

  useEffect(() => {
    if (!chart) return;
    fetchBaziTimeline(
      chart.bazi,
      chart.gender,
      chart.birthDate || "",
      chart.birthTime || "00:00",
      chart.calendarType || "solar",
      80
    )
      .then(setTimeline)
      .catch(() => setTimeline(null));
  }, [chart?.bazi, chart?.gender, chart?.birthDate, chart?.birthTime]);

  // Auto-load structural yearly
  useEffect(() => {
    if (!chart) return;
    void runAnalyze();
  }, [chart?.bazi, chart?.gender, chart?.birthDate, mode, startYear, spanYears, runAnalyze]);

  const yearly = result?.yearly_analysis || [];
  const dayun = result?.dayun_summary || [];
  const groups = useMemo(
    () => groupByDayun(yearly, dayun, birthYear),
    [yearly, dayun, birthYear]
  );

  useEffect(() => {
    if (mode !== "lifetime" || yearly.length === 0) return;
    const hit = yearly.find((y) => y.year === currentYear);
    if (hit) {
      setExpandedYear(currentYear);
      const g = groups.find((x) => x.years.some((y) => y.year === currentYear));
      setOpenGroup(g?.key ?? groups[0]?.key ?? null);
    } else {
      setOpenGroup(groups[0]?.key ?? null);
    }
  }, [mode, yearly, currentYear, groups]);

  if (!chart) {
    return (
      <EmptyState
        title="暂无命盘"
        description="请先在首页输入八字信息，然后再进行流年精排。"
        action={
          <Link to="/" className="btn-primary inline-flex">
            前往首页
          </Link>
        }
      />
    );
  }

  const isLifetime = mode === "lifetime";
  const compact = isLifetime || yearly.length > 15;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <SectionCard>
        <PageHeader
          title="流年精排"
          subtitle="结合大运与流年，推演运势走势 · 结构层优先"
          action={
            <ToggleGroup
              options={[
                { value: "10y", label: "未来10年" },
                { value: "20y", label: "未来20年" },
                { value: "lifetime", label: "看到80岁" },
                { value: "custom", label: "自定义" },
              ]}
              value={mode}
              onChange={(v) => setMode(v as typeof mode)}
            />
          }
        />

        {!hasBirthInfo && (
          <div className="mb-4 flex items-start gap-3 rounded-xl bg-gold/10 p-4 text-sm text-gold dark:bg-gold/20">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              当前缺少准确的出生时间或性别，流年与大运按“0岁起运”近似计算。如需精确排盘，请返回首页重新输入。
            </div>
          </div>
        )}

        {(mode === "custom" || mode === "10y" || mode === "20y") && (
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <label className="text-xs text-ink-500">
              起始年
              <input
                type="number"
                className="input mt-1 w-28 text-sm"
                value={startYear}
                min={1900}
                max={2100}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (!Number.isNaN(v)) setStartYear(v);
                }}
              />
            </label>
            {mode === "custom" && (
              <label className="text-xs text-ink-500">
                跨度
                <select
                  className="input mt-1 w-28 text-sm"
                  value={spanYears}
                  onChange={(e) =>
                    setSpanYears(
                      Number(e.target.value) as (typeof SPAN_OPTIONS)[number]
                    )
                  }
                >
                  {SPAN_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n} 年
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button
              type="button"
              className="btn-secondary text-xs"
              onClick={() => setStartYear(currentYear)}
            >
              回到今年
            </button>
          </div>
        )}

        {timeline && timeline.dayun.length > 0 && (
          <div className="mb-6">
            <h2 className="mb-3 text-sm font-medium text-ink-600 dark:text-ink-300">
              大运时间轴
            </h2>
            <div className="flex gap-3 overflow-x-auto pb-2">
              {timeline.dayun.map((d) => (
                <div
                  key={d.index}
                  className="shrink-0 rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 text-center dark:border-ink-500/20 dark:bg-ink-800/40"
                >
                  <div className="text-lg font-bold text-vermilion">{d.pillar}</div>
                  <div className="text-xs text-ink-500 dark:text-ink-400">
                    {formatAge(d.start_age)} - {formatAge(d.end_age)}
                  </div>
                  {d.start_year && d.end_year && (
                    <div className="text-xs text-ink-400 dark:text-ink-500">
                      {d.start_year}-{d.end_year}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={() => void runAnalyze()}
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
      </SectionCard>

      {loading && !result && <ChartLoader />}

      {error && <ErrorPanel title="分析出错">{error}</ErrorPanel>}

      {result?.error && <ErrorPanel>{result.error}</ErrorPanel>}

      {result && !result.error && (
        <div className="space-y-6">
          {dayun.length > 0 && (
            <SectionCard title="大运主题" delay={0}>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {dayun.map((d, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40"
                  >
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-lg font-bold text-vermilion">
                        {d.pillar}
                      </span>
                      <span className="text-xs text-ink-500 dark:text-ink-400">
                        {formatAge(d.start_age)} - {formatAge(d.end_age)}
                      </span>
                    </div>
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

          {result.liuqin_analysis && (
            <SectionCard title="六亲断语" borderLeft="jade" delay={150}>
              {typeof result.liuqin_analysis === "string" ? (
                <div className="space-y-2">
                  {result.liuqin_analysis.split("\n").map((line, idx) => {
                    const trimmed = line.trim();
                    if (!trimmed) return null;
                    return (
                      <p key={idx} className="text-ink-700 dark:text-ink-200">
                        {trimmed}
                      </p>
                    );
                  })}
                </div>
              ) : (
                <div className="space-y-5">
                  {Object.entries(result.liuqin_analysis).map(([key, value]) => {
                    const titles: Record<string, string> = {
                      father: "父亲",
                      mother: "母亲",
                      spouse: "配偶",
                      children: "子女",
                      siblings: "兄弟姐妹",
                      family_relations: "六亲之间的关系",
                    };
                    if (!value) return null;
                    if (typeof value === "string") {
                      return (
                        <div key={key}>
                          <h3 className="mb-1 font-semibold text-ink-800 dark:text-ink-100">
                            {titles[key] || key}
                          </h3>
                          <p className="whitespace-pre-line text-sm text-ink-700 dark:text-ink-200">
                            {value}
                          </p>
                        </div>
                      );
                    }
                    return (
                      <div key={key}>
                        <h3 className="mb-1 font-semibold text-ink-800 dark:text-ink-100">
                          {titles[key] || key}
                        </h3>
                        <div className="space-y-0.5">
                          {Object.entries(value).map(([subKey, subValue]) => {
                            if (!subValue) return null;
                            const subTitles: Record<string, string> = {
                              star: "星宫",
                              palace: "夫妻宫",
                              character: "性格",
                              ability: "能力",
                              health: "健康",
                              appearance: "外貌",
                              relationship: "与命主关系",
                              overview: "子女总体判断",
                              sons: "儿子",
                              daughters: "女儿",
                              brothers: "兄弟",
                              sisters: "姐妹",
                            };
                            return (
                              <p
                                key={subKey}
                                className="text-sm text-ink-700 dark:text-ink-200"
                              >
                                <span className="font-medium">
                                  {subTitles[subKey] || subKey}：
                                </span>
                                {String(subValue)}
                              </p>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </SectionCard>
          )}

          {result.milestones && result.milestones.length > 0 && (
            <SectionCard title="人生节点时间线" borderLeft="gold" delay={200}>
              <div className="flex flex-wrap gap-3">
                {result.milestones.map((m, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-3 dark:border-ink-500/20 dark:bg-ink-800/40"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-vermilion">{m.year}年</span>
                      <span className="text-xs text-ink-500 dark:text-ink-400">
                        ({m.age}岁)
                      </span>
                    </div>
                    <div className="text-sm font-medium text-ink-700 dark:text-ink-200">
                      {m.type}
                    </div>
                    <div className="text-xs text-ink-500 dark:text-ink-400">
                      {m.description}
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {yearly.length > 0 && !compact && (
            <SectionCard title="逐年流年" delay={300}>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {yearly.map((y) => (
                  <YearDetailCard
                    key={y.year}
                    y={y}
                    isNow={y.year === currentYear}
                  />
                ))}
              </div>
            </SectionCard>
          )}

          {yearly.length > 0 && compact && (
            <SectionCard
              title={
                isLifetime
                  ? "一生流年（按大运压缩）"
                  : `流年列表（${yearly.length} 年 · 压缩）`
              }
              delay={300}
            >
              <p className="mb-3 text-xs text-ink-400">
                共 {yearly.length} 年，按大运折叠；点击年份展开详情。含「今年」的组默认展开。
              </p>
              <div className="space-y-3">
                {groups.map((g) => {
                  const open = openGroup === g.key;
                  const y0 = g.years[0]?.year;
                  const y1 = g.years[g.years.length - 1]?.year;
                  return (
                    <div
                      key={g.key}
                      className="rounded-xl border border-ink-300/20 dark:border-ink-600/30"
                    >
                      <button
                        type="button"
                        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left hover:bg-ink-100/40 dark:hover:bg-ink-800/40"
                        onClick={() => setOpenGroup(open ? null : g.key)}
                      >
                        <span className="font-medium text-ink-800 dark:text-ink-100">
                          {g.label}
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
                                      <td className="py-1.5 text-ink-500">
                                        {(y.overview || "").slice(0, 40)}
                                        {(y.overview || "").length > 40
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
                                <YearDetailCard
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
            <SectionCard title="综合建议" delay={400}>
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
              <SectionCard title="注意事项" borderLeft="gold" delay={500}>
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
