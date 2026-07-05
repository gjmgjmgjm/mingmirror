import { useState } from "react";
import { Link } from "react-router-dom";
import { useChart } from "../contexts/ChartContext";
import { analyzeBazi, type BaziAnalyzeResponse } from "../api/client";
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

function isCaseItem(item: string) {
  return /^参考相似案例[：:]?/.test(item);
}

function cleanCaseItem(item: string) {
  return item.replace(/^参考相似案例[：:]?\s*/, "");
}

function splitSummary(items: string[]) {
  const core: string[] = [];
  const cases: string[] = [];
  for (const item of items) {
    if (isCaseItem(item)) {
      cases.push(cleanCaseItem(item));
    } else {
      core.push(item);
    }
  }
  return { core, cases };
}

export default function ChartBasic() {
  const { chart } = useChart();
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<BaziAnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!chart) return;

    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const data = await analyzeBazi(chart.bazi, question.trim());
      setResponse(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "分析失败";
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
          请先在首页输入八字信息，然后再进行分析。
        </p>
        <Link to="/" className="btn-primary inline-flex">
          前往首页
        </Link>
      </div>
    );
  }

  const result = response?.result;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <section className="panel p-6 md:p-8">
        <h1 className="mb-6 font-display text-3xl text-ink-800 dark:text-ink-100">
          八字排盘分析
        </h1>
        <form onSubmit={handleAnalyze} className="space-y-4">
          <div>
            <label
              htmlFor="question"
              className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300"
            >
              你想问什么？
            </label>
            <input
              id="question"
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="事业、财运、婚姻、健康……"
              className="input"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="btn-primary disabled:cursor-not-allowed"
          >
            {loading ? "分析中……" : "开始分析"}
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
              基本信息
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <InfoItem label="八字" value={result.basic_info.bazi} delay={0} />
              <InfoItem label="日主" value={result.basic_info.day_master} delay={40} />
              <InfoItem label="月令" value={result.basic_info.month_branch} delay={80} />
              <InfoItem label="格局" value={result.basic_info.pattern} delay={120} />
              <InfoItem
                label="用神"
                value={result.basic_info.useful_gods.join("、")}
                delay={160}
              />
              <InfoItem
                label="忌神"
                value={result.basic_info.taboo_gods.join("、")}
                delay={200}
              />
              <InfoItem
                label="置信度"
                value={CONFIDENCE_LABELS[result.confidence] ?? result.confidence}
                delay={240}
              />
            </div>
          </section>

          <section
            className="panel p-6 animate-chart-section"
            style={{ animationDelay: "150ms" }}
          >
            <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
              领域分析
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

          {(result.wealth_level || result.marriage_status || (result.milestones && result.milestones.length > 0)) && (
            <section
              className="panel p-6 animate-chart-section"
              style={{ animationDelay: "180ms" }}
            >
              <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
                财富、婚姻与人生节点
              </h2>
              <div className="grid gap-4 sm:grid-cols-2">
                {result.wealth_level && (
                  <DomainRow
                    title="财富等级"
                    text={`${result.wealth_level}${result.wealth_evidence ? `。${result.wealth_evidence}` : ""}`}
                    delay={200}
                  />
                )}
                {result.marriage_status && (
                  <DomainRow
                    title="婚姻状况"
                    text={`${result.marriage_status}${result.marriage_evidence ? `。${result.marriage_evidence}` : ""}`}
                    delay={260}
                  />
                )}
              </div>
              {result.milestones && result.milestones.length > 0 && (
                <div className="mt-4">
                  <h3 className="mb-2 text-sm font-medium text-ink-600 dark:text-ink-300">
                    关键节点
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {result.milestones.map((m, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-ink-100/60 px-3 py-1.5 text-sm text-ink-700 dark:bg-ink-800/60 dark:text-ink-200"
                      >
                        <span className="font-semibold text-vermilion">{m.year}年</span>
                        <span className="text-xs text-ink-500 dark:text-ink-400">({m.age}岁)</span>
                        <span>{m.type}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          {result.personality && (
            <section
              className="panel relative overflow-hidden p-6 animate-chart-section"
              style={{ animationDelay: "220ms" }}
            >
              <div className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-vermilion/5 blur-2xl" />
              <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
                性格画像
              </h2>
              <blockquote className="relative border-l-4 border-vermilion bg-ink-100/40 p-4 text-ink-700 dark:border-vermilion-light dark:bg-ink-800/40 dark:text-ink-200">
                <span className="absolute left-2 top-2 text-2xl text-vermilion/20">“</span>
                <p className="pl-4 leading-relaxed">{result.personality}</p>
              </blockquote>
            </section>
          )}

          {result.events && result.events.length > 0 && (
            <section
              className="panel p-6 animate-chart-section"
              style={{ animationDelay: "260ms" }}
            >
              <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
                直断几件事
              </h2>
              <ul className="space-y-3">
                {result.events.map((item, idx) => (
                  <li
                    key={idx}
                    className="flex gap-3 rounded-xl bg-ink-100/40 p-3 dark:bg-ink-800/40"
                  >
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-gold text-xs font-bold text-white">
                      {idx + 1}
                    </span>
                    <span className="text-ink-700 dark:text-ink-200">{item}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

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

          {(() => {
            const { core, cases: summaryCases } = splitSummary(result.summary);
            const caveatCases = result.caveats.filter(isCaseItem).map(cleanCaseItem);
            const caveats = result.caveats.filter((item) => !isCaseItem(item));
            const allCases = [...summaryCases, ...caveatCases];
            return (
              <>
                <section
                  className="panel border-l-4 border-l-jade p-6 animate-chart-section"
                  style={{ animationDelay: "450ms" }}
                >
                  <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
                    核心断语
                  </h2>
                  {core.length > 0 ? (
                    <ul className="space-y-3">
                      {core.map((item, idx) => (
                        <li
                          key={idx}
                          className="flex gap-3 rounded-xl bg-ink-100/40 p-3 dark:bg-ink-800/40"
                        >
                          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-vermilion text-xs font-bold text-white">
                            {idx + 1}
                          </span>
                          <span className="text-ink-700 dark:text-ink-200">
                            {item}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-ink-500 dark:text-ink-400">
                      暂无核心断语
                    </p>
                  )}
                </section>

                {caveats.length > 0 && (
                  <section
                    className="panel border-l-4 border-l-gold p-6 animate-chart-section"
                    style={{ animationDelay: "600ms" }}
                  >
                    <h2 className="mb-2 text-xl font-semibold text-ink-700 dark:text-ink-200">
                      注意事项
                    </h2>
                    <ul className="list-inside list-disc space-y-1 text-ink-600 dark:text-ink-300">
                      {caveats.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </section>
                )}

                {allCases.length > 0 && (
                  <section
                    className="panel border-l-4 border-l-ink-300 p-6 animate-chart-section dark:border-l-ink-600"
                    style={{ animationDelay: "750ms" }}
                  >
                    <h2 className="mb-2 text-xl font-semibold text-ink-700 dark:text-ink-200">
                      相似案例参考
                    </h2>
                    <ul className="list-inside list-disc space-y-1 text-ink-600 dark:text-ink-300">
                      {allCases.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </section>
                )}
              </>
            );
          })()}

          <style>{`
            @keyframes chart-section-enter {
              0% {
                opacity: 0;
                transform: translateY(16px);
              }
              100% {
                opacity: 1;
                transform: translateY(0);
              }
            }

            @keyframes chart-card-enter {
              0% {
                opacity: 0;
                transform: scale(0.96) translateY(10px);
              }
              100% {
                opacity: 1;
                transform: scale(1) translateY(0);
              }
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
