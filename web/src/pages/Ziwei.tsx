import { useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import { analyzeBazi, type BaziAnalyzeResponse } from "../api/client";
import ChartLoader from "../components/ChartLoader";
import ZiweiStarMap from "../components/ZiweiStarMap";
import { SectionCard, InfoCard, DomainCard, EmptyState, PageHeader, ErrorPanel } from "../components/ui";

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

export default function Ziwei() {
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
      const message = err instanceof Error ? err.message : "紫微斗数分析失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  if (!chart) {
    return (
      <EmptyState
        title="暂无命盘"
        description="请先在首页输入八字信息，然后再进行紫微斗数分析。"
        action={
          <Link to="/" className="btn-primary inline-flex">
            前往首页
          </Link>
        }
      />
    );
  }

  const result = response?.result;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="紫微斗数"
        subtitle="以十二宫布星，观主星、辅星、煞星之组合，推断人生格局"
      />
      <SectionCard>
        <div className="mb-6 flex justify-center">
          <ZiweiStarMap bazi={chart.bazi} />
        </div>

        <form onSubmit={handleAnalyze} className="space-y-4">
          <div>
            <label
              htmlFor="ziwei-question"
              className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300"
            >
              你想问什么？
            </label>
            <input
              id="ziwei-question"
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
            className="btn-primary btn-shimmer disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <span className="relative mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                <span className="relative">分析中</span>
              </>
            ) : (
              <>
                <Sparkles className="relative mr-2 h-4 w-4" />
                <span className="relative">开始紫微斗数分析</span>
              </>
            )}
          </button>
        </form>
      </SectionCard>

      {loading && <ChartLoader />}

      {error && <ErrorPanel title="分析出错">{error}</ErrorPanel>}

      {result && (
        <div className="space-y-6">
          <SectionCard title="基本信息" delay={0}>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <InfoCard label="八字" value={result.basic_info.bazi} delay={0} />
              <InfoCard label="日主" value={result.basic_info.day_master} delay={40} term="日主" />
              <InfoCard label="月令" value={result.basic_info.month_branch} delay={80} term="月令" />
              <InfoCard label="格局" value={result.basic_info.pattern} delay={120} term="格局" />
              <InfoCard
                label="用神"
                value={result.basic_info.useful_gods.join("、")}
                delay={160}
                term="用神"
              />
              <InfoCard
                label="忌神"
                value={result.basic_info.taboo_gods.join("、")}
                delay={200}
                term="忌神"
              />
              <InfoCard
                label="置信度"
                value={CONFIDENCE_LABELS[result.confidence] ?? result.confidence}
                delay={240}
              />
            </div>
          </SectionCard>

          <SectionCard title="领域分析" delay={150}>
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

          {result.summary && result.summary.length > 0 && (
            <SectionCard title="核心断语" borderLeft="jade" delay={300}>
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
            <SectionCard title="注意事项" borderLeft="gold" delay={450}>
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
