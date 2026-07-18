import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useChart } from "../contexts/ChartContext";
import { analyzeQizheng, type QizhengResult } from "../api/client";
import ChartLoader from "../components/ChartLoader";
import {
  SectionCard,
  InfoCard,
  DomainCard,
  EmptyState,
  PageHeader,
  ErrorPanel,
} from "../components/ui";
import QizhengStarMap from "../components/QizhengStarMap";

const DOMAIN_LABELS: Record<string, string> = {
  career: "事业",
  wealth: "财运",
  marriage: "婚姻",
  health: "健康",
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const DIGNITY_OPTIONS: { value: "default" | "yang"; label: string }[] = [
  { value: "default", label: "默认庙旺表" },
  { value: "yang", label: "杨国正派" },
];

export default function Qizheng() {
  const { chart } = useChart();
  const [question, setQuestion] = useState("");
  const [dignityTable, setDignityTable] = useState<"default" | "yang">("default");
  const [result, setResult] = useState<QizhengResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runAnalyze = async (q: string) => {
    if (!chart) return;
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeQizheng(chart.bazi, q, dignityTable);
      setResult(data.result);
    } catch (err) {
      const message = err instanceof Error ? err.message : "七政四余分析失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  // Auto structural load
  useEffect(() => {
    if (!chart) return;
    void runAnalyze("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chart?.bazi, dignityTable]);

  const handleAnalyze = async (event: React.FormEvent) => {
    event.preventDefault();
    setResult(null);
    await runAnalyze(question.trim());
  };

  if (!chart) {
    return (
      <EmptyState
        title="暂无命盘"
        description="请先在首页输入八字信息，然后再进行七政四余分析。"
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
          title="七政四余"
          subtitle="以日、月、金、木、水、火、土七政为主，结合紫气、月孛、罗睺、计都四余进行推断"
          action={
            <Link to="/qizheng/yearly" className="btn-secondary text-sm">
              大运流年
            </Link>
          }
        />
        <div className="mb-6 flex justify-center">
          <QizhengStarMap
            bazi={chart.bazi}
            lifePalace={result?.basic_info.life_palace}
            bodyPalace={result?.basic_info.body_palace}
            dominantStars={result?.basic_info.dominant_stars}
          />
        </div>
        <form onSubmit={handleAnalyze} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="qizheng-dignity"
                className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300"
              >
                庙旺流派
              </label>
              <select
                id="qizheng-dignity"
                value={dignityTable}
                onChange={(e) =>
                  setDignityTable(e.target.value as "default" | "yang")
                }
                className="input"
              >
                {DIGNITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="qizheng-question"
                className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300"
              >
                你想问什么？
              </label>
              <input
                id="qizheng-question"
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="事业、财运、婚姻、健康、六亲……"
                className="input"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={loading}
            className="btn-primary disabled:cursor-not-allowed"
          >
            {loading ? "分析中……" : "开始七政四余分析"}
          </button>
        </form>
      </SectionCard>

      {loading && <ChartLoader />}

      {error && <ErrorPanel title="分析出错">{error}</ErrorPanel>}

      {result && (
        <div className="space-y-6">
          <SectionCard title="命盘结构" delay={0}>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <InfoItem label="八字" value={result.basic_info.chart} delay={0} />
              <InfoItem
                label="日主"
                value={result.basic_info.day_master ?? "—"}
                delay={40}
                term="日主"
              />
              <InfoItem
                label="命宫"
                value={result.basic_info.life_palace ?? "—"}
                delay={80}
                term="命宫"
              />
              <InfoItem
                label="身宫"
                value={result.basic_info.body_palace ?? "—"}
                delay={120}
                term="身宫"
              />
              <InfoItem
                label="身主 / 主星"
                value={
                  (result.basic_info as { body_lord?: string }).body_lord ||
                  result.basic_info.dominant_stars?.join("、") ||
                  "—"
                }
                delay={160}
                term="主星"
              />
              <InfoItem
                label="五行局"
                value={
                  (result.basic_info as { five_element_pattern?: string })
                    .five_element_pattern || "—"
                }
                delay={180}
              />
              <InfoItem
                label="置信度"
                value={
                  CONFIDENCE_LABELS[result.confidence ?? ""] ??
                  result.confidence ??
                  "—"
                }
                delay={200}
              />
            </div>
            {result.summary && result.summary.length > 0 && (
              <p className="mt-3 text-xs text-ink-500 dark:text-ink-400">
                {result.summary.join(" · ")}
              </p>
            )}

            {result.basic_info.twelve_palaces &&
              Object.keys(result.basic_info.twelve_palaces).length > 0 && (
                <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {Object.entries(result.basic_info.twelve_palaces).map(
                    ([name, branch], idx) => (
                      <div
                        key={name}
                        className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-3 text-center dark:border-ink-500/20 dark:bg-ink-800/40 animate-chart-card"
                        style={{ animationDelay: `${240 + idx * 40}ms` }}
                      >
                        <span className="block text-xs text-ink-500 dark:text-ink-400">
                          {name}
                        </span>
                        <span className="block font-medium text-ink-700 dark:text-ink-200">
                          {branch}
                        </span>
                      </div>
                    )
                  )}
                </div>
              )}
          </SectionCard>

          <SectionCard title="领域断语" delay={150}>
            <div className="grid gap-4 sm:grid-cols-2">
              {Object.entries(DOMAIN_LABELS).map(([key, label], index) => {
                const text = result.domain_analysis[key as keyof typeof result.domain_analysis];
                if (!text) return null;
                return (
                  <DomainCard
                    key={key}
                    title={label}
                    text={text}
                    delay={index * 60 + 200}
                  />
                );
              })}
            </div>
          </SectionCard>

          <SectionCard title="推理过程" delay={300}>
            <p className="whitespace-pre-wrap text-ink-600 dark:text-ink-300">
              {result.reasoning}
            </p>
          </SectionCard>

          {result.summary && result.summary.length > 0 && (
            <SectionCard title="核心断语" borderLeft="jade" delay={450}>
              <ul className="space-y-3">
                {result.summary.map((item, idx) => (
                  <li
                    key={idx}
                    className="flex gap-3 rounded-xl bg-ink-100/40 p-3 dark:bg-ink-800/40"
                  >
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-vermilion text-xs font-bold text-white">
                      {idx + 1}
                    </span>
                    <span className="text-ink-700 dark:text-ink-200">{item}</span>
                  </li>
                ))}
              </ul>
            </SectionCard>
          )}

          {result.caveats && result.caveats.length > 0 && (
            <SectionCard title="注意事项" borderLeft="gold" delay={600}>
              <ul className="list-inside list-disc space-y-1 text-ink-600 dark:text-ink-300">
                {result.caveats.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            </SectionCard>
          )}
        </div>
      )}
    </div>
  );
}

function InfoItem({
  label,
  value,
  delay,
  term,
}: {
  label: string;
  value: string;
  delay: number;
  term?: string;
}) {
  return (
    <InfoCard
      label={label}
      value={value}
      delay={delay}
      term={term}
    />
  );
}
