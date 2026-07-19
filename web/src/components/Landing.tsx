import { useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Sparkles,
  ArrowDown,
  ShieldCheck,
  ScrollText,
  Users,
  CalendarDays,
  Target,
  FlaskConical,
  BookOpen,
  Compass,
  Library,
  Download,
} from "lucide-react";
import { SectionCard, SealStamp, CloudDivider, InfoCard, DomainCard } from "./ui";
import { track } from "../lib/analytics";
import { PLAN_COPY } from "../lib/entitlements";
import type { DemoChart } from "../api/client";

interface LandingProps {
  demos: DemoChart[];
  onLoadDemo: (d: DemoChart) => void;
  /** 主 CTA:滚到排盘表单 / 聚焦输入 */
  onStart: () => void;
}

// 结构层 scoreboard — 仅 A 层 det（见 docs/capability-boundary.md）
// 禁止把事件/年份 MCQ 写成结构准确率。
const ACCURACY = [
  { label: "排盘（iztro gold）", value: "100%" },
  { label: "用神（穷通宝鉴）", value: "100%" },
  { label: "六亲强弱 det", value: "100%" },
  { label: "格局注入", value: "100%" },
];

const PILLARS = [
  { title: "结构层确定性", text: "排盘、用神、六亲、神煞由程序严格计算,可复核、可验证,而非模型拍脑袋。" },
  { title: "可解释命书", text: "每条断语标注 ✅ 确定性 / ◐ AI 推理,你分得清哪些是算出来的、哪些是推出来的。" },
  { title: "多体系同参", text: "八字 / 紫微 / 七政三套命理结构层,加命理议会多模型圆桌辩论。" },
  { title: "事件校准进化", text: "用你真实的婚动、入职、搬迁等事件校准,命盘越用越贴合实际轨迹。" },
];

const STEPS = [
  { n: "一", title: "输入生辰", text: "出生公历/农历时间 + 地点 + 性别,程序推导四柱八字。" },
  { n: "二", title: "确定性结构层", text: "排盘、用神、六亲、神煞严格查表,可解释报告骨架生成。" },
  { n: "三", title: "读命书 · 推流年", text: "在线免费阅读完整命书,叠加大运流年与择日,导出可打印 PDF。" },
];

const FEATURES = [
  { icon: ScrollText, name: "八字分析", desc: "四柱结构层 + 取象 + 四领域" },
  { icon: Sparkles, name: "紫微斗数", desc: "主星 / 四化 / 大限" },
  { icon: Compass, name: "七政四余", desc: "星盘 / 庙旺 / 流年" },
  { icon: Users, name: "命理议会", desc: "多模型辩论 + critic 裁决" },
  { icon: FlaskConical, name: "命运沙盒", desc: "合婚 / 对比 / 推演" },
  { icon: CalendarDays, name: "择日引擎", desc: "用神 + 冲合 + 神煞" },
  { icon: BookOpen, name: "命运剧本", desc: "时间序列推演" },
  { icon: Target, name: "事件校准", desc: "真事写回权重" },
  { icon: Library, name: "案例库", desc: "真实命主结构层" },
];

