import { useEffect, useState } from "react";
import { Sun, Cloud, CloudRain, CloudSun } from "lucide-react";
import { fetchDailyFortune, type DailyFortuneResponse } from "../api/client";
import { ELEMENT_META } from "../lib/bazi";

interface DailyWeatherProps {
  bazi: string;
  animate?: boolean;
}

const WEATHER_ICONS: Record<string, React.ReactNode> = {
  晴: <Sun className="h-8 w-8 text-gold" />,
  多云: <CloudSun className="h-8 w-8 text-gold" />,
  阴: <Cloud className="h-8 w-8 text-ink-500" />,
  雨: <CloudRain className="h-8 w-8 text-blue-500" />,
};

const PILLAR_LABELS: Record<string, string> = {
  year: "年",
  month: "月",
  day: "日",
};

export default function DailyWeather({ bazi, animate = false }: DailyWeatherProps) {
  const [data, setData] = useState<DailyFortuneResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchDailyFortune({ bazi });
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "获取运势失败");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [bazi]);

  if (loading) {
    return (
      <div className="panel p-6">
        <p className="text-center text-ink-500 dark:text-ink-400">
          正在推算今日运势……
        </p>
      </div>
    );
  }

  if (error || !data || data.error) {
    return (
      <div className="panel p-6">
        <p className="text-sm text-vermilion">
          {error || data?.error || "无法获取运势"}
        </p>
      </div>
    );
  }

  return (
    <div
      className={`panel p-6 ${animate ? "animate-weather-enter" : ""}`}
      style={animate ? { animationDelay: "0ms" } : undefined}
    >
      <div className="mb-5 flex items-center gap-4">
        <div
          className={`flex h-16 w-16 items-center justify-center rounded-full bg-ink-100 dark:bg-ink-800 ${
            animate ? "animate-weather-icon" : ""
          }`}
        >
          {WEATHER_ICONS[data.weather] ?? WEATHER_ICONS["阴"]}
        </div>
        <div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-ink-800 dark:text-ink-100">
              {data.weather}
            </span>
            <span className="text-sm text-ink-500 dark:text-ink-400">
              {data.weather_label}
            </span>
          </div>
          <p className="text-sm text-ink-500 dark:text-ink-400">{data.date}</p>
        </div>
      </div>

      <p className="mb-5 leading-relaxed text-ink-700 dark:text-ink-300">
        {data.description}
      </p>

      <div className="mb-5 grid grid-cols-3 gap-2 text-center text-xs">
        {Object.entries(data.today_pillars).map(([key, pillar], index) => (
          <div
            key={key}
            className={`rounded-xl bg-ink-100/60 py-2 dark:bg-ink-800/60 ${
              animate ? "animate-weather-pillar" : ""
            }`}
            style={animate ? { animationDelay: `${index * 80 + 120}ms` } : undefined}
          >
            <span className="block text-ink-500 dark:text-ink-400">
              {PILLAR_LABELS[key] ?? key}
            </span>
            <span className="font-medium text-ink-700 dark:text-ink-200">
              {pillar}
            </span>
          </div>
        ))}
      </div>

      <div className="mb-5 space-y-2">
        {(Object.entries(data.energy) as Array<[string, number]>).map(
          ([element, value], index) => (
            <EnergyBar
              key={element}
              element={element}
              value={value}
              index={index}
              animate={animate}
            />
          )
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div
          className={`${animate ? "animate-weather-list" : ""}`}
          style={animate ? { animationDelay: "400ms" } : undefined}
        >
          <h4 className="mb-2 text-sm font-medium text-jade">宜</h4>
          <ul className="space-y-1 text-sm text-ink-600 dark:text-ink-400">
            {data.dos.map((item, idx) => (
              <li key={idx}>• {item}</li>
            ))}
          </ul>
        </div>
        <div
          className={`${animate ? "animate-weather-list" : ""}`}
          style={animate ? { animationDelay: "520ms" } : undefined}
        >
          <h4 className="mb-2 text-sm font-medium text-vermilion">忌</h4>
          <ul className="space-y-1 text-sm text-ink-600 dark:text-ink-400">
            {data.avoids.map((item, idx) => (
              <li key={idx}>• {item}</li>
            ))}
          </ul>
        </div>
      </div>


    </div>
  );
}

interface EnergyBarProps {
  element: string;
  value: number;
  index: number;
  animate: boolean;
}

function EnergyBar({ element, value, index, animate }: EnergyBarProps) {
  const meta = ELEMENT_META[element as keyof typeof ELEMENT_META];
  const [width, setWidth] = useState(animate ? 0 : value);

  useEffect(() => {
    if (!animate) {
      setWidth(value);
      return;
    }
    setWidth(0);
    const timer = setTimeout(() => setWidth(value), index * 60 + 240);
    return () => clearTimeout(timer);
  }, [animate, value, index]);

  return (
    <div className="flex items-center gap-2">
      <span className={`w-4 text-sm ${meta.color}`}>{meta.label}</span>
      <div className="flex-1 overflow-hidden rounded-full bg-ink-200/50 dark:bg-ink-700/50">
        <div
          className={`h-1.5 rounded-full ${meta.bg
            .replace("/10", "")
            .replace("/20", "")}`}
          style={{ width: `${width}%`, transition: "width 0.8s ease-out" }}
        />
      </div>
      <span className="w-8 text-right text-xs text-ink-500 dark:text-ink-400">
        {value}%
      </span>
    </div>
  );
}
