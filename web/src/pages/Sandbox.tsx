import { FlaskConical } from "lucide-react";

export default function Sandbox() {
  return (
    <div className="panel mx-auto max-w-3xl p-8 text-center md:p-16">
      <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-vermilion/10 text-vermilion dark:bg-vermilion/20">
        <FlaskConical className="h-8 w-8" />
      </div>
      <h1 className="mb-4 font-display text-4xl text-ink-800 dark:text-ink-100">
        命运沙盒
      </h1>
      <p className="mx-auto max-w-xl text-ink-600 dark:text-ink-300">
        推演不同选择下的命运分支，对比关键决策的潜在走向。沙盒引擎正在搭建中，敬请期待。
      </p>
    </div>
  );
}
