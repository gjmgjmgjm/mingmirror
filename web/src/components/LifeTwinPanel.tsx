import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  Cloud,
  CloudRain,
  CloudSun,
  Download,
  ScrollText,
  Sparkles,
  Sun,
  Target,
  Users,
} from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import {
  fetchDailyFortune,
  fetchBaziTimeline,
  fetchLatestCalibration,
  exportChartPackage,
  exportBaziPackage,
  downloadTextFile,
  openHtmlPrint,
  type DailyFortuneResponse,
  type BaziTimelineResponse,
  type CalibrationResponse,
} from "../api/client";
import {
  canExportFullPackage,
  getEntitlement,
  refreshEntitlementFromServer,
  type Entitlement,
} from "../lib/entitlements";
import { getDeviceId } from "../lib/analytics";

const WEATHER_ICONS: Record<string, React.ReactNode> = {
  晴: <Sun className="h-7 w-7 text-gold" />,
  多云: <CloudSun className="h-7 w-7 text-gold" />,
  阴: <Cloud className="h-7 w-7 text-ink-500" />,
  雨: <CloudRain className="h-7 w-7 text-blue-500" />,
};

function currentDayun(
  timeline: BaziTimelineResponse | null,
  birthYear: number | null
): { pillar: string; range: string; blurb: string } | null {
  if (!timeline?.dayun?.length) return null;
  const year = new Date().getFullYear();
  let age: number | null = null;
  if (birthYear && birthYear > 1900 && birthYear <= year) {
    age = year - birthYear;
  }
  let pick = timeline.dayun[0];
  if (age != null) {
    const hit = timeline.dayun.find(
      (d) => age! >= d.start_age && age! < d.end_age
    );
    if (hit) pick = hit;
  } else if (timeline.dayun.some((d) => d.start_year != null)) {
    const hit = timeline.dayun.find(
      (d) =>
        d.start_year != null &&
        d.end_year != null &&
        year >= d.start_year &&
        year <= d.end_year
    );
    if (hit) pick = hit;
  }
  const range =
    pick.start_year != null && pick.end_year != null
      ? `${pick.start_year}–${pick.end_year}`
      : `${Math.round(pick.start_age)}–${Math.round(pick.end_age)}岁`;
  return {
    pillar: pick.pillar,
    range,
    blurb: `当前大运「${pick.pillar}」（${range}），宜结合用神看十年主题。`,
  };
}

