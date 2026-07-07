import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, AlertCircle } from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import { analyzeYearly, fetchBaziTimeline, type BaziTimelineResponse } from "../api/client";
import ChartLoader from "../components/ChartLoader";

function formatAge(age: number): string {
  const years = Math.floor(age);
  const months = Math.round((age - years) * 12);
  if (months === 0) return `${years}岁`;
  return `${years}岁${months}个月`;
}

interface YearlyResult {
  dayun_summary?: Array<{
    pillar: string;
    start_age: number;
    end_age: number;
    theme: string;
    focus: string;
  }>;
  yearly_analysis?: Array<{
    year: number;
    pillar: string;
    overview: string;
    key_event: string;
    career: string;
    wealth: string;
    marriage: string;
    health: string;
    caution: string;
  }>;
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

export default function YearlyChart() {
  const { chart } = useChart();
  const [mode, setMode] = useState<"10y" | "20y" | "lifetime">("10y");
  const [timeline, setTimeline] = useState<BaziTimelineResponse | null>(null);
  const [result, setResult] = useState<YearlyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasBirthInfo = Boolean(
    chart?.birthDate && chart.gender && chart.birthTime
  );

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
  }, [chart, mode]);

  const handleAnalyze = async () => {
    if (!chart) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await analyzeYearly(
        chart.bazi,
        chart.gender,
        chart.birthDate || "",
        chart.birthTime || "00:00",
        chart.calendarType || "solar",
        mode
      );
      setResult((data.result as YearlyResult) || null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "流年分析失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  if (!chart) {
    return (
      <div className="panel mx-auto max-w-2xl p-8 text-center">
        <h2 className="mb-4 text-2xl font-semibold text-ink-700 dark:text-ink-200">
          暂无命盘
        </h2>
        <p className="mb-6 text-ink-600 dark:text-ink-400">
          请先在首页输入八字信息，然后再进行流年精排。
        </p>
        <Link to="/" className="btn-primary inline-flex">
          前往首页
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section className="panel p-6 md:p-8">
        <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="font-display text-3xl text-ink-800 dark:text-ink-100">
              流年精排
            </h1>
            <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
              结合大运与流年，推演未来运势走势
            </p>
          </div>
          <div className="inline-flex rounded-xl border border-ink-300/40 bg-ink-100/50 p-1 dark:border-ink-500/40 dark:bg-ink-800/50">
            {[
              { value: "10y", label: "未来10年" },
              { value: "20y", label: "未来20年" },
              { value: "lifetime", label: "看到80岁" },
            ].map((m) => (
              <button
                key={m.value}
                type="button"
                onClick={() => setMode(m.value as "10y" | "20y" | "lifetime")}
                className={`rounded-lg px-4 py-1.5 text-sm transition ${
                  mode === m.value
                    ? "bg-white text-ink-800 shadow-sm dark:bg-ink-700 dark:text-ink-100"
                    : "text-ink-500 dark:text-ink-400"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {!hasBirthInfo && (
          <div className="mb-4 flex items-start gap-3 rounded-xl bg-gold/10 p-4 text-sm text-gold dark:bg-gold/20">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              当前缺少准确的出生时间或性别，流年与大运按“0岁起运”近似计算。如需精确排盘，请返回首页重新输入。
            </div>
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
          onClick={handleAnalyze}
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
              <span className="relative">生成流年精排</span>
            </>
          )}
        </button>
      </section>

      {loading && <ChartLoader />}

      {error && (
        <div className="panel border-l-4 border-l-vermilion p-6 text-vermilion dark:border-l-vermilion-light">
          <p className="font-medium">分析出错</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {result?.error && (
        <div className="panel border-l-4 border-l-vermilion p-6 text-vermilion dark:border-l-vermilion-light">
          <p className="font-medium">{result.error}</p>
        </div>
      )}

      {result && !result.error && (
        <div className="space-y-6">
          {result.dayun_summary && result.dayun_summary.length > 0 && (
            <section className="panel p-6 animate-chart-section">
              <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
                大运主题
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {result.dayun_summary.map((d, idx) => (
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
            </section>
          )}

          {result.liuqin_analysis && (
            <section className="panel border-l-4 border-l-jade p-6 animate-chart-section">
              <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
                六亲断语
              </h2>
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
                          <h3 className="mb-1 font-semibold text-ink-800 dark:text-ink-100">{titles[key] || key}</h3>
                          <p className="whitespace-pre-line text-sm text-ink-700 dark:text-ink-200">{value}</p>
                        </div>
                      );
                    }
                    return (
                      <div key={key}>
                        <h3 className="mb-1 font-semibold text-ink-800 dark:text-ink-100">{titles[key] || key}</h3>
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
                              <p key={subKey} className="text-sm text-ink-700 dark:text-ink-200">
                                <span className="font-medium">{subTitles[subKey] || subKey}：</span>
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
            </section>
          )}

          {result.milestones && result.milestones.length > 0 && (
            <section className="panel border-l-4 border-l-gold p-6 animate-chart-section">
              <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
                人生节点时间线
              </h2>
              <div className="flex flex-wrap gap-3">
                {result.milestones.map((m, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-3 dark:border-ink-500/20 dark:bg-ink-800/40"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-vermilion">{m.year}年</span>
                      <span className="text-xs text-ink-500 dark:text-ink-400">({m.age}岁)</span>
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
            </section>
          )}

          {result.yearly_analysis && result.yearly_analysis.length > 0 && (
            <section className="panel p-6 animate-chart-section">
              <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
                逐年流年
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {result.yearly_analysis.map((y, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40"
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-lg font-bold text-ink-800 dark:text-ink-100">
                        {y.year}年
                      </span>
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
                ))}
              </div>
            </section>
          )}

          {result.overall_guidance && (
            <section className="panel relative overflow-hidden p-6 animate-chart-section">
              <div className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-gold/10 blur-2xl" />
              <h2 className="mb-2 text-xl font-semibold text-ink-700 dark:text-ink-200">
                综合建议
              </h2>
              <p className="leading-relaxed text-ink-700 dark:text-ink-200">
                {result.overall_guidance}
              </p>
            </section>
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
              <section className="panel border-l-4 border-l-gold p-6 animate-chart-section">
                <h2 className="mb-2 text-lg font-semibold text-ink-700 dark:text-ink-200">
                  注意事项
                </h2>
                <ul className="list-inside list-disc space-y-1 text-sm text-ink-600 dark:text-ink-300">
                  {visibleCaveats.map((c, idx) => (
                    <li key={idx}>{c}</li>
                  ))}
                </ul>
              </section>
            ) : null;
          })()}

          <style>{`
            @keyframes chart-section-enter {
              0% { opacity: 0; transform: translateY(16px); }
              100% { opacity: 1; transform: translateY(0); }
            }
            .animate-chart-section {
              opacity: 0;
              animation: chart-section-enter 0.5s ease-out forwards;
            }
          `}</style>
        </div>
      )}
    </div>
  );
}
