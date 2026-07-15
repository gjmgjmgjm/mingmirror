import { FlaskConical, GitBranch, Scale, TrendingUp, AlertTriangle } from "lucide-react";
import { SectionCard } from "../components/ui";

const scenarios = [
  {
    title: "职业分支",
    description: "对比换工作、创业、留守现状三种选择的运势走向。",
    icon: TrendingUp,
  },
  {
    title: "感情抉择",
    description: "推演不同时间点表白、分手、复合对后续感情的影响。",
    icon: Scale,
  },
  {
    title: "投资决策",
    description: "模拟不同年份、不同方向投资的财运起伏。",
    icon: GitBranch,
  },
];

export default function Sandbox() {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="panel mesh-bg p-8 text-center md:p-12">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-vermilion/10 text-vermilion dark:bg-vermilion/20">
          <FlaskConical className="h-8 w-8" />
        </div>
        <h1 className="mb-4 font-display text-4xl text-ink-800 dark:text-ink-100 md:text-5xl">
          命运沙盒
        </h1>
        <p className="mx-auto max-w-2xl text-ink-600 dark:text-ink-300">
          推演不同选择下的命运分支，对比关键决策的潜在走向，让每一次重大决定都有据可依。
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {scenarios.map((scenario) => {
          const Icon = scenario.icon;
          return (
            <SectionCard
              key={scenario.title}
              title={scenario.title}
              icon={<Icon className="h-5 w-5 text-vermilion" />}
              className="transition hover:-translate-y-0.5"
            >
              <p className="text-sm text-ink-600 dark:text-ink-300">
                {scenario.description}
              </p>
            </SectionCard>
          );
        })}
      </div>

      <SectionCard
        title="沙盒示例"
        icon={<GitBranch className="h-5 w-5 text-gold" />}
      >
        <div className="space-y-4">
          <div className="flex items-center gap-4 rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-vermilion/10 text-vermilion dark:bg-vermilion/20">
              A
            </div>
            <div className="flex-1">
              <p className="font-medium text-ink-700 dark:text-ink-200">
                2026 年跳槽到南方城市
              </p>
              <p className="text-sm text-ink-500 dark:text-ink-400">
                火旺之地，对喜火命主有利，事业运上升但人际关系波动。
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4 rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gold/10 text-gold dark:bg-gold/20">
              B
            </div>
            <div className="flex-1">
              <p className="font-medium text-ink-700 dark:text-ink-200">
                2026 年留守原岗位
              </p>
              <p className="text-sm text-ink-500 dark:text-ink-400">
                运势平稳，适合深耕积累，财运小增但突破有限。
              </p>
            </div>
          </div>
        </div>

        <div className="mt-4 flex items-start gap-3 rounded-xl bg-gold/10 p-4 text-sm text-gold dark:bg-gold/20">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            沙盒引擎正在搭建中。上线后支持输入多个决策变量，自动生成对比报告与推荐路径。
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
