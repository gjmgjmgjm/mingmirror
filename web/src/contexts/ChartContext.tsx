import {
  createContext,
  useContext,
  useState,
  type ReactNode,
} from "react";

export interface LocationInfo {
  name?: string;
  longitude: number;
  latitude: number;
  timezone: string;
}

export interface ChartInfo {
  bazi: string;
  gender: string;
  birthDate: string;
  birthTime: string;
  calendarType?: "solar" | "lunar";
  location?: LocationInfo;
}

interface ChartContextValue {
  chart: ChartInfo | null;
  setChart: (chart: ChartInfo | null) => void;
}

const ChartContext = createContext<ChartContextValue | null>(null);

export function ChartProvider({ children }: { children: ReactNode }) {
  const [chart, setChart] = useState<ChartInfo | null>(null);

  return (
    <ChartContext.Provider value={{ chart, setChart }}>
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
