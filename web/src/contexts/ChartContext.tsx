import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { createChart as apiCreateChart } from "../api/client";

export interface LocationInfo {
  name?: string;
  longitude: number;
  latitude: number;
  timezone: string;
}

export interface ChartInfo {
  /** Server UUID when persisted; optional for offline/local-only. */
  id?: string;
  bazi: string;
  gender: string;
  birthDate: string;
  birthTime: string;
  calendarType?: "solar" | "lunar";
  location?: LocationInfo;
  label?: string;
}

interface ChartContextValue {
  chart: ChartInfo | null;
  setChart: (chart: ChartInfo | null) => void;
  /** Prefer UUID for events/calibration; fall back to bazi (legacy). */
  chartScopeId: string | null;
  persistChart: (chart: ChartInfo) => Promise<ChartInfo>;
}

const STORAGE_KEY = "mingmirror_active_chart_v1";

const ChartContext = createContext<ChartContextValue | null>(null);

function loadStored(): ChartInfo | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as ChartInfo;
    if (!data?.bazi) return null;
    return data;
  } catch {
    return null;
  }
}

function saveStored(chart: ChartInfo | null) {
  try {
    if (!chart) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(chart));
    }
  } catch {
    // ignore quota / private mode
  }
}

export function ChartProvider({ children }: { children: ReactNode }) {
  const [chart, setChartState] = useState<ChartInfo | null>(() => loadStored());

  const setChart = useCallback((next: ChartInfo | null) => {
    setChartState(next);
    saveStored(next);
  }, []);

  const persistChart = useCallback(async (input: ChartInfo): Promise<ChartInfo> => {
    try {
      const saved = await apiCreateChart({
        bazi: input.bazi,
        gender: input.gender || "male",
        birth_date: input.birthDate || "",
        birth_time: input.birthTime || "",
        calendar_type: input.calendarType || "solar",
        location: input.location
          ? {
              longitude: input.location.longitude,
              latitude: input.location.latitude,
              timezone: input.location.timezone,
              name: input.location.name,
            }
          : undefined,
        label: input.label || input.bazi,
        reuse_existing: true,
      });
      const merged: ChartInfo = {
        ...input,
        id: saved.id,
        bazi: saved.bazi,
        gender: saved.gender,
        birthDate: saved.birth_date || input.birthDate,
        birthTime: saved.birth_time || input.birthTime,
        calendarType: (saved.calendar_type as "solar" | "lunar") || input.calendarType,
        label: saved.label || input.label,
      };
      setChart(merged);
      return merged;
    } catch {
      // Offline / server down: keep local-only chart
      setChart(input);
      return input;
    }
  }, [setChart]);

  // Re-hydrate once on mount (already in useState init); sync tab changes
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) {
        setChartState(loadStored());
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const chartScopeId = chart?.id || chart?.bazi || null;

  return (
    <ChartContext.Provider
      value={{ chart, setChart, chartScopeId, persistChart }}
    >
      {children}
    </ChartContext.Provider>
  );
}

// oxlint-disable-next-line react/only-export-components
export function useChart() {
  const ctx = useContext(ChartContext);
  if (!ctx) throw new Error("useChart must be used within ChartProvider");
  return ctx;
}
