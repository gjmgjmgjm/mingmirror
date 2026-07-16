import { Link, useLocation } from "react-router-dom";
import ChartBasic from "./ChartBasic";
import YearlyChart from "./YearlyChart";
import ReadingReport from "./ReadingReport";

const tabs = [
  { path: "/chart", label: "基础分析" },
  { path: "/chart/report", label: "解读报告" },
  { path: "/chart/yearly", label: "流年精排" },
];

const SUB_PATHS = ["/chart/yearly", "/chart/report"];

export default function Chart() {
  const location = useLocation();
  const active = SUB_PATHS.includes(location.pathname)
    ? location.pathname
    : "/chart";

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 inline-flex rounded-2xl border border-ink-300/40 bg-ink-100/50 p-1.5 dark:border-ink-500/40 dark:bg-ink-800/50">
        {tabs.map((tab) => {
          const selected = active === tab.path;
          return (
            <Link
              key={tab.path}
              to={tab.path}
              className={`rounded-xl px-5 py-2 text-sm font-medium transition-all ${
                selected
                  ? "bg-white text-ink-800 shadow-md dark:bg-ink-700 dark:text-ink-100"
                  : "text-ink-500 hover:bg-ink-200/60 dark:text-ink-400 dark:hover:bg-ink-700/60"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>

      {active === "/chart/yearly" ? (
        <YearlyChart />
      ) : active === "/chart/report" ? (
        <ReadingReport />
      ) : (
        <ChartBasic />
      )}
    </div>
  );
}
