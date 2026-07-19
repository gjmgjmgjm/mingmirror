import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Scale } from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import {
  councilDestiny,
  fetchLatestCalibration,
  type DestinyAnalyzeResponse,
  type CalibrationResponse,
} from "../api/client";
import CouncilLoader from "../components/CouncilLoader";
import { SectionCard, InfoCard, EmptyState, PageHeader, ErrorPanel } from "../components/ui";
import { getDeviceId, track } from "../lib/analytics";

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

const SYSTEM_LABELS: Record<string, string> = {
  bazi: "八字",
  ziwei: "紫微",
  qizheng: "七政",
};

function WeightsBar({
  weights,
  source,
}: {
  weights: Record<string, number>;
  source?: string;
}) {
  const entries = Object.entries(weights);
  if (entries.length === 0) return null;
  const total = entries.reduce((s, [, v]) => s + v, 0) || 1;
  return (
    <SectionCard
      title={
        <>
          <Scale className="mr-1.5 inline h-4 w-4 text-gold" />
          系统权重
          {source === "calibration" && (
            <span className="ml-2 text-xs font-normal text-jade">· 来自事件校准</span>
          )}
        </>
      }
      borderLeft="gold"
    >
      <div className="space-y-3">
        {entries.map(([sys, w]) => {
          const pct = Math.round((w / total) * 100);
          return (
            <div key={sys}>
              <div className="mb-1 flex justify-between text-xs">
                <span className="text-ink-600 dark:text-ink-300">
                  {SYSTEM_LABELS[sys] ?? sys}
                </span>
                <span className="text-ink-500">
                  {w.toFixed(2)}（{pct}%）
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-ink-100 dark:bg-ink-800">
                <div
                  className="h-full rounded-full bg-gold"
                  style={{ width: `${Math.min(100, pct)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-ink-400">
        权重影响议会共识投票：高权重体系的结论在分歧时优先。可在「校准」页录入事件后运行校准以更新。
      </p>
    </SectionCard>
  );
}

export default function Council() {
  const { chart, chartScopeId } = useChart();
  const [selectedSystems, setSelectedSystems] = useState<string[]>([
    "bazi",
    "qizheng",
  ]);
  const [strategy, setStrategy] = useState("debate");
  const [question, setQuestion] = useState("");
  const [useCalibration, setUseCalibration] = useState(true);
  const [result, setResult] = useState<DestinyAnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedCalibration, setSavedCalibration] = useState<CalibrationResponse | null>(
    null
  );

  useEffect(() => {
    if (!chartScopeId) {
      setSavedCalibration(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const latest = await fetchLatestCalibration(chartScopeId, getDeviceId());
        if (!cancelled) setSavedCalibration(latest);
      } catch {
        if (!cancelled) setSavedCalibration(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chartScopeId]);

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
      // Use wall-clock local datetime (no toISOString/UTC shift) so hour pillar
      // matches Dashboard / Ziwei pages.
      const birth_datetime =
        chart.birthDate && chart.birthTime
          ? `${chart.birthDate}T${chart.birthTime}`
          : chart.birthDate
            ? `${chart.birthDate}T00:00`
            : undefined;
      const data = await councilDestiny({
        bazi: chart.bazi,
        gender: chart.gender,
        birth_datetime,
        location: chart.location,
        chart_id: chart.id || chartScopeId || undefined,
        systems: selectedSystems,
        strategy,
        question: question.trim() || undefined,
        use_calibration_weights: useCalibration,
      });
      track("council_run", { strategy, systems: selectedSystems.join(",") }, chartScopeId || chart.bazi);
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
      <EmptyState
        title="暂无命盘"
        description="请先在首页输入八字信息，然后再召集命理议会。"
        action={
          <Link to="/" className="btn-primary inline-flex">
            前往首页
          </Link>
        }
      />
    );
  }

  const previewWeights =
    useCalibration && savedCalibration?.adjusted_weights
      ? savedCalibration.adjusted_weights
      : null;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="命理议会"
        subtitle="召集八字、紫微、七政四余多体系共同议事；可叠加事件校准权重"
      />
      <SectionCard>
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

          <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-600 dark:text-ink-300">
            <input
              type="checkbox"
              className="h-4 w-4 accent-gold"
              checked={useCalibration}
              onChange={(e) => setUseCalibration(e.target.checked)}
            />
            使用事件校准权重
            {!savedCalibration && (
              <span className="text-xs text-ink-400">
                （尚未校准，
                <Link to="/events" className="text-gold underline">
                  去校准
                </Link>
                ）
              </span>
            )}
            {savedCalibration && (
              <span className="text-xs text-jade">
                已有校准 · 均分 {(savedCalibration.average_score * 100).toFixed(0)}%
              </span>
            )}
          </label>

          <button
            type="submit"
            disabled={loading || selectedSystems.length === 0}
            className="btn-primary disabled:cursor-not-allowed"
          >
            {loading ? "议会审议中……" : "召集议会"}
          </button>
        </form>
      </SectionCard>

      {previewWeights && !result && (
        <WeightsBar weights={previewWeights} source="calibration" />
      )}

      {loading && <CouncilLoader systems={selectedSystems} />}

      {error && <ErrorPanel title="议会出错">{error}</ErrorPanel>}

      {result && (
        <div className="space-y-6">
          {result.system_weights && (
            <WeightsBar
              weights={result.system_weights}
              source={result.weights_source}
            />
          )}

          <SectionCard title="各体系观点" delay={0}>
            <div className="mb-4 flex items-center justify-between">
              <span />
              <span className="text-sm text-ink-500 dark:text-ink-400">
                策略：
                {STRATEGIES.find((s) => s.id === result.strategy)?.label ??
                  result.strategy ??
                  "single"}
              </span>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {result.per_system.map((item, index) => {
                const w = result.system_weights?.[item.system];
                return (
                  <div
                    key={item.system}
                    className="rounded-xl bg-ink-100/60 p-5 dark:bg-ink-800/60 animate-council-card"
                    style={{ animationDelay: `${index * 80 + 80}ms` }}
                  >
                    <span className="mb-2 flex items-center justify-between text-sm font-medium text-vermilion">
                      <span>
                        {SYSTEMS.find((s) => s.id === item.system)?.label ?? item.system}
                      </span>
                      {w !== undefined && (
                        <span className="rounded bg-gold/15 px-1.5 py-0.5 text-[10px] font-normal text-gold">
                          权重 {w.toFixed(2)}
                        </span>
                      )}
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
                );
              })}
            </div>
          </SectionCard>

          <SectionCard title="议会共识" borderLeft="jade" delay={200}>
            <div className="grid gap-4 sm:grid-cols-2">
              {Object.entries(result.aligned).map(([domain, entry], index) => {
                if (!entry || !entry.consensus) return null;
                return (
                  <InfoCard
                    key={domain}
                    label={`${DOMAIN_LABELS[domain] ?? domain} · ${CONFIDENCE_LABELS[entry.confidence] ?? entry.confidence}`}
                    value={entry.consensus}
                    delay={index * 60 + 300}
                  />
                );
              })}
            </div>
          </SectionCard>

          <SectionCard title="最终总结" borderLeft="gold" delay={400}>
            <p className="whitespace-pre-wrap text-ink-600 dark:text-ink-300">
              {result.final_summary}
            </p>
            <div className="mt-4 inline-block rounded-lg bg-gold/10 px-3 py-1 text-sm text-gold dark:bg-gold/20">
              整体置信度：
              {CONFIDENCE_LABELS[result.overall_confidence] ?? result.overall_confidence}
            </div>
          </SectionCard>
        </div>
      )}
    </div>
  );
}
