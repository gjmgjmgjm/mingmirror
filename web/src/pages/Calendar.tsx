import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Download } from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import {
  fetchBaziAuspicious,
  type AuspiciousResponse,
  type AuspiciousDay,
} from "../api/client";
import ChartLoader from "../components/ChartLoader";
import {
  SectionCard,
  PageHeader,
  CloudDivider,
  ToggleGroup,
  EmptyState,
  ErrorPanel,
} from "../components/ui";

const EVENT_OPTIONS = [
  { value: "marriage", label: "嫁娶" },
  { value: "opening", label: "开业" },
  { value: "moving", label: "入宅" },
  { value: "travel", label: "出行" },
  { value: "signing", label: "签约" },
  { value: "interview", label: "求职" },
];

const WEEK = ["日", "一", "二", "三", "四", "五", "六"];
const WEATHER_ICON: Record<string, string> = { 晴: "☀", 多云: "⛅", 阴: "☁", 雨: "🌧" };

function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

function scoreColor(score?: number): string {
  if (score === undefined) return "text-ink-300 dark:text-ink-600";
  if (score >= 70) return "bg-jade/15 text-jade font-medium dark:bg-jade/20";
  if (score >= 50) return "bg-ink-100/70 text-ink-600 dark:bg-ink-800/70 dark:text-ink-300";
  if (score >= 35) return "bg-gold/10 text-gold dark:bg-gold/15";
  return "bg-vermilion/10 text-vermilion dark:bg-vermilion/15";
}

function scoreBadge(score: number): string {
  if (score >= 70) return "bg-jade text-white";
  if (score >= 50) return "bg-ink-400 text-white dark:bg-ink-500";
  if (score >= 35) return "bg-gold text-white";
  return "bg-vermilion text-white";
}

function downloadIcs(dateStr: string, label: string): void {
  const dt = dateStr.replace(/-/g, "");
  const ics = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//MingMirror//ZH",
    "BEGIN:VEVENT",
    `UID:${dateStr}@mingmirror`,
    `DTSTART;VALUE=DATE:${dt}`,
    `SUMMARY:命镜择日·${label}`,
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");
  const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `mingmirror_${dateStr}.ics`;
  a.click();
  URL.revokeObjectURL(url);
}

function MonthGrid({ days, offset }: { days: AuspiciousDay[]; offset: number }) {
  const scoreMap = new Map(days.map((d) => [d.date, d.score]));
  const base = new Date();
  base.setMonth(base.getMonth() + offset);
  const year = base.getFullYear();
  const month = base.getMonth();
  const firstWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: Array<{ day: number; iso: string; score?: number } | null> = [];
  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    cells.push({ day: d, iso, score: scoreMap.get(iso) });
  }
  return (
    <div className="rounded-xl border border-ink-300/20 bg-ink-100/30 p-4 dark:border-ink-500/20 dark:bg-ink-800/30">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-display text-xl text-ink-800 dark:text-ink-100">
          {year}年{month + 1}月
        </span>
        <span className="text-xs text-ink-400">宜 / 平 / 忌</span>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center">
        {WEEK.map((w) => (
          <div key={w} className="py-1.5 text-xs text-ink-400">
            {w}
          </div>
        ))}
        {cells.map((c, i) =>
          c === null ? (
            <div key={i} />
          ) : (
            <div key={i} className={`rounded-lg py-1.5 text-sm ${scoreColor(c.score)}`}>
              <div>{c.day}</div>
              {c.score !== undefined && (
                <div className="text-[10px] opacity-70">{c.score}</div>
              )}
            </div>
          )
        )}
      </div>
    </div>
  );
}

