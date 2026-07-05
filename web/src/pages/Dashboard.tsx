import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Sparkles,
  ArrowRight,
  RefreshCw,
  MapPin,
  LocateFixed,
  Settings2,
  ChevronDown,
} from "lucide-react";
import { useChart, type ChartInfo, type LocationInfo } from "../contexts/ChartContext";
import { parseBazi } from "../lib/bazi";
import { baziFromDatetime } from "../api/client";
import PillarsChart from "../components/PillarsChart";
import FiveElementBars from "../components/FiveElementBars";
import DailyWeather from "../components/DailyWeather";
import WheelPicker from "../components/WheelPicker";

const DEFAULT_LOCATION: LocationInfo = {
  name: "北京",
  longitude: 116.4074,
  latitude: 39.9042,
  timezone: "Asia/Shanghai",
};

const GENDER_OPTIONS = [
  { value: "", label: "未知" },
  { value: "male", label: "男" },
  { value: "female", label: "女" },
];

const TIMEZONE_OPTIONS: { value: string; label: string }[] = [
  { value: "Asia/Shanghai", label: "上海 / 北京 / 中国标准时间" },
  { value: "Asia/Hong_Kong", label: "香港" },
  { value: "Asia/Taipei", label: "台北" },
  { value: "Asia/Tokyo", label: "东京" },
  { value: "Asia/Seoul", label: "首尔" },
  { value: "Asia/Singapore", label: "新加坡" },
  { value: "Asia/Bangkok", label: "曼谷" },
  { value: "Asia/Dubai", label: "迪拜" },
  { value: "Europe/London", label: "伦敦" },
  { value: "Europe/Paris", label: "巴黎" },
  { value: "Europe/Berlin", label: "柏林" },
  { value: "America/New_York", label: "纽约" },
  { value: "America/Los_Angeles", label: "洛杉矶" },
  { value: "America/Toronto", label: "多伦多" },
  { value: "Australia/Sydney", label: "悉尼" },
  { value: "Pacific/Auckland", label: "奥克兰" },
  { value: "UTC", label: "UTC / 协调世界时" },
];

