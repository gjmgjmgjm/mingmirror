import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useChart } from "../contexts/ChartContext";
import { fetchBaziReport, type ReportData, type ReportSection } from "../api/client";
import { ELEMENT_META, type Element } from "../lib/bazi";
import ChartLoader from "../components/ChartLoader";
import PillarsChart from "../components/PillarsChart";
import {
  SectionCard,
  InfoCard,
  DomainCard,
  EmptyState,
  SealStamp,
  CloudDivider,
  ErrorPanel,
} from "../components/ui";

const CN_NUM = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];

const BORDER_BY_ID: Record<string, "vermilion" | "gold" | "jade" | "ink"> = {
  chart: "gold",
  yongshen: "jade",
  dayun: "gold",
  summary: "jade",
};

const ELEMENT_KEY: Record<string, Element> = {
  木: "wood", 火: "fire", 土: "earth", 金: "metal", 水: "water",
};

// ---------------------------------------------------------------------------
// 可信度标记
// ---------------------------------------------------------------------------

function TrustBadge({ type }: { type: "certain" | "ai" }) {
  const certain = type === "certain";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 align-middle text-[11px] font-medium ${
        certain
          ? "border-jade/40 bg-jade/10 text-jade"
          : "border-gold/40 bg-gold/10 text-gold"
      }`}
    >
      {certain ? "✓ 确定性" : "◐ AI 推理"}
    </span>
  );
}

// ---------------------------------------------------------------------------
// 五行分布(消费后端 report 的 elements)
// ---------------------------------------------------------------------------

interface ElementItem {
  element: string;
  count: number;
  percent: number;
}

function ElementsBlock({ elements }: { elements: ElementItem[] }) {
  return (
    <div className="mt-4 rounded-xl bg-ink-100/50 p-4 dark:bg-ink-800/50">
      <h4 className="mb-3 text-sm font-medium text-ink-600 dark:text-ink-300">
        五行能量分布
        <span className="ml-2 text-xs font-normal text-ink-400">确定性 · 天干地支计数</span>
      </h4>
      <div className="space-y-2">
        {elements.map(({ element, count, percent }) => {
          const m = ELEMENT_META[ELEMENT_KEY[element] ?? "wood"];
          return (
            <div key={element} className="flex items-center gap-2">
              <span className={`w-5 text-center text-sm ${m.color}`}>{element}</span>
              <div className="flex-1 overflow-hidden rounded-full bg-ink-200/40 dark:bg-ink-700/40">
                <div
                  className={`h-2 rounded-full ${m.bg.replace("/10", "").replace("/20", "")}`}
                  style={{ width: `${percent}%` }}
                />
              </div>
              <span className="w-16 text-right text-xs text-ink-500 dark:text-ink-400">
                {count} 字 · {percent}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 章节正文(按 section.id 渲染,消费 section.data)
// ---------------------------------------------------------------------------

function SectionBody({ section, bazi }: { section: ReportSection; bazi: string }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const d: Record<string, any> = section.data ?? {};

  switch (section.id) {
    case "chart":
      return (
        <>
          <PillarsChart bazi={bazi} />
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <InfoCard label="日主" value={d.day_master || "—"} term="日主" />
            <InfoCard label="格局" value={d.geju || "—"} term="格局" />
            <InfoCard label="月令" value={d.month_branch || "—"} term="月令" />
          </div>
          {d.daymaster_trait && (
            <p className="mt-3 text-sm text-ink-500 dark:text-ink-400">
              日主「{d.day_master}」:{d.daymaster_trait}
            </p>
          )}
          {Array.isArray(d.elements) && d.elements.length > 0 && (
            <ElementsBlock elements={d.elements} />
          )}
        </>
      );

    case "yongshen": {
      const useful = Array.isArray(d.useful_gods) ? d.useful_gods.join("、") : "—";
      const taboo = Array.isArray(d.taboo_gods) ? d.taboo_gods.join("、") : "—";
      return (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl bg-jade/10 p-4 dark:bg-jade/15">
              <div className="text-xs font-medium text-jade">用神 · 顺势成长方向</div>
              <div className="mt-1 text-2xl font-semibold text-jade">{useful}</div>
            </div>
            <div className="rounded-xl bg-vermilion/10 p-4 dark:bg-vermilion/15">
              <div className="text-xs font-medium text-vermilion">忌神 · 需规避化解</div>
              <div className="mt-1 text-2xl font-semibold text-vermilion">{taboo}</div>
            </div>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-ink-400">
            由扶抑 + 调候 + 通关 engine 判定,与《穷通宝鉴》调候用神在 n=92 真实命主上
            90.2% 一致。
          </p>
        </>
      );
    }

    case "liuqin":
      return (
        <>
          {Array.isArray(d.members) && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
              {d.members.map(
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                (m: any) => (
                  <div
                    key={m.key}
                    className="rounded-lg bg-ink-100/50 p-3 text-center dark:bg-ink-800/50"
                  >
                    <div className="text-xs text-ink-500 dark:text-ink-400">{m.label}</div>
                    <div
                      className={`mt-1 text-lg font-semibold ${
                        m.strength === "强"
                          ? "text-jade"
                          : m.strength === "弱"
                            ? "text-vermilion"
                            : "text-ink-400"
                      }`}
                    >
                      {m.strength || "—"}
                    </div>
                  </div>
                )
              )}
            </div>
          )}
          {d.liuqin_analysis && (
            <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-ink-600 dark:text-ink-300">
              {d.liuqin_analysis}
            </p>
          )}
        </>
      );

    case "quxiang": {
      const items: Array<[string, string]> = [
        ["日主取象", d.day_master],
        ["关键十神取象", d.key_shishen],
        ["职业取象", d.career],
        ["健康取象", d.health],
      ].filter(([, v]) => v) as Array<[string, string]>;
      return (
        <div className="space-y-4">
          {items.map(([label, text]) => (
            <div key={label}>
              <div className="mb-1 text-sm font-medium text-vermilion">{label}</div>
              <p className="text-sm leading-relaxed text-ink-600 dark:text-ink-300">{text}</p>
            </div>
          ))}
        </div>
      );
    }

    case "life":
      return (
        <>
          {d.personality && (
            <blockquote className="relative mb-4 border-l-4 border-vermilion bg-ink-100/40 p-4 text-ink-700 dark:border-vermilion-light dark:bg-ink-800/40 dark:text-ink-200">
              <span className="absolute left-2 top-1 text-2xl text-vermilion/20">&ldquo;</span>
              <p className="pl-4 leading-relaxed">{d.personality}</p>
            </blockquote>
          )}
          {Array.isArray(d.domains) && d.domains.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2">
              {d.domains.map(
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                (dm: any) => (
                  <DomainCard key={dm.key} title={dm.label} text={dm.text} />
                )
              )}
            </div>
          )}
          {Array.isArray(d.events) && d.events.length > 0 && (
            <div className="mt-4">
              <h4 className="mb-2 text-sm font-medium text-ink-600 dark:text-ink-300">
                趋势提示
              </h4>
              <ul className="space-y-2">
                {d.events.map((item: string, idx: number) => (
                  <li
                    key={idx}
                    className="flex gap-2 rounded-lg bg-ink-100/40 p-2 text-sm text-ink-600 dark:bg-ink-800/40 dark:text-ink-300"
                  >
                    <span className="text-gold">·</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      );

    case "wealth_marriage":
      return (
        <div className="grid gap-4 sm:grid-cols-2">
          {d.wealth_level && (
            <DomainCard
              title="原局财富潜力"
              text={`${d.wealth_level}${d.wealth_evidence ? `。${d.wealth_evidence}` : ""}`}
            />
          )}
          {d.marriage_status && (
            <DomainCard
              title="婚姻基调"
              text={`${d.marriage_status}${d.marriage_evidence ? `。${d.marriage_evidence}` : ""}`}
            />
          )}
        </div>
      );

    case "dayun":
      if (Array.isArray(d.pillars) && d.pillars.length > 0) {
        return (
          <div className="flex flex-wrap gap-2">
            {d.pillars.map(
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              (p: any, i: number) => (
                <div
                  key={i}
                  className="min-w-[72px] rounded-lg border border-ink-300/20 bg-white/60 px-3 py-2 text-center dark:border-ink-500/20 dark:bg-ink-800/60"
                >
                  <div className="text-[11px] text-ink-500 dark:text-ink-400">
                    {p.start_age}–{p.end_age}岁
                  </div>
                  <div className="text-lg font-semibold text-ink-700 dark:text-ink-200">
                    {p.pillar}
                  </div>
                </div>
              )
            )}
          </div>
        );
      }
      return (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-600 dark:text-ink-300">
          {d.summary}
        </p>
      );

    case "milestones":
      return (
        <div className="flex flex-wrap gap-2">
          {Array.isArray(d.milestones) &&
            d.milestones.map(
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              (m: any, idx: number) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-ink-100/60 px-3 py-1.5 text-sm text-ink-700 dark:bg-ink-800/60 dark:text-ink-200"
                >
                  <span className="font-semibold text-vermilion">{m.year}年</span>
                  <span className="text-xs text-ink-500 dark:text-ink-400">({m.age}岁)</span>
                  <span>{m.type}</span>
                </span>
              )
            )}
        </div>
      );

    case "summary":
      return (
        <>
          {Array.isArray(d.summary) && d.summary.length > 0 && (
            <ul className="space-y-3">
              {d.summary.map((item: string, idx: number) => (
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
          )}
          {Array.isArray(d.caveats) && d.caveats.length > 0 && (
            <div className="mt-4">
              <h4 className="mb-2 text-sm font-medium text-ink-600 dark:text-ink-300">
                可能的误差来源
              </h4>
              <ul className="list-inside list-disc space-y-1 text-sm text-ink-500 dark:text-ink-400">
                {d.caveats.map((item: string, idx: number) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      );

    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// 主组件
// ---------------------------------------------------------------------------

export default function ReadingReport() {
  const { chart } = useChart();
  const [report, setReport] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!chart) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setReport(null);

    (async () => {
      try {
        const res = await fetchBaziReport(
          chart.bazi,
          chart.gender,
          chart.birthDate,
          chart.birthTime || "00:00",
          chart.calendarType || "solar"
        );
        if (!cancelled) setReport(res.report);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "报告生成失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [chart?.bazi, chart?.gender, chart?.birthDate, chart?.birthTime]);

  if (!chart) {
    return (
      <EmptyState
        title="暂无命盘"
        description="请先在首页输入八字信息,再生成解读报告。"
        action={
          <Link to="/" className="btn-primary inline-flex">
            前往首页
          </Link>
        }
      />
    );
  }

  const sections = report?.sections ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* 报告头 */}
      <SectionCard borderLeft="vermilion" delay={0}>
        <div className="flex items-start gap-4">
          <SealStamp size="lg" variant="vermilion">
            命書
          </SealStamp>
          <div className="flex-1">
            <h1 className="font-display text-2xl text-ink-700 dark:text-ink-200">
              命盘解读报告
            </h1>
            <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
              {chart.bazi}　·　{report?.meta?.gender_label ?? ""}
            </p>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-500 dark:text-ink-400">
              <span className="inline-flex items-center gap-1">
                <span className="text-jade">✓</span> 确定性(排盘 / 格局 / 用神 / 六亲 / 大运)
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="text-gold">◐</span> AI 趋势(取象 / 领域 / 节点 / 断语)
              </span>
            </div>
            <p className="mt-2 text-[11px] text-ink-400">
              本报告不构成医疗 / 法律 / 投资建议。
            </p>
          </div>
        </div>
      </SectionCard>

      <CloudDivider variant="vermilion" />

      {loading && <ChartLoader />}

      {error && <ErrorPanel title="报告生成出错">{error}</ErrorPanel>}

      {report && sections.length > 0 && (
        <>
          {sections.map((s, i) => (
            <SectionCard
              key={s.id}
              title={
                <>
                  <span className="font-display text-vermilion">{CN_NUM[i] ?? i + 1}</span>
                  、{s.title}
                  <span className="ml-2">
                    <TrustBadge type={s.trust} />
                  </span>
                </>
              }
              borderLeft={BORDER_BY_ID[s.id]}
              delay={i * 80}
            >
              <SectionBody section={s} bazi={report.meta.bazi} />
            </SectionCard>
          ))}

          <CloudDivider variant="ink" />
          <p className="text-center text-xs leading-relaxed text-ink-400">
            结构层由确定性算法计算(排盘对齐 iztro、用神对齐穷通宝鉴、六亲星宫同参),
            <br />
            AI 章节为趋势性参考,具体年份事件为概率倾向,非确定性预言。
          </p>
        </>
      )}
    </div>
  );
}