export default function Calendar() {
  const { chart } = useChart();
  const [eventType, setEventType] = useState("marriage");
  const [data, setData] = useState<AuspiciousResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!chart) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    const today = new Date();
    const dateFrom = isoOf(today);
    const end = new Date(today.getTime() + 59 * 86400000);
    const dateTo = isoOf(end);
    (async () => {
      try {
        const res = await fetchBaziAuspicious(
          chart.bazi,
          chart.gender || "male",
          eventType,
          dateFrom,
          dateTo
        );
        if (!cancelled) setData(res);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "择日失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chart?.bazi, chart?.gender, eventType]);

  if (!chart) {
    return (
      <EmptyState
        title="暂无命盘"
        description="请先在首页输入八字信息,择日引擎将结合你的用神喜忌推荐吉日。"
        action={
          <Link to="/" className="btn-primary inline-flex">
            前往首页
          </Link>
        }
      />
    );
  }

  const days = data?.days ?? [];
  const topDays = days.slice(0, 8);
  const eventLabel =
    EVENT_OPTIONS.find((e) => e.value === eventType)?.label ?? eventType;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <PageHeader
        title="择日引擎"
        subtitle={`结合命主用神喜忌与冲合,为目标推荐良辰吉日 · ${chart.bazi}`}
      />

      <CloudDivider variant="gold" />

      <SectionCard>
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-medium text-ink-600 dark:text-ink-300">选择事项</h3>
          <ToggleGroup
            options={EVENT_OPTIONS}
            value={eventType}
            onChange={(v) => setEventType(v)}
          />
        </div>
        {data && (data.useful_gods.length > 0 || data.taboo_gods.length > 0) && (
          <div className="flex flex-wrap gap-3 text-sm">
            <span className="rounded-lg bg-jade/10 px-3 py-1.5 text-jade dark:bg-jade/15">
              命主用神:{data.useful_gods.join("、") || "—"}
            </span>
            <span className="rounded-lg bg-vermilion/10 px-3 py-1.5 text-vermilion dark:bg-vermilion/15">
              忌神:{data.taboo_gods.join("、") || "—"}
            </span>
            <span className="rounded-lg bg-ink-100/60 px-3 py-1.5 text-ink-500 dark:bg-ink-800/60">
              未来 60 天
            </span>
          </div>
        )}
      </SectionCard>

      {loading && <ChartLoader />}

      {error && <ErrorPanel title="择日出错">{error}</ErrorPanel>}

      {data && days.length > 0 && (
        <>
          <SectionCard
            title={
              <>
                <span className="font-display text-vermilion">一</span>、良辰吉日 · {eventLabel}
                <span className="ml-2 text-xs font-normal text-jade">
                  ✓ 基于用神 + 冲合规则
                </span>
              </>
            }
            borderLeft="gold"
            delay={0}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              {topDays.map((d, idx) => (
                <div
                  key={d.date}
                  className="flex gap-3 rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40"
                >
                  <div
                    className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-lg font-bold ${scoreBadge(
                      d.score
                    )}`}
                  >
                    {d.score}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="font-display text-lg text-ink-800 dark:text-ink-100">
                        {d.day_pillar}
                      </span>
                      <span className="text-xs text-ink-500 dark:text-ink-400">{d.date}</span>
                      <span className="text-base">{WEATHER_ICON[d.weather] ?? ""}</span>
                      {idx === 0 && (
                        <span className="ml-auto rounded bg-gold px-1.5 py-0.5 text-[10px] font-medium text-white">
                          首吉
                        </span>
                      )}
                    </div>
                    <div className="mb-1 text-xs text-ink-500 dark:text-ink-400">
                      当日透「{d.shishen}」
                    </div>
                    <p className="mb-2 text-xs leading-relaxed text-ink-600 dark:text-ink-300">
                      {d.reasoning}
                    </p>
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex-1 truncate text-[11px] text-jade">
                        宜 {d.dos.join("、")}
                      </div>
                      <button
                        type="button"
                        onClick={() => downloadIcs(d.date, eventLabel)}
                        className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-gold/15 px-2 py-1 text-[11px] text-gold transition hover:bg-gold/25"
                      >
                        <Download className="h-3 w-3" />
                        加日历
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard
            title={
              <>
                <span className="font-display text-vermilion">二</span>、日历总览(未来两月)
              </>
            }
            borderLeft="jade"
            delay={100}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <MonthGrid days={days} offset={0} />
              <MonthGrid days={days} offset={1} />
            </div>
            <div className="mt-4 flex flex-wrap gap-4 text-xs text-ink-500 dark:text-ink-400">
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-jade" />
                宜(≥70)
              </span>
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-ink-400" />
                平
              </span>
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-gold" />
                小忌
              </span>
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-vermilion" />
                忌(&lt;35)
              </span>
            </div>
          </SectionCard>

          <CloudDivider variant="ink" />
          <p className="text-center text-xs leading-relaxed text-ink-400">
            择日基于命主用神(对齐穷通宝鉴)与冲合规则评分,为趋势参考;
            <br />
            传统黄历宜忌因无数据源未纳入,重大事项建议兼顾多方。
          </p>
        </>
      )}

      {data && days.length === 0 && !loading && (
        <SectionCard>
          <p className="text-center text-sm text-ink-500">
            所选区间未能选出吉日,请尝试其他事项或扩大日期范围。
          </p>
        </SectionCard>
      )}
    </div>
  );
}