export default function Landing({ demos, onLoadDemo, onStart }: LandingProps) {
  useEffect(() => {
    track("landing_view");
  }, []);

  const cta = (position: string) => {
    track("landing_cta_click", { position });
    onStart();
  };

  return (
    <div className="space-y-8">
      {/* 1 · Hero */}
      <section className="relative overflow-hidden rounded-2xl border border-vermilion/10 bg-gradient-to-br from-white/90 via-ink-100/90 to-white/90 px-6 py-10 text-center shadow-lg backdrop-blur-sm dark:border-vermilion/20 dark:from-ink-800/90 dark:via-ink-900/90 dark:to-ink-800/90 md:px-12 md:py-14">
        <div className="pointer-events-none absolute -right-6 -top-6 h-28 w-28 rounded-full border border-vermilion/20 opacity-50 animate-orbit-slow" aria-hidden="true" />
        <div className="pointer-events-none absolute -left-4 bottom-0 h-20 w-20 rounded-full border border-gold/20 opacity-50 animate-orbit-slow-reverse" aria-hidden="true" />
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-full w-full -translate-x-1/2 -translate-y-1/2 bg-[radial-gradient(circle,rgba(201,162,39,0.10),transparent_60%)]" aria-hidden="true" />

        <div className="relative mb-3 flex items-center justify-center gap-3">
          <SealStamp size="md" variant="vermilion">命镜</SealStamp>
        </div>
        <h1 className="relative font-display text-3xl text-ink-800 dark:text-ink-100 md:text-4xl">
          生成你的命运数字孪生
        </h1>
        <p className="relative mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-ink-600 dark:text-ink-300 md:text-base">
          不是传统算命,是<b className="text-vermilion">可计算、可验证、可交互</b>的个人命运模型 ——
          结构层优先,排盘可复核,流年可导出,AI 为可选增强。
        </p>

        <div className="relative mt-6 flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => cta("hero_primary")}
            className="btn-primary btn-shimmer inline-flex items-center gap-2"
          >
            <Sparkles className="h-4 w-4" />
            免费排盘
          </button>
          {demos.length > 0 && (
            <button
              type="button"
              onClick={() => {
                track("landing_cta_click", { position: "hero_demo" });
                onLoadDemo(demos[0]);
              }}
              className="btn-secondary inline-flex items-center gap-2"
            >
              看一份样例命书
              <ArrowDown className="h-4 w-4" />
            </button>
          )}
        </div>

        <div className="relative mt-5 flex flex-wrap items-center justify-center gap-2 text-[11px]">
          {["排盘 100%", "用神 90%", "结构层可复核", "免登录"].map((t) => (
            <span key={t} className="rounded-full bg-jade/15 px-2.5 py-0.5 text-jade">
              <ShieldCheck className="mr-1 inline h-3 w-3" />
              {t}
            </span>
          ))}
        </div>
      </section>

      {/* 2 · 差异化 / 价值主张 */}
      <SectionCard
        borderLeft="vermilion"
        title={<>为什么是命镜,而不是又一个算命网站</>}
        subtitle="护城河不在「算得准」,在「算的东西能拿出来给人看依据」"
        delay={60}
      >
        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {ACCURACY.map((a, i) => (
            <InfoCard key={a.label} label={a.label} value={a.value} delay={i * 70} />
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {PILLARS.map((p, i) => (
            <DomainCard key={p.title} title={p.title} text={p.text} delay={i * 70} />
          ))}
        </div>
      </SectionCard>

      <CloudDivider variant="gold" />

      {/* 3 · 免费样例命书(THE HOOK) */}
      <SectionCard
        borderLeft="gold"
        title={<>免费样例命书 · 一键查看完整命盘</>}
        subtitle="无需注册,点开即看八字 / 紫微 / 七政 / 流年 / 命书全包"
        delay={80}
      >
        {demos.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {demos.map((d, i) => (
              <button
                key={d.id}
                type="button"
                onClick={() => {
                  track("landing_cta_click", { position: "demo_card", demo_id: d.id });
                  onLoadDemo(d);
                }}
                className="group rounded-xl border border-ink-300/30 bg-white/60 p-4 text-left transition hover:-translate-y-0.5 hover:border-vermilion/40 hover:shadow-md dark:border-ink-500/30 dark:bg-ink-800/60"
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <div className="mb-1 text-sm font-semibold text-ink-800 group-hover:text-vermilion dark:text-ink-100">
                  {d.label}
                </div>
                <div className="font-mono text-xs text-ink-500 dark:text-ink-400">{d.bazi}</div>
                <div className="mt-2 text-[11px] text-gold">点开看完整命书 →</div>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-500">样例加载中…</p>
        )}
      </SectionCard>

      <CloudDivider variant="ink" />

      {/* 4 · 如何工作 */}
      <SectionCard borderLeft="jade" title={<>三步生成你的命书</>} delay={80}>
        <div className="grid gap-4 sm:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.n} className="rounded-xl bg-ink-100/40 p-4 dark:bg-ink-800/40">
              <div className="mb-1 flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-jade/15 font-display text-sm text-jade">
                  {s.n}
                </span>
                <span className="font-semibold text-ink-800 dark:text-ink-100">{s.title}</span>
              </div>
              <p className="text-sm leading-relaxed text-ink-500 dark:text-ink-400">{s.text}</p>
            </div>
          ))}
        </div>
      </SectionCard>

      {/* 5 · 能力清单 */}
      <SectionCard title={<>能力清单 · 九大命理工具</>} delay={80}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.name} className="flex items-start gap-2.5 rounded-lg bg-white/50 p-3 dark:bg-ink-800/50">
              <f.icon className="mt-0.5 h-4 w-4 shrink-0 text-vermilion" />
              <div>
                <div className="text-sm font-medium text-ink-800 dark:text-ink-100">{f.name}</div>
                <div className="text-[11px] text-ink-500 dark:text-ink-400">{f.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      {/* 6 · 定价预告 */}
      <SectionCard
        borderLeft="gold"
        title={<>免费读 · 付费导出</>}
        subtitle="在线阅读命书全程免费;打印 PDF 命书交付包按需付费"
        delay={80}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-jade/30 bg-jade/5 p-4">
            <div className="mb-1 flex items-center gap-2 text-jade">
              <span className="text-lg font-semibold">{PLAN_COPY.free.name}</span>
              <span className="text-xs">¥0</span>
            </div>
            <ul className="space-y-1 text-xs text-ink-600 dark:text-ink-300">
              {PLAN_COPY.free.features.map((f) => (
                <li key={f}>· {f}</li>
              ))}
              <li className="text-jade">· 命书在线阅读 + Markdown 导出</li>
            </ul>
          </div>
          <div className="rounded-xl border border-gold/40 bg-gold/5 p-4">
            <div className="mb-1 flex items-center gap-2 text-gold">
              <span className="text-lg font-semibold">{PLAN_COPY.pro.name}</span>
              <span className="text-xs">¥19 / 单次 · ¥99 / 30 天</span>
            </div>
            <ul className="space-y-1 text-xs text-ink-600 dark:text-ink-300">
              {PLAN_COPY.pro.features.map((f) => (
                <li key={f}>· {f}</li>
              ))}
            </ul>
            <Link
              to="/pricing"
              onClick={() => track("landing_cta_click", { position: "pricing_teaser" })}
              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-vermilion hover:underline"
            >
              <Download className="h-3 w-3" />
              查看套餐 / 导出命书 PDF
            </Link>
          </div>
        </div>
      </SectionCard>

      {/* 7 · 终极 CTA */}
      <section className="rounded-2xl border border-vermilion/20 bg-gradient-to-br from-vermilion/5 to-gold/5 p-8 text-center">
        <h2 className="font-display text-2xl text-ink-800 dark:text-ink-100 md:text-3xl">
          你的命盘,免费排起
        </h2>
        <p className="mx-auto mt-2 max-w-xl text-sm text-ink-500 dark:text-ink-400">
          输入出生信息,30 秒生成可解释命书 + 今日运势 + 流年主线。
        </p>
        <button
          type="button"
          onClick={() => cta("final")}
          className="btn-primary btn-shimmer mt-5 inline-flex items-center gap-2"
        >
          <Sparkles className="h-4 w-4" />
          免费排盘
        </button>
        <p className="mt-4 text-[11px] leading-relaxed text-ink-400">
          内容仅供参考,不构成医疗 / 法律 / 投资建议。
        </p>
      </section>
    </div>
  );
}
