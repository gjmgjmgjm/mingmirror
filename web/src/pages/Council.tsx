import { useState } from "react";
import { Link } from "react-router-dom";
import { useChart } from "../contexts/ChartContext";
import { councilDestiny, type DestinyAnalyzeResponse } from "../api/client";
import CouncilLoader from "../components/CouncilLoader";

const SYSTEMS = [
  { id: "bazi", label: "八字" },
  { id: "ziwei", label: "紫微" },
  { id: "qizheng", label: "七政" },
];

const STRATEGIES = [
  { id: "single", label: "单一结论" },
  { id: "reflection", label: "自我反思" },
  { id: "debate", label: "多 Agent 辩论" },
  { id: "tool_augmented", label: "规则校验增强" },
];

const DOMAIN_LABELS: Record<string, string> = {
  career: "事业",
  wealth: "财运",
  marriage: "婚姻",
  health: "健康",
  general: "综合",
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export default function Council() {
  const { chart } = useChart();
  const [selectedSystems, setSelectedSystems] = useState<string[]>([
    "bazi",
    "qizheng",
  ]);
  const [strategy, setStrategy] = useState("debate");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<DestinyAnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleSystem = (id: string) => {
    setSelectedSystems((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!chart || selectedSystems.length === 0) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await councilDestiny({
        bazi: chart.bazi,
        gender: chart.gender,
        birth_datetime:
          chart.birthDate && chart.birthTime
            ? new Date(`${chart.birthDate}T${chart.birthTime}`).toISOString()
            : undefined,
        location: chart.location,
        systems: selectedSystems,
        strategy,
        question: question.trim() || undefined,
      });
      setResult(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "议会分析失败";
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
          请先在首页输入八字信息，然后再召集命理议会。
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
        <h1 className="mb-6 font-display text-3xl text-ink-800 dark:text-ink-100">
          命理议会
        </h1>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <span className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300">
              选择命理体系
            </span>
            <div className="flex flex-wrap gap-3">
              {SYSTEMS.map((system) => (
                <label
                  key={system.id}
                  className={`flex cursor-pointer items-center gap-2 rounded-xl border px-4 py-2 transition ${
                    selectedSystems.includes(system.id)
                      ? "border-vermilion bg-vermilion/10 text-vermilion dark:bg-vermilion/20"
                      : "border-ink-300/40 bg-ink-100/50 text-ink-700 dark:border-ink-500/40 dark:bg-ink-800/50 dark:text-ink-200"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-vermilion"
                    checked={selectedSystems.includes(system.id)}
                    onChange={() => toggleSystem(system.id)}
                  />
                  <span>{system.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <label
              htmlFor="strategy"
              className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300"
            >
              决策策略
            </label>
            <select
              id="strategy"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="input md:w-72"
            >
              {STRATEGIES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="council-question"
              className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300"
            >
              问题（可选）
            </label>
            <input
              id="council-question"
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="例如：未来三年事业发展如何？"
              className="input"
            />
          </div>

          <button
            type="submit"
            disabled={loading || selectedSystems.length === 0}
            className="btn-primary disabled:cursor-not-allowed"
          >
            {loading ? "议会审议中……" : "召集议会"}
          </button>
        </form>
      </section>

      {loading && <CouncilLoader systems={selectedSystems} />}

      {error && (
        <div className="panel border-l-4 border-l-vermilion p-6 text-vermilion dark:border-l-vermilion-light">
          <p className="font-medium">议会出错</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {result && (
        <div className="space-y-6">
          <section
            className="panel p-6 animate-council-section"
            style={{ animationDelay: "0ms" }}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-ink-700 dark:text-ink-200">
                各体系观点
              </h2>
              <span className="text-sm text-ink-500 dark:text-ink-400">
                策略：{STRATEGIES.find((s) => s.id === result.strategy)?.label ?? result.strategy ?? "single"}
              </span>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {result.per_system.map((item, index) => (
                <div
                  key={item.system}
                  className="rounded-xl bg-ink-100/60 p-5 dark:bg-ink-800/60 animate-council-card"
                  style={{ animationDelay: `${index * 80 + 80}ms` }}
                >
                  <span className="mb-2 block text-sm font-medium text-vermilion">
                    {SYSTEMS.find((s) => s.id === item.system)?.label ?? item.system}
                  </span>
                  {item.domain_conclusions.length > 0 ? (
                    <ul className="space-y-1 text-sm text-ink-700 dark:text-ink-200">
                      {item.domain_conclusions.map((dc, idx) => (
                        <li key={idx}>
                          <span className="text-ink-500 dark:text-ink-400">
                            {DOMAIN_LABELS[dc.domain] ?? dc.domain}：
                          </span>
                          {dc.text}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-ink-600 dark:text-ink-400">
                      该体系暂无可用结论
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section
            className="panel border-l-4 border-l-jade p-6 animate-council-section"
            style={{ animationDelay: "200ms" }}
          >
            <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
              议会共识
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {Object.entries(result.aligned).map(([domain, entry], index) => {
                if (!entry || !entry.consensus) return null;
                return (
                  <div
                    key={domain}
                    className="rounded-xl bg-ink-100/60 p-4 dark:bg-ink-800/60 animate-council-card"
                    style={{ animationDelay: `${index * 60 + 300}ms` }}
                  >
                    <div className="mb-1 flex items-center justify-between">
                      <span className="font-medium text-ink-700 dark:text-ink-200">
                        {DOMAIN_LABELS[domain] ?? domain}
                      </span>
                      <span className="text-xs text-gold">
                        {CONFIDENCE_LABELS[entry.confidence] ?? entry.confidence}
                      </span>
                    </div>
                    <p className="text-sm text-ink-600 dark:text-ink-300">
                      {entry.consensus}
                    </p>
                  </div>
                );
              })}
            </div>
          </section>

          <section
            className="panel border-l-4 border-l-gold p-6 animate-council-section"
            style={{ animationDelay: "400ms" }}
          >
            <h2 className="mb-2 text-xl font-semibold text-ink-700 dark:text-ink-200">
              最终总结
            </h2>
            <p className="whitespace-pre-wrap text-ink-600 dark:text-ink-300">
              {result.final_summary}
            </p>
            <div className="mt-4 inline-block rounded-lg bg-gold/10 px-3 py-1 text-sm text-gold dark:bg-gold/20">
              整体置信度：{CONFIDENCE_LABELS[result.overall_confidence] ?? result.overall_confidence}
            </div>
          </section>

          <style>{`
            @keyframes council-section-enter {
              0% {
                opacity: 0;
                transform: translateY(16px);
              }
              100% {
                opacity: 1;
                transform: translateY(0);
              }
            }

            @keyframes council-card-enter {
              0% {
                opacity: 0;
                transform: scale(0.96) translateY(12px);
              }
              100% {
                opacity: 1;
                transform: scale(1) translateY(0);
              }
            }

            .animate-council-section {
              opacity: 0;
              animation: council-section-enter 0.5s ease-out forwards;
            }

            .animate-council-card {
              opacity: 0;
              animation: council-card-enter 0.45s ease-out forwards;
            }
          `}</style>
        </div>
      )}
    </div>
  );
}
