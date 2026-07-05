import { CalendarDays } from "lucide-react";

export default function Calendar() {
  return (
    <div className="panel mx-auto max-w-3xl p-8 text-center md:p-16">
      <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-gold/10 text-gold dark:bg-gold/20">
        <CalendarDays className="h-8 w-8" />
      </div>
      <h1 className="mb-4 font-display text-4xl text-ink-800 dark:text-ink-100">
        择日引擎
      </h1>
      <p className="mx-auto max-w-xl text-ink-600 dark:text-ink-300">
        基于个人命盘与黄历数据，智能推荐结婚、开业、出行等良辰吉日。引擎正在接入历法数据源。
      </p>
    </div>
  );
}
