import { useState } from "react";
import { Link } from "react-router-dom";
import { useChart } from "../contexts/ChartContext";
import { analyzeBazi, type BaziAnalyzeResponse } from "../api/client";
import ChartLoader from "../components/ChartLoader";
import YearTimingPanel from "../components/YearTimingPanel";
import LiuqinDossierPanel from "../components/LiuqinDossierPanel";
import {
  SectionCard,
  InfoCard,
  DomainCard,
  EmptyState,
  PageHeader,
  ErrorPanel,
} from "../components/ui";

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
      const data = await analyzeBazi(chart.bazi, question.trim(), {
        gender: chart.gender || "male",
        birthDate: chart.birthDate || "",
        birthTime: chart.birthTime || "00:00",
        calendarType: chart.calendarType || "solar",
      });
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
      <EmptyState
        title="暂无命盘"
        description="请先在首页输入八字信息，然后再进行分析。"
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
    <div className="mx-auto max-w-4xl space-y-6">
      <SectionCard>
        <PageHeader title="八字排盘分析" />
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

          <YearTimingPanel surface={result.year_timing_surface} delay={170} />

          <LiuqinDossierPanel
            dossier={result.liuqin_dossier}
            delay={180}
            highlightYears={(
              result.year_timing_surface?.candidates || []
            )
              .map((c) => c.year)
              .filter((y): y is number => typeof y === "number" && y > 0)
              .concat(
                result.year_timing_surface?.meta?.liuqin_bridge?.overlap_years ||
                  []
              )}
          />

          {(result.wealth_level || result.marriage_status || (result.milestones && result.milestones.length > 0)) && (
            <SectionCard title="财富、婚姻与人生节点" delay={180}>
              <div className="grid gap-4 sm:grid-cols-2">
                {result.wealth_level && (
                  <DomainCard
                    title="财富等级"
                    text={`${result.wealth_level}${result.wealth_evidence ? `。${result.wealth_evidence}` : ""}`}
                    delay={200}
                  />
                )}
                {result.marriage_status && (
                  <DomainCard
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
            </SectionCard>
          )}

          {result.personality && (
            <SectionCard title="性格画像" delay={220}>
              <blockquote className="relative border-l-4 border-vermilion bg-ink-100/40 p-4 text-ink-700 dark:border-vermilion-light dark:bg-ink-800/40 dark:text-ink-200">
                <span className="absolute left-2 top-2 text-2xl text-vermilion/20">“</span>
                <p className="pl-4 leading-relaxed">{result.personality}</p>
              </blockquote>
            </SectionCard>
          )}

          {result.events && result.events.length > 0 && (
            <SectionCard title="直断几件事" delay={260}>
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
            </SectionCard>
          )}

          <SectionCard title="推理过程" delay={300}>
            <p className="whitespace-pre-wrap text-ink-600 dark:text-ink-300">
              {result.reasoning}
            </p>
          </SectionCard>

          {(() => {
            const { core, cases: summaryCases } = splitSummary(result.summary);
            const caveatCases = result.caveats.filter(isCaseItem).map(cleanCaseItem);
            const caveats = result.caveats.filter((item) => !isCaseItem(item));
            const allCases = [...summaryCases, ...caveatCases];
            return (
              <>
                <SectionCard title="核心断语" borderLeft="jade" delay={450}>
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
                </SectionCard>

                {caveats.length > 0 && (
                  <SectionCard title="注意事项" borderLeft="gold" delay={600}>
                    <ul className="list-inside list-disc space-y-1 text-ink-600 dark:text-ink-300">
                      {caveats.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </SectionCard>
                )}

                {allCases.length > 0 && (
                  <SectionCard title="相似案例参考" borderLeft="ink" delay={750}>
                    <ul className="list-inside list-disc space-y-1 text-ink-600 dark:text-ink-300">
                      {allCases.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </SectionCard>
                )}
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}