function buildDate(year: string, month: string, day: string) {
  if (!year || !month || !day) return "";
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

function buildTime(hour: string, minute: string) {
  if (hour === "" || minute === "") return "";
  return `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
}

function getNowParts() {
  const now = new Date();
  return {
    year: String(now.getFullYear()),
    month: String(now.getMonth() + 1).padStart(2, "0"),
    day: String(now.getDate()).padStart(2, "0"),
    hour: String(now.getHours()).padStart(2, "0"),
    minute: String(now.getMinutes()).padStart(2, "0"),
  };
}

const YEAR_OPTIONS = Array.from({ length: 127 }, (_, i) =>
  String(2026 - i)
);
const MONTH_OPTIONS = Array.from({ length: 12 }, (_, i) =>
  String(i + 1).padStart(2, "0")
);
const DAY_OPTIONS = Array.from({ length: 31 }, (_, i) =>
  String(i + 1).padStart(2, "0")
);
const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) =>
  String(i).padStart(2, "0")
);
const MINUTE_OPTIONS = Array.from({ length: 60 }, (_, i) =>
  String(i).padStart(2, "0")
);

export default function Dashboard() {
  const { chart, setChart } = useChart();

  const now = getNowParts();
  const defaultYear = String(new Date().getFullYear() - 25);

  const [birthYear, setBirthYear] = useState(chart?.birthDate ? chart.birthDate.split("-")[0] : defaultYear);
  const [birthMonth, setBirthMonth] = useState(chart?.birthDate ? chart.birthDate.split("-")[1] : now.month);
  const [birthDay, setBirthDay] = useState(chart?.birthDate ? chart.birthDate.split("-")[2] : now.day);
  const [birthHour, setBirthHour] = useState(chart?.birthTime ? chart.birthTime.split(":")[0] : now.hour);
  const [birthMinute, setBirthMinute] = useState(chart?.birthTime ? chart.birthTime.split(":")[1] : now.minute);
  const [savedTime, setSavedTime] = useState({
    hour: chart?.birthTime ? chart.birthTime.split(":")[0] : now.hour,
    minute: chart?.birthTime ? chart.birthTime.split(":")[1] : now.minute,
  });
  const [timeUnknown, setTimeUnknown] = useState(false);
  const [gender, setGender] = useState(chart?.gender ?? "");
  const [calendarType, setCalendarType] = useState<"solar" | "lunar">(chart?.calendarType ?? "solar");

  const [previewBazi, setPreviewBazi] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [locationName, setLocationName] = useState(
    chart?.location?.name ?? DEFAULT_LOCATION.name
  );
  const [longitude, setLongitude] = useState(
    chart?.location?.longitude ?? DEFAULT_LOCATION.longitude
  );
  const [latitude, setLatitude] = useState(
    chart?.location?.latitude ?? DEFAULT_LOCATION.latitude
  );
  const [timezone, setTimezone] = useState(
    chart?.location?.timezone ?? DEFAULT_LOCATION.timezone
  );
  const [locateError, setLocateError] = useState<string | null>(null);

  const [useManualBazi, setUseManualBazi] = useState(false);

  // Debounced bazi preview when date/time/calendar changes.
  useEffect(() => {
    if (useManualBazi) {
      setPreviewBazi(null);
      setPreviewError(null);
      return;
    }
    const date = buildDate(birthYear, birthMonth, birthDay);
    const time = buildTime(birthHour, birthMinute);
    if (!date || !time) {
      setPreviewBazi(null);
      return;
    }
    setPreviewLoading(true);
    const timer = setTimeout(async () => {
      try {
        const result = await baziFromDatetime(`${date}T${time}`, calendarType);
        setPreviewBazi(result.bazi);
        setPreviewError(null);
      } catch (err) {
        setPreviewBazi(null);
        setPreviewError(err instanceof Error ? err.message : "八字预览失败");
      } finally {
        setPreviewLoading(false);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [birthYear, birthMonth, birthDay, birthHour, birthMinute, calendarType, useManualBazi]);
  const [manualBazi, setManualBazi] = useState(chart?.bazi ?? "");

  const [deriving, setDeriving] = useState(false);
  const [locating, setLocating] = useState(false);
  const [deriveError, setDeriveError] = useState<string | null>(null);
  const [animateKey, setAnimateKey] = useState(0);

  const parsed = chart ? parseBazi(chart.bazi) : null;

  const birthDate = buildDate(birthYear, birthMonth, birthDay);
  const birthTime = buildTime(birthHour, birthMinute);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setDeriveError(null);

    let bazi = "";

    if (useManualBazi) {
      const trimmed = manualBazi.trim();
      if (!trimmed || !parseBazi(trimmed)) {
        setDeriveError("请输入正确的四柱八字，例如：甲子 乙丑 丙寅 丁卯");
        return;
      }
      bazi = trimmed;
    } else {
      if (!birthDate || !birthTime) {
        setDeriveError("请选择出生日期和时间");
        return;
      }
      setDeriving(true);
      try {
        const result = await baziFromDatetime(
          `${birthDate}T${birthTime}`,
          calendarType
        );
        bazi = result.bazi;
      } catch (err) {
        const message = err instanceof Error ? err.message : "八字推导失败";
        setDeriveError(message);
        setDeriving(false);
        return;
      }
      setDeriving(false);
    }

    const next: ChartInfo = {
      bazi,
      gender,
      birthDate: useManualBazi ? "" : birthDate,
      birthTime: useManualBazi ? "" : birthTime,
      calendarType: useManualBazi ? undefined : calendarType,
      location: {
        name: locationName,
        longitude,
        latitude,
        timezone,
      },
    };
    setChart(next);
    setAnimateKey((k) => k + 1);
  };

  const handleReplay = () => {
    if (parsed) setAnimateKey((k) => k + 1);
  };

  const handleLocate = () => {
    if (!navigator.geolocation) {
      setLocateError("当前浏览器不支持自动定位");
      return;
    }
    setLocating(true);
    setLocateError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLongitude(Number(pos.coords.longitude.toFixed(4)));
        setLatitude(Number(pos.coords.latitude.toFixed(4)));
        setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone);
        setLocating(false);
      },
      () => {
        setLocating(false);
        setLocateError("自动定位失败，请手动输入城市与经纬度");
      }
    );
  };

  return (
    <div className="relative mx-auto max-w-5xl space-y-8">
      <section className="relative panel mesh-bg px-6 py-12 text-center md:px-12 animate-fade-up overflow-hidden">
        <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full border border-vermilion/20 opacity-40 animate-orbit-slow" aria-hidden="true" />
        <div className="pointer-events-none absolute -left-6 bottom-0 h-24 w-24 rounded-full border border-gold/20 opacity-40 animate-orbit-slow-reverse" aria-hidden="true" />
        <h1 className="mb-4 font-display text-4xl text-ink-800 dark:text-ink-100 md:text-5xl">
          生成你的命运数字孪生
        </h1>
        <p className="mx-auto max-w-2xl text-ink-600 dark:text-ink-300">
          输入出生时间、地点与性别，命镜将自动推导出八字，并为你构建可交互、可推演、可对比的个人命运模型。
        </p>
      </section>

      <section className="panel mesh-bg p-6 md:p-8">
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="form-group">
            <label className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300">
              历法
            </label>
            <div
              className="calendar-toggle inline-flex rounded-xl border border-ink-300/40 bg-ink-100/50 p-1 dark:border-ink-500/40 dark:bg-ink-800/50"
              data-active={calendarType}
            >
              {[
                { value: "solar", label: "公历" },
                { value: "lunar", label: "农历" },
              ].map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setCalendarType(t.value as "solar" | "lunar")}
                  className={`relative z-10 rounded-lg px-4 py-1.5 text-sm transition ${
                    calendarType === t.value
                      ? "text-ink-800 dark:text-ink-100"
                      : "text-ink-500 dark:text-ink-400"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300">
              {calendarType === "lunar" ? "农历出生日期" : "公历出生日期"}
            </label>
            <div className="flex gap-3">
              <WheelPicker
                options={YEAR_OPTIONS}
                value={birthYear}
                onChange={setBirthYear}
                label="年"
                disabled={useManualBazi}
              />
              <WheelPicker
                options={MONTH_OPTIONS}
                value={birthMonth}
                onChange={setBirthMonth}
                label="月"
                disabled={useManualBazi}
              />
              <WheelPicker
                options={DAY_OPTIONS}
                value={birthDay}
                onChange={setBirthDay}
                label="日"
                disabled={useManualBazi}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300">
              出生时间
            </label>
            <div className="flex gap-3 md:w-2/3">
              <WheelPicker
                options={HOUR_OPTIONS}
                value={timeUnknown ? "12" : birthHour}
                onChange={setBirthHour}
                label="时"
                disabled={timeUnknown}
              />
              <WheelPicker
                options={MINUTE_OPTIONS}
                value={timeUnknown ? "00" : birthMinute}
                onChange={setBirthMinute}
                label="分"
                disabled={timeUnknown}
              />
            </div>
            <label className="mt-2 inline-flex cursor-pointer items-center gap-2 text-sm text-ink-500 dark:text-ink-400">
              <input
                type="checkbox"
                checked={timeUnknown}
                onChange={(e) => {
                  const checked = e.target.checked;
                  setTimeUnknown(checked);
                  if (checked) {
                    setSavedTime({ hour: birthHour, minute: birthMinute });
                    setBirthHour("12");
                    setBirthMinute("00");
                  } else {
                    setBirthHour(savedTime.hour);
                    setBirthMinute(savedTime.minute);
                  }
                }}
                className="h-4 w-4 accent-vermilion"
              />
              时辰不详（默认用正午 12:00 生成时柱，仅供粗略参考）
            </label>
          </div>

          <div className="form-group">
            <label className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300">
              性别
            </label>
            <div className="inline-flex gap-2 rounded-2xl border border-ink-300/40 bg-ink-100/50 p-1.5 dark:border-ink-500/40 dark:bg-ink-800/50">
              {GENDER_OPTIONS.map((g) => {
                const selected = gender === g.value;
                return (
                  <button
                    key={g.value}
                    type="button"
                    onClick={() => setGender(g.value)}
                    className={`relative rounded-xl px-5 py-2 text-sm font-medium transition-all ${
                      selected
                        ? "bg-white text-ink-800 shadow-md dark:bg-ink-700 dark:text-ink-100"
                        : "text-ink-500 hover:bg-ink-200/60 dark:text-ink-400 dark:hover:bg-ink-700/60"
                    }`}
                  >
                    {g.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="form-group space-y-3 rounded-2xl border border-ink-300/20 bg-ink-100/30 p-4 dark:border-ink-500/20 dark:bg-ink-800/30">
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm font-medium text-ink-600 dark:text-ink-300">
                <MapPin className="h-4 w-4 floating-icon" />
                出生地点
              </label>
              <button
                type="button"
                onClick={handleLocate}
                disabled={locating}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-ink-500 transition hover:bg-ink-200 disabled:opacity-50 dark:text-ink-400 dark:hover:bg-ink-700"
                title="使用当前位置"
              >
                <LocateFixed className="h-3 w-3" />
                {locating ? "定位中" : "自动定位"}
              </button>
            </div>

            {locateError && (
              <p className="text-xs text-vermilion">{locateError}</p>
            )}

            <div className="grid gap-3 md:grid-cols-2">
              <input
                type="text"
                value={locationName}
                onChange={(e) => setLocationName(e.target.value)}
                placeholder="城市 / 地区，例如：北京"
                className="input input-glow"
              />
              <div className="relative">
                <select
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  className="input input-glow appearance-none pr-10"
                >
                  {TIMEZONE_OPTIONS.map((tz) => (
                    <option key={tz.value} value={tz.value}>
                      {tz.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400 dark:text-ink-500" />
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <input
                type="number"
                step="0.0001"
                value={longitude}
                onChange={(e) => setLongitude(Number(e.target.value))}
                placeholder="经度"
                className="input input-glow"
              />
              <input
                type="number"
                step="0.0001"
                value={latitude}
                onChange={(e) => setLatitude(Number(e.target.value))}
                placeholder="纬度"
                className="input input-glow"
              />
            </div>
          </div>

          <div className="form-group flex items-center gap-3">
            <button
              type="button"
              onClick={() => setUseManualBazi((v) => !v)}
              className="inline-flex items-center gap-1 text-sm text-ink-500 transition hover:text-ink-700 hover:translate-x-0.5 dark:text-ink-400 dark:hover:text-ink-200"
            >
              <Settings2 className="h-4 w-4" />
              {useManualBazi ? "使用出生时间推导" : "手动输入八字"}
            </button>
          </div>

          {useManualBazi && (
            <div className="form-group">
              <label
                htmlFor="manualBazi"
                className="mb-2 block text-sm font-medium text-ink-600 dark:text-ink-300"
              >
                四柱八字
              </label>
              <input
                id="manualBazi"
                type="text"
                value={manualBazi}
                onChange={(e) => setManualBazi(e.target.value)}
                placeholder="例如：甲子 乙丑 丙寅 丁卯"
                className="input input-glow"
                required={useManualBazi}
              />
            </div>
          )}

          {deriveError && (
            <div className="form-group rounded-xl bg-vermilion/10 px-4 py-3 text-sm text-vermilion dark:bg-vermilion/20">
              {deriveError}
            </div>
          )}

          {!useManualBazi && (
            <div className="form-group rounded-xl border border-ink-300/20 bg-ink-100/30 p-4 dark:border-ink-500/20 dark:bg-ink-800/30">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium text-ink-600 dark:text-ink-300">
                  四柱预览
                </span>
                <span className="text-xs text-ink-400 dark:text-ink-500">
                  {calendarType === "lunar" ? "农历" : "公历"} {buildDate(birthYear, birthMonth, birthDay)} {buildTime(birthHour, birthMinute)}
                </span>
              </div>
              {previewLoading ? (
                <div className="flex items-center gap-2 text-sm text-ink-500 dark:text-ink-400">
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-ink-300 border-t-vermilion" />
                  正在推导……
                </div>
              ) : previewError ? (
                <p className="text-sm text-vermilion">{previewError}</p>
              ) : previewBazi ? (
                <div className="flex flex-wrap gap-2">
                  {previewBazi.split(" ").map((pillar, idx) => (
                    <span
                      key={idx}
                      className="rounded-lg bg-white/80 px-3 py-1 text-base font-semibold text-ink-800 shadow-sm dark:bg-ink-700/80 dark:text-ink-100"
                    >
                      {pillar}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-ink-500 dark:text-ink-400">
                  请选择完整的出生日期和时间
                </p>
              )}
            </div>
          )}

          <div className="form-group flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={deriving}
              className="btn-primary btn-shimmer disabled:cursor-not-allowed"
            >
              {deriving ? (
                <>
                  <span className="relative mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  <span className="relative">推导八字中</span>
                </>
              ) : (
                <>
                  <Sparkles className="relative mr-2 h-4 w-4" />
                  <span className="relative">生成命盘</span>
                </>
              )}
            </button>
            {deriving && (
              <span className="text-sm text-ink-500 animate-pulse dark:text-ink-400">
                正在校准节气与历法……
              </span>
            )}
            {parsed && (
              <button
                type="button"
                onClick={handleReplay}
                className="inline-flex items-center justify-center rounded-xl border border-ink-300/40 bg-ink-100/50 px-5 py-3 text-ink-700 transition hover:bg-ink-200 dark:border-ink-500/40 dark:bg-ink-800/50 dark:text-ink-200 dark:hover:bg-ink-700"
              >
                <RefreshCw className="mr-2 h-4 w-4" />
                重启动效
              </button>
            )}
          </div>
        </form>
      </section>

      {parsed && chart && (
        <>
          <section className="panel mesh-bg relative p-6 md:p-8 animate-fade-up">
            <div className="pointer-events-none absolute inset-0 -z-10 animate-pulse-ring rounded-3xl bg-vermilion/5 dark:bg-vermilion/10" aria-hidden="true" />
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-ink-700 dark:text-ink-200">
                命盘
                <span className="ml-2 text-sm font-normal text-ink-500 dark:text-ink-400">
                  {chart.bazi}
                </span>
              </h2>
              <div className="flex gap-3">
                <Link
                  to="/chart"
                  className="inline-flex items-center text-sm font-medium text-vermilion hover:underline"
                >
                  八字分析
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Link>
                <Link
                  to="/council"
                  className="inline-flex items-center text-sm font-medium text-vermilion hover:underline"
                >
                  命理议会
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Link>
              </div>
            </div>
            <PillarsChart
              key={animateKey}
              bazi={chart.bazi}
              animate={animateKey > 0}
            />
          </section>

          <FiveElementBars bazi={chart.bazi} animate={animateKey > 0} />

          <section>
            <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
              今日运势天气
            </h2>
            <DailyWeather bazi={chart.bazi} animate={animateKey > 0} />
          </section>
        </>
      )}

      {chart && !parsed && (
        <section className="panel border-l-4 border-l-vermilion p-6 animate-fade-up">
          <h2 className="mb-2 text-lg font-semibold text-ink-700 dark:text-ink-200">
            八字格式不正确
          </h2>
          <p className="text-ink-600 dark:text-ink-400">
            请检查出生日期/时间，或手动输入正确的四柱八字，例如：甲子 乙丑 丙寅 丁卯
          </p>
        </section>
      )}

      <style>{`
        @keyframes mesh {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }

        @keyframes fade-up {
          0% { opacity: 0; transform: translateY(16px); }
          100% { opacity: 1; transform: translateY(0); }
        }

        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }

        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-6px); }
        }

        @keyframes orbit-slow {
          0% { transform: rotate(0deg) translateX(8px) rotate(0deg); }
          100% { transform: rotate(360deg) translateX(8px) rotate(-360deg); }
        }

        @keyframes orbit-slow-reverse {
          0% { transform: rotate(0deg) translateX(-8px) rotate(0deg); }
          100% { transform: rotate(-360deg) translateX(-8px) rotate(360deg); }
        }

        @keyframes pulse-ring {
          0% { transform: scale(0.8); opacity: 0.5; }
          50% { transform: scale(1.1); opacity: 1; }
          100% { transform: scale(0.8); opacity: 0.5; }
        }

        .mesh-bg {
          background: linear-gradient(
            -45deg,
            rgba(201, 162, 39, 0.06),
            rgba(201, 54, 29, 0.06),
            rgba(201, 162, 39, 0.06),
            rgba(52, 73, 94, 0.04)
          );
          background-size: 400% 400%;
          animation: mesh 12s ease infinite;
        }

        .animate-fade-up {
          animation: fade-up 0.5s ease-out forwards;
        }

        .form-group {
          opacity: 0;
          animation: fade-up 0.5s ease-out forwards;
        }

        .form-group:nth-child(1) { animation-delay: 50ms; }
        .form-group:nth-child(2) { animation-delay: 100ms; }
        .form-group:nth-child(3) { animation-delay: 150ms; }
        .form-group:nth-child(4) { animation-delay: 200ms; }
        .form-group:nth-child(5) { animation-delay: 250ms; }
        .form-group:nth-child(6) { animation-delay: 300ms; }
        .form-group:nth-child(7) { animation-delay: 350ms; }

        .input-glow {
          transition: all 0.25s ease;
        }

        .input-glow:focus,
        .input-glow:focus-within {
          box-shadow: 0 0 0 3px rgba(201, 54, 29, 0.15), 0 4px 12px rgba(0, 0, 0, 0.08);
          transform: translateY(-1px);
        }

        .btn-shimmer {
          position: relative;
          overflow: hidden;
          transition: all 0.25s ease;
        }

        .btn-shimmer::after {
          content: "";
          position: absolute;
          inset: 0;
          background: linear-gradient(
            90deg,
            transparent,
            rgba(255, 255, 255, 0.25),
            transparent
          );
          background-size: 200% 100%;
          animation: shimmer 2.5s infinite;
        }

        .btn-shimmer:hover {
          transform: translateY(-2px);
          box-shadow: 0 8px 20px rgba(201, 54, 29, 0.3);
        }

        .btn-shimmer:active {
          transform: translateY(0);
        }

        .calendar-toggle {
          position: relative;
        }

        .calendar-toggle::before {
          content: "";
          position: absolute;
          top: 4px;
          left: 4px;
          width: calc(50% - 4px);
          height: calc(100% - 8px);
          background: white;
          border-radius: 0.5rem;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
          transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        .dark .calendar-toggle::before {
          background: rgb(55, 65, 81);
        }

        .calendar-toggle[data-active="lunar"]::before {
          transform: translateX(100%);
        }

        .floating-icon {
          animation: float 3s ease-in-out infinite;
        }

        .animate-orbit-slow {
          animation: orbit-slow 12s linear infinite;
        }

        .animate-orbit-slow-reverse {
          animation: orbit-slow-reverse 15s linear infinite;
        }

        .animate-pulse-ring {
          animation: pulse-ring 2s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}