export default function LifeTwinPanel() {
  const { chart, chartScopeId } = useChart();
  const [daily, setDaily] = useState<DailyFortuneResponse | null>(null);
  const [timeline, setTimeline] = useState<BaziTimelineResponse | null>(null);
  const [calibration, setCalibration] = useState<CalibrationResponse | null>(null);
  const [ent, setEnt] = useState<Entitlement>(() => getEntitlement());
  const [exporting, setExporting] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    const sync = () => setEnt(getEntitlement());
    window.addEventListener("mingmirror-entitlement", sync);
    window.addEventListener("storage", sync);
    void refreshEntitlementFromServer().then(setEnt);
    return () => {
      window.removeEventListener("mingmirror-entitlement", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  useEffect(() => {
    if (!chart?.bazi) return;
    let cancelled = false;
    (async () => {
      try {
        const d = await fetchDailyFortune({ bazi: chart.bazi });
        if (!cancelled) setDaily(d);
      } catch {
        if (!cancelled) setDaily(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chart?.bazi]);

  useEffect(() => {
    if (!chart?.bazi || !chart.birthDate) {
      setTimeline(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const t = await fetchBaziTimeline(
          chart.bazi,
          chart.gender || "male",
          chart.birthDate,
          chart.birthTime || "12:00",
          chart.calendarType || "solar"
        );
        if (!cancelled) setTimeline(t);
      } catch {
        if (!cancelled) setTimeline(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chart?.bazi, chart?.gender, chart?.birthDate, chart?.birthTime, chart?.calendarType]);

  useEffect(() => {
    if (!chartScopeId) {
      setCalibration(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const c = await fetchLatestCalibration(chartScopeId);
        if (!cancelled) setCalibration(c);
      } catch {
        if (!cancelled) setCalibration(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chartScopeId]);

  if (!chart) return null;

  const birthYear = chart.birthDate
    ? parseInt(chart.birthDate.slice(0, 4), 10)
    : null;
  const dayun = currentDayun(timeline, Number.isFinite(birthYear) ? birthYear : null);
  const needsCalibration = !calibration || calibration.event_count === 0;
  const weather = daily?.weather || "多云";
  const canExport = canExportFullPackage(ent);
  const [exportStartYear, setExportStartYear] = useState(
    () => new Date().getFullYear()
  );
  const [exportYears, setExportYears] = useState<5 | 10 | 15 | 20>(10);

  const handleExport = async () => {
    setMsg(null);
    // 服务端在 export 端点权威校验 + 扣次(非 pro);此处 canExportFullPackage 为 UI 预检。
    if (!canExportFullPackage(getEntitlement())) {
      setMsg("体验版需开通完整版或购买交付包次数，见下方套餐。");
      return;
    }
    setExporting(true);
    try {
      const rangeOpts = {
        liunian_start_year: exportStartYear,
        liunian_years: exportYears,
      };
      const deviceId = getDeviceId();
      const pkg =
        chart.id
          ? await exportChartPackage(chart.id, rangeOpts, deviceId)
          : await exportBaziPackage(
              {
                bazi: chart.bazi,
                gender: chart.gender || "male",
                birth_date: chart.birthDate || "",
                birth_time: chart.birthTime || "",
                calendar_type: chart.calendarType || "solar",
                label: chart.label || chart.bazi,
                ...rangeOpts,
              },
              deviceId
            );
      openHtmlPrint(pkg.html);
      downloadTextFile(pkg.markdown, `${pkg.filename_stem}.md`, "text/markdown");
      // 服务端刚扣过次,刷新本地权益使额度显示同步
      void refreshEntitlementFromServer().then(() => setEnt(getEntitlement()));
      setMsg(
        `已导出（流年 ${exportStartYear} 起 ${exportYears} 年，含「今年」高亮），打印页与 Markdown 已生成。`
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : "导出失败";
      setMsg(
        msg.includes("402")
          ? "完整交付包需开通套餐或购买次数，请前往套餐页。"
          : msg
      );
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-4 animate-fade-up">
      {/* Hero status */}
      <section className="panel mesh-bg relative overflow-hidden p-5 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-widest text-ink-400">
              人生数字孪生
            </p>
            <h2 className="mt-1 font-display text-2xl text-ink-800 dark:text-ink-100">
              今日运势 · {weather}
            </h2>
            <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
              {chart.bazi}
              {chart.id && (
                <span className="ml-2 text-xs text-ink-400">
                  ID {chart.id.slice(0, 8)}…
                </span>
              )}
            </p>
          </div>
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-ink-100/80 dark:bg-ink-800/80">
            {WEATHER_ICONS[weather] ?? WEATHER_ICONS["多云"]}
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-ink-300/20 bg-white/50 p-3 dark:border-ink-600/30 dark:bg-ink-900/40">
            <div className="text-[11px] text-ink-400">今日天气</div>
            <div className="mt-0.5 text-sm font-medium text-ink-700 dark:text-ink-200">
              {daily?.weather_label || daily?.description || "加载中…"}
            </div>
            {daily?.dos?.[0] && (
              <div className="mt-1 truncate text-[11px] text-jade">
                宜 {daily.dos[0]}
              </div>
            )}
          </div>
          <div className="rounded-xl border border-ink-300/20 bg-white/50 p-3 dark:border-ink-600/30 dark:bg-ink-900/40">
            <div className="text-[11px] text-ink-400">当前大运</div>
            {dayun ? (
              <>
                <div className="mt-0.5 font-display text-lg text-ink-800 dark:text-ink-100">
                  {dayun.pillar}
                </div>
                <div className="text-[11px] text-ink-500">{dayun.range}</div>
              </>
            ) : (
              <div className="mt-0.5 text-sm text-ink-500">
                {chart.birthDate
                  ? "推算中或暂无数据"
                  : "填写出生日期后显示大运"}
              </div>
            )}
          </div>
          <div className="rounded-xl border border-ink-300/20 bg-white/50 p-3 dark:border-ink-600/30 dark:bg-ink-900/40">
            <div className="text-[11px] text-ink-400">个人模型</div>
            {calibration && calibration.event_count > 0 ? (
              <>
                <div className="mt-0.5 text-sm font-medium text-jade">
                  已校准 · {calibration.event_count} 事件
                </div>
                <div className="text-[11px] text-ink-500">
                  均分 {(calibration.average_score * 100).toFixed(0)}%
                </div>
              </>
            ) : (
              <>
                <div className="mt-0.5 text-sm font-medium text-gold">未校准</div>
                <Link
                  to="/events"
                  className="mt-1 inline-flex items-center text-[11px] text-vermilion hover:underline"
                >
                  用 1～3 件真事校准
                  <ArrowRight className="ml-0.5 h-3 w-3" />
                </Link>
              </>
            )}
          </div>
        </div>

        {dayun && (
          <p className="mt-3 text-xs leading-relaxed text-ink-500 dark:text-ink-400">
            {dayun.blurb}
          </p>
        )}
      </section>

      {/* CTAs */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex flex-col gap-2 rounded-xl border border-vermilion/30 bg-vermilion/10 p-4 sm:col-span-2 lg:col-span-1">
          <button
            type="button"
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-3 text-left transition disabled:opacity-50"
          >
            <Download className="h-5 w-5 shrink-0 text-vermilion" />
            <div>
              <div className="text-sm font-medium text-ink-800 dark:text-ink-100">
                {exporting ? "导出中…" : "导出命书"}
              </div>
              <div className="text-[11px] text-ink-500">
                {canExport
                  ? ent.plan === "pro"
                    ? "完整版 · 无限次"
                    : `剩余 ${ent.packageCredits} 次`
                  : "需开通套餐"}
              </div>
            </div>
          </button>
          <div className="flex flex-wrap items-center gap-2 border-t border-vermilion/20 pt-2">
            <label className="text-[10px] text-ink-500">
              流年起
              <input
                type="number"
                className="input ml-1 w-20 py-0.5 text-[11px]"
                value={exportStartYear}
                min={1900}
                max={2100}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (!Number.isNaN(v)) setExportStartYear(v);
                }}
              />
            </label>
            <label className="text-[10px] text-ink-500">
              跨度
              <select
                className="input ml-1 w-16 py-0.5 text-[11px]"
                value={exportYears}
                onChange={(e) =>
                  setExportYears(Number(e.target.value) as 5 | 10 | 15 | 20)
                }
              >
                {[5, 10, 15, 20].map((n) => (
                  <option key={n} value={n}>
                    {n}年
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <Link
          to="/chart/report"
          className="flex items-center gap-3 rounded-xl border border-ink-300/30 bg-ink-100/50 p-4 transition hover:bg-ink-200/50 dark:border-ink-600/30 dark:bg-ink-800/40"
        >
          <BookOpen className="h-5 w-5 shrink-0 text-gold" />
          <div>
            <div className="text-sm font-medium text-ink-800 dark:text-ink-100">
              在线命书
            </div>
            <div className="text-[11px] text-ink-500">结构层解读报告</div>
          </div>
        </Link>
        <Link
          to="/calendar"
          className="flex items-center gap-3 rounded-xl border border-ink-300/30 bg-ink-100/50 p-4 transition hover:bg-ink-200/50 dark:border-ink-600/30 dark:bg-ink-800/40"
        >
          <CalendarDays className="h-5 w-5 shrink-0 text-jade" />
          <div>
            <div className="text-sm font-medium text-ink-800 dark:text-ink-100">
              择日引擎
            </div>
            <div className="text-[11px] text-ink-500">近 60 日良辰</div>
          </div>
        </Link>
        <Link
          to="/events"
          className="flex items-center gap-3 rounded-xl border border-ink-300/30 bg-ink-100/50 p-4 transition hover:bg-ink-200/50 dark:border-ink-600/30 dark:bg-ink-800/40"
        >
          <Target className="h-5 w-5 shrink-0 text-vermilion" />
          <div>
            <div className="text-sm font-medium text-ink-800 dark:text-ink-100">
              事件校准
            </div>
            <div className="text-[11px] text-ink-500">
              {needsCalibration ? "推荐完成" : "更新权重"}
            </div>
          </div>
        </Link>
      </section>

      {msg && (
        <p className="text-center text-xs text-ink-500 dark:text-ink-400">{msg}</p>
      )}

      {/* Secondary nav chips */}
      <section className="flex flex-wrap gap-2">
        {[
          { to: "/chart", label: "八字分析", icon: ScrollText },
          { to: "/ziwei", label: "紫微斗数", icon: Sparkles },
          { to: "/qizheng", label: "七政四余", icon: CalendarDays },
          { to: "/council", label: "命理议会", icon: Users },
          { to: "/sandbox", label: "合婚沙盒", icon: Sparkles },
          { to: "/pricing", label: "套餐", icon: BookOpen },
        ].map(({ to, label, icon: Icon }) => (
          <Link
            key={to}
            to={to}
            className="inline-flex items-center gap-1.5 rounded-full border border-ink-300/30 bg-ink-100/40 px-3 py-1.5 text-xs text-ink-600 transition hover:border-vermilion/40 hover:text-vermilion dark:border-ink-600/30 dark:bg-ink-800/40 dark:text-ink-300"
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </Link>
        ))}
      </section>

      {/* Plan strip */}
      <section className="rounded-xl border border-gold/25 bg-gold/5 px-4 py-3 text-xs text-ink-600 dark:text-ink-300">
        当前套餐：
        <span className="font-medium text-gold">
          {ent.plan === "pro" ? "完整版" : "体验版"}
        </span>
        {ent.plan === "pro" && ent.expiresAt && (
          <span className="text-ink-400">
            {" "}
            · 至 {new Date(ent.expiresAt).toLocaleDateString()}
          </span>
        )}
        {ent.plan === "free" && (
          <Link to="/pricing" className="ml-2 text-vermilion underline">
            升级完整版
          </Link>
        )}
        <span className="mx-2 text-ink-300">|</span>
        内容仅供参考，不构成医疗 / 法律 / 投资建议
      </section>
    </div>
  );
}
