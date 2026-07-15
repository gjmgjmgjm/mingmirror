import { useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, AlertCircle } from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import { analyzeQizhengYearly } from "../api/client";
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
    career: string;
    wealth: string;
    marriage: string;
    health: string;
    caution: string;
  }>;
  overall_guidance?: string;
  caveats?: string[];
  error?: string;
}

function parseBirthYear(birthDate?: string): number {
  if (!birthDate) return 0;
  const year = Number(birthDate.split("-")[0]);
  return Number.isNaN(year) ? 0 : year;
}

const DIGNITY_OPTIONS: { value: "default" | "yang"; label: string }[] = [
  { value: "default", label: "默认庙旺表" },
  { value: "yang", label: "杨国正派" },
];

export default function QizhengYearly() {
  const { chart } = useChart();
  const [mode, setMode] = useState<"10y" | "lifetime">("10y");
  const [dignityTable, setDignityTable] = useState<"default" | "yang">("default");
  const [result, setResult] = useState<YearlyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const birthYear = parseBirthYear(chart?.birthDate);
  const hasBirthInfo = Boolean(chart?.gender && birthYear > 0);

  const handleAnalyze = async () => {
    if (!chart) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await analyzeQizhengYearly(
        chart.bazi,
        chart.gender,
        birthYear,
        mode,
        dignityTable
      );
      setResult((data.result as YearlyResult) || null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "七政大运流年分析失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

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
          subtitle="以七政四余推演大运与流年运势走势"
          action={
            <div className="flex items-center gap-3">
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
              <span className="relative">生成七政大运流年</span>
            </>
          )}
        </button>
      </SectionCard>

      {loading && <ChartLoader />}

      {error && <ErrorPanel title="分析出错">{error}</ErrorPanel>}

      {result?.error && <ErrorPanel>{result.error}</ErrorPanel>}

      {result && !result.error && (
        <div className="space-y-6">
          {result.dayun_summary && result.dayun_summary.length > 0 && (
            <SectionCard title="大运主题" delay={0}>
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
            </SectionCard>
          )}

          {result.yearly_analysis && result.yearly_analysis.length > 0 && (
            <SectionCard title="逐年流年" delay={150}>
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
            </SectionCard>
          )}

          {result.overall_guidance && (
            <SectionCard title="综合建议" delay={300}>
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
              <SectionCard title="注意事项" borderLeft="gold" delay={450}>
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
