import { Sparkles, Heart, Briefcase, Plane, Home } from "lucide-react";
import { SectionCard, PageHeader, CloudDivider } from "../components/ui";

const occasions = [
  { icon: Heart, label: "嫁娶", color: "text-vermilion" },
  { icon: Briefcase, label: "开业", color: "text-gold" },
  { icon: Plane, label: "出行", color: "text-jade" },
  { icon: Home, label: "入宅", color: "text-ink-600" },
];

const weekDays = ["日", "一", "二", "三", "四", "五", "六"];

export default function Calendar() {
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <PageHeader
        title="择日引擎"
        subtitle="基于个人命盘、黄历与二十八宿，智能推荐结婚、开业、出行等良辰吉日"
      />

      <CloudDivider variant="gold" />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {occasions.map((occasion) => {
          const Icon = occasion.icon;
          return (
            <div
              key={occasion.label}
              className="panel flex flex-col items-center gap-2 p-4 text-center transition hover:-translate-y-0.5"
            >
              <Icon className={`h-6 w-6 ${occasion.color}`} />
              <span className="font-medium text-ink-700 dark:text-ink-200">
                {occasion.label}
              </span>
            </div>
          );
        })}
      </div>

      <SectionCard title="黄历预览（示例）" icon={<Sparkles className="h-5 w-5 text-gold" />}>
        <div className="rounded-xl border border-ink-300/20 bg-ink-100/30 p-4 dark:border-ink-500/20 dark:bg-ink-800/30">
          <div className="mb-4 flex items-center justify-between">
            <span className="font-display text-2xl text-ink-800 dark:text-ink-100">
              2026 年 7 月
            </span>
            <span className="text-sm text-ink-500 dark:text-ink-400">
              丙午月
            </span>
          </div>

          <div className="grid grid-cols-7 gap-1 text-center text-sm font-medium text-ink-500 dark:text-ink-400">
            {weekDays.map((day) => (
              <div key={day} className="py-2">
                {day}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-1 text-center text-sm">
            {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => {
              const isAuspicious = [3, 8, 12, 18, 21, 26].includes(day);
              const isInauspicious = [5, 14, 19, 27].includes(day);
              return (
                <div
                  key={day}
                  className={`rounded-lg py-2 ${
                    isAuspicious
                      ? "bg-jade/10 text-jade dark:bg-jade/20"
                      : isInauspicious
                        ? "bg-vermilion/10 text-vermilion dark:bg-vermilion/20"
                        : "text-ink-600 hover:bg-ink-200/40 dark:text-ink-300 dark:hover:bg-ink-700/40"
                  }`}
                >
                  {day}
                </div>
              );
            })}
          </div>

          <div className="mt-4 flex flex-wrap gap-4 text-xs text-ink-500 dark:text-ink-400">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-jade" />
              宜
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-vermilion" />
              忌
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-ink-300 dark:bg-ink-600" />
              平
            </span>
          </div>
        </div>

        <div className="mt-4 rounded-xl bg-gold/10 p-4 text-sm text-gold dark:bg-gold/20">
          引擎正在接入完整历法数据源。上线后将结合你的命盘五行喜忌，给出个性化的择日建议。
        </div>
      </SectionCard>
    </div>
  );
}
