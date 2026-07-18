import { useState } from "react";
import { Download, FlaskConical, Heart, Scale } from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import {
  fetchCompatibility,
  type CompatibilityResponse,
} from "../api/client";
import ChartLoader from "../components/ChartLoader";
import {
  SectionCard,
  PageHeader,
  CloudDivider,
  EmptyState,
  ErrorPanel,
} from "../components/ui";
import { Link } from "react-router-dom";
import { track } from "../lib/analytics";

function downloadIcs(ics: string, filename: string) {
  const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function scoreBarColor(score: number): string {
  if (score >= 70) return "bg-jade";
  if (score >= 50) return "bg-gold";
  return "bg-vermilion";
}

function scoreTextColor(score: number): string {
  if (score >= 70) return "text-jade";
  if (score >= 50) return "text-gold";
  return "text-vermilion";
}

export default function Sandbox() {
  const { chart } = useChart();
  const [baziB, setBaziB] = useState("");
  const [genderB, setGenderB] = useState("female");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CompatibilityResponse | null>(null);

  const runCompare = async () => {
    if (!chart) return;
    const partner = baziB.trim().replace(/\s+/g, " ");
    if (partner.split(" ").length < 4) {
      setError("请输入完整四柱八字，例如：甲子 丙寅 戊辰 壬子");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetchCompatibility(
        chart.bazi,
        chart.gender || "male",
        partner,
        genderB,
        { includeJointDays: true, includeIcs: true, eventType: "marriage", topN: 8 }
      );
      setResult(res);
      track("compatibility_run", { score: res.score }, chart.id || chart.bazi);
    } catch (err) {
      setError(err instanceof Error ? err.message : "合婚分析失败");
    } finally {
      setLoading(false);
    }
  };

  if (!chart) {
    return (
      <EmptyState
        title="暂无命盘"
        description="请先在首页输入你的八字，再在沙盒中与对方命盘做合婚对比。"
        action={
          <Link to="/" className="btn-primary inline-flex">
            前往首页
          </Link>
        }
      />
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <PageHeader
        title="命运沙盒 · 合婚"
        subtitle="双盘结构性匹配：用神亲和 · 日干关系 · 地支和谐 · 配偶星 · 旺衰互补"
      />

      <CloudDivider variant="gold" />

      <SectionCard
        title={
          <>
            <Heart className="mr-1.5 inline h-4 w-4 text-vermilion" />
            双方命盘
          </>
        }
        borderLeft="vermilion"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40">
            <div className="mb-1 text-xs text-ink-400">甲方（当前命盘）</div>
            <div className="font-display text-xl text-ink-800 dark:text-ink-100">
              {chart.bazi}
            </div>
            <div className="mt-1 text-xs text-ink-500">
              {chart.gender === "female" ? "女命" : "男命"}
            </div>
          </div>
          <div className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40">
            <div className="mb-2 text-xs text-ink-400">乙方（对方八字）</div>
            <input
              type="text"
              value={baziB}
              onChange={(e) => setBaziB(e.target.value)}
              placeholder="甲子 丙寅 戊辰 壬子"
              className="mb-2 w-full rounded-lg border border-ink-300/30 bg-white/80 px-3 py-2 text-sm text-ink-800 outline-none focus:border-gold dark:border-ink-600 dark:bg-ink-900/60 dark:text-ink-100"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setGenderB("female")}
                className={`rounded-lg px-3 py-1 text-xs ${
                  genderB === "female"
                    ? "bg-vermilion text-white"
                    : "bg-ink-100 text-ink-500 dark:bg-ink-700"
                }`}
              >
                女命
              </button>
              <button
                type="button"
                onClick={() => setGenderB("male")}
                className={`rounded-lg px-3 py-1 text-xs ${
                  genderB === "male"
                    ? "bg-vermilion text-white"
                    : "bg-ink-100 text-ink-500 dark:bg-ink-700"
                }`}
              >
                男命
              </button>
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={runCompare}
          disabled={loading}
          className="btn-primary mt-4 inline-flex items-center gap-2"
        >
          <Scale className="h-4 w-4" />
          {loading ? "分析中…" : "开始合婚对比"}
        </button>
      </SectionCard>

      {loading && <ChartLoader />}
      {error && <ErrorPanel title="合婚出错">{error}</ErrorPanel>}

      {result && (
        <>
          <SectionCard
            title={
              <>
                <FlaskConical className="mr-1.5 inline h-4 w-4 text-gold" />
                合婚指数
              </>
            }
            borderLeft="gold"
          >
            <div className="flex flex-wrap items-end gap-6">
              <div>
                <div
                  className={`font-display text-5xl font-bold ${scoreTextColor(
                    result.score
                  )}`}
                >
                  {result.score}
                </div>
                <div className="mt-1 text-sm text-ink-500">{result.level}</div>
              </div>
              <p className="max-w-xl flex-1 text-sm leading-relaxed text-ink-600 dark:text-ink-300">
                {result.summary}
              </p>
            </div>
          </SectionCard>

          <SectionCard title="分维雷达" borderLeft="jade">
            <div className="space-y-3">
              {result.dimensions.map((d) => (
                <div key={d.key}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="text-ink-600 dark:text-ink-300">
                      {d.label}
                      <span className="ml-1 text-ink-400">
                        (权重 {Math.round(d.weight * 100)}%)
                      </span>
                    </span>
                    <span className={scoreTextColor(d.score)}>{d.score}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-ink-100 dark:bg-ink-800">
                    <div
                      className={`h-full rounded-full ${scoreBarColor(d.score)}`}
                      style={{ width: `${d.score}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          <div className="grid gap-4 sm:grid-cols-2">
            <SectionCard title="助力信号" borderLeft="jade">
              {result.supports.length === 0 ? (
                <p className="text-sm text-ink-400">暂无显著助力</p>
              ) : (
                <ul className="space-y-1.5 text-sm text-jade">
                  {result.supports.map((s, i) => (
                    <li key={i}>· {s}</li>
                  ))}
                </ul>
              )}
            </SectionCard>
            <SectionCard title="冲突信号" borderLeft="vermilion">
              {result.conflicts.length === 0 ? (
                <p className="text-sm text-ink-400">暂无显著冲突</p>
              ) : (
                <ul className="space-y-1.5 text-sm text-vermilion">
                  {result.conflicts.map((s, i) => (
                    <li key={i}>· {s}</li>
                  ))}
                </ul>
              )}
            </SectionCard>
          </div>

          {result.reading && (
            <SectionCard title="结构解读" borderLeft="gold">
              <div className="space-y-4">
                {result.reading.sections.map((sec) => (
                  <div key={sec.id}>
                    <h4 className="mb-1 text-sm font-medium text-ink-700 dark:text-ink-200">
                      {sec.title}
                    </h4>
                    <p className="text-sm leading-relaxed text-ink-600 dark:text-ink-300">
                      {sec.text}
                    </p>
                  </div>
                ))}
                {result.reading.advice.length > 0 && (
                  <div>
                    <h4 className="mb-1 text-sm font-medium text-ink-700 dark:text-ink-200">
                      行动建议
                    </h4>
                    <ul className="space-y-1 text-sm text-ink-600 dark:text-ink-300">
                      {result.reading.advice.map((a, i) => (
                        <li key={i}>· {a}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </SectionCard>
          )}

          {result.joint_top && result.joint_top.length > 0 && (
            <SectionCard
              title={
                <>
                  共同择日
                  {result.ics && (
                    <button
                      type="button"
                      onClick={() =>
                        downloadIcs(result.ics!, "mingmirror_合婚择日.ics")
                      }
                      className="ml-3 inline-flex items-center gap-1 rounded-lg bg-gold/15 px-2 py-1 text-xs font-normal text-gold transition hover:bg-gold/25"
                    >
                      <Download className="h-3 w-3" />
                      导出日历
                    </button>
                  )}
                </>
              }
              borderLeft="jade"
            >
              <p className="mb-3 text-xs text-ink-400">
                双方用神+冲合调和分；任一方过差会降权。适合婚嫁/共同大事窗口。
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                {result.joint_top.map((d, idx) => (
                  <div
                    key={d.date}
                    className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-3 dark:border-ink-500/20 dark:bg-ink-800/40"
                  >
                    <div className="flex items-baseline gap-2">
                      <span className="font-display text-lg text-ink-800 dark:text-ink-100">
                        {d.day_pillar}
                      </span>
                      <span className="text-xs text-ink-500">{d.date}</span>
                      <span className="ml-auto text-sm font-medium text-jade">
                        {d.score}
                      </span>
                      {idx === 0 && (
                        <span className="rounded bg-gold px-1.5 py-0.5 text-[10px] text-white">
                          首吉
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-[11px] text-ink-500">
                      甲{d.score_a} · 乙{d.score_b}
                      {d.best_hour?.label
                        ? ` · 吉时 ${d.best_hour.label}`
                        : ""}
                    </div>
                    <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-ink-600 dark:text-ink-300">
                      {d.reasoning}
                    </p>
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          <p className="text-center text-xs leading-relaxed text-ink-400">
            {result.note ||
              "结构性评分供决策参考，重大事项请兼顾多方。"}
          </p>
        </>
      )}
    </div>
  );
}
