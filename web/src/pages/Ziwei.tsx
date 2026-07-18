import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import {
  analyzeZiwei,
  analyzeZiweiYearly,
  type ZiweiAnalyzeResponse,
  type ZiweiPalace,
  type ZiweiLiunianYear,
} from "../api/client";
import ChartLoader from "../components/ChartLoader";
import ZiweiStarMap from "../components/ZiweiStarMap";
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
  general: "综合",
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const LIUNIAN_SPAN_OPTIONS = [5, 10, 15, 20] as const;

function domainText(val: unknown): string {
  if (!val) return "";
  if (typeof val === "string") return val;
  if (typeof val === "object" && val !== null && "text" in val) {
    return String((val as { text: string }).text || "");
  }
  return String(val);
}

export default function Ziwei() {
  const { chart } = useChart();
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<ZiweiAnalyzeResponse | null>(null);
  const [liunian, setLiunian] = useState<ZiweiLiunianYear[]>([]);
  const [liunianNote, setLiunianNote] = useState("");
  const [liunianStart, setLiunianStart] = useState(() => new Date().getFullYear());
  const [liunianYears, setLiunianYears] =
    useState<(typeof LIUNIAN_SPAN_OPTIONS)[number]>(10);
  const [liunianLoading, setLiunianLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLiunian = useCallback(
    async (start: number, years: number) => {
      if (!chart) return;
      setLiunianLoading(true);
      try {
        const y = await analyzeZiweiYearly({
          bazi: chart.bazi,
          gender: chart.gender || "male",
          birth_date: chart.birthDate || "",
          start_year: start,
          years,
        });
        setLiunian(y.result.liunian || []);
        setLiunianNote(y.result.note || "");
      } catch {
        setLiunian([]);
      } finally {
        setLiunianLoading(false);
      }
    },
    [chart]
  );

  // Auto-load structural chart on mount
  useEffect(() => {
    if (!chart) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await analyzeZiwei({
          bazi: chart.bazi,
          gender: chart.gender || "male",
          birth_date: chart.birthDate,
          birth_datetime:
            chart.birthDate && chart.birthTime
              ? `${chart.birthDate}T${chart.birthTime}:00`
              : undefined,
          location: chart.location
            ? {
                longitude: chart.location.longitude,
                latitude: chart.location.latitude,
                timezone: chart.location.timezone,
              }
            : undefined,
          question: "",
        });
        if (!cancelled) setResponse(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "紫微排盘失败");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chart?.bazi, chart?.gender, chart?.birthDate, chart?.birthTime]);

  // 流年区间独立加载
  useEffect(() => {
    if (!chart) return;
    void loadLiunian(liunianStart, liunianYears);
  }, [chart?.bazi, chart?.gender, chart?.birthDate, liunianStart, liunianYears, loadLiunian]);

  const handleAnalyze = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!chart) return;
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeZiwei({
        bazi: chart.bazi,
        gender: chart.gender || "male",
        birth_date: chart.birthDate,
        birth_datetime:
          chart.birthDate && chart.birthTime
            ? `${chart.birthDate}T${chart.birthTime}:00`
            : undefined,
        location: chart.location
          ? {
              longitude: chart.location.longitude,
              latitude: chart.location.latitude,
              timezone: chart.location.timezone,
            }
          : undefined,
        question: question.trim(),
      });
      setResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "紫微斗数分析失败");
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
  const basic = result?.basic_info;
  const palaces: ZiweiPalace[] = basic?.palaces || result?.structural?.palaces || [];
  const domains = result?.domain_analysis || {};

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="紫微斗数"
        subtitle="结构层：命身宫 · 五行局 · 紫微/天府系主星 · 年干四化（确定性简化）"
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
              追问（可选，配置 API Key 后 LLM 细批更完整）
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
            {loading ? "分析中…" : (
              <>
                <Sparkles className="relative mr-2 h-4 w-4" />
                刷新紫微分析
              </>
            )}
          </button>
        </form>
      </SectionCard>

      {loading && <ChartLoader />}
      {error && <ErrorPanel title="分析出错">{error}</ErrorPanel>}

      {basic && (
        <div className="space-y-6">
          <SectionCard title="结构信息" borderLeft="gold" delay={0}>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <InfoCard label="命宫" value={basic.ming_gong || basic.life_palace || "—"} />
              <InfoCard label="身宫" value={basic.shen_gong || basic.body_palace || "—"} />
              <InfoCard label="五行局" value={basic.bureau_label || "—"} />
              <InfoCard
                label="命宫主星"
                value={(basic.zhu_xing || []).join("、") || "—"}
              />
              <InfoCard
                label="命宫辅星"
                value={(basic.ming_aux || []).join("、") || "—"}
              />
              <InfoCard
                label="命宫煞星"
                value={(basic.ming_sha || []).join("、") || "—"}
              />
              <InfoCard
                label="年干四化"
                value={(basic.si_hua || []).join("；") || "—"}
              />
              <InfoCard
                label="当前大限"
                value={
                  basic.current_limit
                    ? `${basic.current_limit.label} · ${basic.current_limit.branch}（${basic.limit_direction || ""}）`
                    : "—"
                }
              />
              <InfoCard
                label="置信"
                value={
                  CONFIDENCE_LABELS[result?.confidence || ""] ||
                  result?.confidence ||
                  "中"
                }
              />
            </div>
            {basic.note && (
              <p className="mt-3 text-xs leading-relaxed text-ink-400">{basic.note}</p>
            )}
          </SectionCard>

          {palaces.length > 0 && (
            <SectionCard title="十二宫（主 / 辅 / 煞）" borderLeft="jade">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {palaces.map((p) => (
                  <div
                    key={p.name}
                    className="rounded-lg border border-ink-300/20 bg-ink-100/40 px-3 py-2 text-sm dark:border-ink-600/30 dark:bg-ink-800/40"
                  >
                    <div className="font-medium text-ink-700 dark:text-ink-200">
                      {p.name}
                      <span className="ml-1 text-xs font-normal text-ink-400">
                        {p.branch}
                      </span>
                    </div>
                    {(p.main_stars && p.main_stars.length > 0) && (
                      <div className="text-xs text-vermilion">
                        主 {(p.main_stars || []).join("、")}
                      </div>
                    )}
                    {(p.aux_stars && p.aux_stars.length > 0) && (
                      <div className="text-xs text-jade">
                        辅 {(p.aux_stars || []).join("、")}
                      </div>
                    )}
                    {(p.sha_stars && p.sha_stars.length > 0) && (
                      <div className="text-xs text-ink-400">
                        煞 {(p.sha_stars || []).join("、")}
                      </div>
                    )}
                    {!p.main_stars?.length &&
                      !p.aux_stars?.length &&
                      !p.sha_stars?.length && (
                        <div className="text-xs text-ink-500">
                          {(p.stars || []).join("、") || "（空）"}
                        </div>
                      )}
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {(basic.major_limits || []).length > 0 && (
            <SectionCard title="大限（十年运）" borderLeft="gold">
              <p className="mb-3 text-xs text-ink-400">
                起运按五行局；{basic.limit_direction || "顺/逆"}自命宫，每宫十年。
                高亮为当前大限（需出生年估算年龄）。
              </p>
              <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
                {(basic.major_limits || []).map((lim) => {
                  const active =
                    basic.current_limit &&
                    lim.index === basic.current_limit.index;
                  return (
                    <div
                      key={lim.index}
                      className={`rounded-lg border px-3 py-2 text-xs ${
                        active
                          ? "border-gold bg-gold/15 text-ink-800 dark:text-ink-100"
                          : "border-ink-300/20 bg-ink-100/30 text-ink-600 dark:border-ink-600/30 dark:bg-ink-800/30 dark:text-ink-300"
                      }`}
                    >
                      <div className="font-medium">
                        {lim.label}
                        {active && (
                          <span className="ml-1 text-[10px] text-gold">当前</span>
                        )}
                      </div>
                      <div>
                        {lim.branch} · {lim.palace_name}
                      </div>
                    </div>
                  );
                })}
              </div>
            </SectionCard>
          )}

          <SectionCard title="领域提示" borderLeft="vermilion">
            <div className="grid gap-3 sm:grid-cols-2">
              {Object.entries(DOMAIN_LABELS).map(([key, label]) => {
                const text = domainText(domains[key]);
                if (!text) return null;
                return (
                  <DomainCard key={key} title={label} text={text} delay={0} />
                );
              })}
            </div>
          </SectionCard>

          <SectionCard title="流年（太岁入宫）" borderLeft="vermilion">
            <div className="mb-3 flex flex-wrap items-end gap-3">
              <label className="text-xs text-ink-500">
                起始年
                <input
                  type="number"
                  className="input mt-1 w-28 text-sm"
                  value={liunianStart}
                  min={1900}
                  max={2100}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    if (!Number.isNaN(v)) setLiunianStart(v);
                  }}
                />
              </label>
              <label className="text-xs text-ink-500">
                跨度
                <select
                  className="input mt-1 w-28 text-sm"
                  value={liunianYears}
                  onChange={(e) =>
                    setLiunianYears(
                      Number(e.target.value) as (typeof LIUNIAN_SPAN_OPTIONS)[number]
                    )
                  }
                >
                  {LIUNIAN_SPAN_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n} 年
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="btn-secondary text-xs"
                onClick={() => setLiunianStart(new Date().getFullYear())}
              >
                回到今年
              </button>
              {liunianLoading && (
                <span className="text-xs text-ink-400">更新中…</span>
              )}
            </div>
            <p className="mb-3 text-xs text-ink-400">
              {liunianNote ||
                "流年地支对应本命宫位为太岁所冲发；附流年四化与所在大限。"}
            </p>
            {liunian.length === 0 && !liunianLoading ? (
              <p className="text-sm text-ink-400">暂无流年数据</p>
            ) : (
              <div className="space-y-3">
                {liunian.map((y) => {
                  const isNow = y.year === new Date().getFullYear();
                  return (
                    <div
                      key={y.year}
                      className={`rounded-xl border p-3 text-sm ${
                        isNow
                          ? "border-gold bg-gold/10"
                          : "border-ink-300/20 bg-ink-100/30 dark:border-ink-600/30 dark:bg-ink-800/30"
                      }`}
                    >
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span className="font-display text-lg text-ink-800 dark:text-ink-100">
                          {y.year}
                        </span>
                        <span className="text-xs text-ink-500">{y.pillar}</span>
                        <span className="text-xs text-vermilion">
                          太岁入{y.palace_name}（{y.palace_branch}）
                        </span>
                        {y.age != null && (
                          <span className="text-xs text-ink-400">{y.age}岁</span>
                        )}
                        {isNow && (
                          <span className="rounded bg-gold px-1.5 py-0.5 text-[10px] text-white">
                            今年
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-ink-600 dark:text-ink-300">
                        {y.overview}
                      </p>
                      <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-ink-500">
                        {(y.si_hua || []).length > 0 && (
                          <span>四化 {(y.si_hua || []).join("、")}</span>
                        )}
                        {y.major_limit && (
                          <span>
                            大限 {y.major_limit.label}·{y.major_limit.branch}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-[11px] text-gold">{y.caution}</p>
                    </div>
                  );
                })}
              </div>
            )}
          </SectionCard>

          {result?.reasoning && (
            <SectionCard title="说明">
              <p className="text-sm leading-relaxed text-ink-600 dark:text-ink-300">
                {result.reasoning}
              </p>
              {result.summary && result.summary.length > 0 && (
                <ul className="mt-2 list-inside list-disc text-xs text-ink-500">
                  {result.summary.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              )}
            </SectionCard>
          )}
        </div>
      )}
    </div>
  );
}
