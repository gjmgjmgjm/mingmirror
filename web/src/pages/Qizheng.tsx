import { useState } from "react";
import { Link } from "react-router-dom";
import { useChart } from "../contexts/ChartContext";
import { analyzeQizheng, type QizhengResult } from "../api/client";
import ChartLoader from "../components/ChartLoader";

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

export default function Qizheng() {
  const { chart } = useChart();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QizhengResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!chart) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await analyzeQizheng(chart.bazi, question.trim());
      setResult(data.result);
    } catch (err) {
      const message = err instanceof Error ? err.message : "七政四余分析失败";
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
          请先在首页输入八字信息，然后再进行七政四余分析。
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
            <h1 className="mb-2 font-display text-3xl text-ink-800 dark:text-ink-100">
              七政四余
            </h1>
            <p className="text-sm text-ink-500 dark:text-ink-400">
              以日、月、金、木、水、火、土七政为主，结合紫气、月孛、罗睺、计都四余进行推断
            </p>
          </div>
          <Link
            to="/qizheng/yearly"
            className="inline-flex items-center justify-center rounded-xl border border-ink-300/40 bg-ink-100/50 px-4 py-2 text-sm font-medium text-ink-700 transition hover:bg-ink-200/60 dark:border-ink-500/40 dark:bg-ink-800/50 dark:text-ink-200 dark:hover:bg-ink-700/60"
          >
            大运流年
          </Link>
        </div>
        <form onSubmit={handleAnalyze} className="space-y-4">
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
          <button
            type="submit"
            disabled={loading}
            className="btn-primary disabled:cursor-not-allowed"
          >
            {loading ? "分析中……" : "开始七政四余分析"}
          </button>
        </form>
      </section>

      {loading && <ChartLoader />}

      {error && (
        <div className="panel border-l-4 border-l-vermilion p-6 text-vermilion dark:border-l-vermilion-light">
          <p className="font-medium">分析出错</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {result && (
        <div className="space-y-6">
          <section
            className="panel p-6 animate-chart-section"
            style={{ animationDelay: "0ms" }}
          >
            <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
              命盘结构
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <InfoItem label="八字" value={result.basic_info.chart} delay={0} />
              <InfoItem
                label="日主"
                value={result.basic_info.day_master ?? "—"}
                delay={40}
              />
              <InfoItem
                label="命宫"
                value={result.basic_info.life_palace ?? "—"}
                delay={80}
              />
              <InfoItem
                label="身宫"
                value={result.basic_info.body_palace ?? "—"}
                delay={120}
              />
              <InfoItem
                label="主星"
                value={result.basic_info.dominant_stars?.join("、") ?? "—"}
                delay={160}
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
          </section>

          <section
            className="panel p-6 animate-chart-section"
            style={{ animationDelay: "150ms" }}
          >
            <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
              领域断语
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {Object.entries(DOMAIN_LABELS).map(([key, label], index) => {
                const text = result.domain_analysis[key as keyof typeof result.domain_analysis];
                if (!text) return null;
                return (
                  <DomainRow
                    key={key}
                    title={label}
                    text={text}
                    delay={index * 60 + 200}
                  />
                );
              })}
            </div>
          </section>

          <section
            className="panel p-6 animate-chart-section"
            style={{ animationDelay: "300ms" }}
          >
            <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
              推理过程
            </h2>
            <p className="whitespace-pre-wrap text-ink-600 dark:text-ink-300">
              {result.reasoning}
            </p>
          </section>

          {result.summary && result.summary.length > 0 && (
            <section
              className="panel border-l-4 border-l-jade p-6 animate-chart-section"
              style={{ animationDelay: "450ms" }}
            >
              <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
                核心断语
              </h2>
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
            </section>
          )}

          {result.caveats && result.caveats.length > 0 && (
            <section
              className="panel border-l-4 border-l-gold p-6 animate-chart-section"
              style={{ animationDelay: "600ms" }}
            >
              <h2 className="mb-2 text-xl font-semibold text-ink-700 dark:text-ink-200">
                注意事项
              </h2>
              <ul className="list-inside list-disc space-y-1 text-ink-600 dark:text-ink-300">
                {result.caveats.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            </section>
          )}

          <style>{`
            @keyframes chart-section-enter {
              0% { opacity: 0; transform: translateY(16px); }
              100% { opacity: 1; transform: translateY(0); }
            }

            @keyframes chart-card-enter {
              0% { opacity: 0; transform: scale(0.96) translateY(10px); }
              100% { opacity: 1; transform: scale(1) translateY(0); }
            }

            .animate-chart-section {
              opacity: 0;
              animation: chart-section-enter 0.5s ease-out forwards;
            }

            .animate-chart-card {
              opacity: 0;
              animation: chart-card-enter 0.4s ease-out forwards;
            }
          `}</style>
        </div>
      )}
    </div>
  );
}

function InfoItem({
  label,
  value,
  delay,
}: {
  label: string;
  value: string;
  delay: number;
}) {
  return (
    <div
      className="rounded-xl bg-ink-100/60 p-4 dark:bg-ink-800/60 animate-chart-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <span className="block text-xs text-ink-500 dark:text-ink-400">
        {label}
      </span>
      <span className="block font-medium text-ink-700 dark:text-ink-200">
        {value}
      </span>
    </div>
  );
}

function DomainRow({
  title,
  text,
  delay,
}: {
  title: string;
  text: string;
  delay: number;
}) {
  return (
    <div
      className="flex flex-col gap-1 rounded-xl bg-ink-100/60 p-4 dark:bg-ink-800/60 animate-chart-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <span className="text-sm font-medium text-vermilion">{title}</span>
      <span className="text-ink-700 dark:text-ink-200">{text}</span>
    </div>
  );
}
