import { useEffect, useState } from "react";
import { countElements, parseBazi, ELEMENT_META } from "../lib/bazi";

interface FiveElementBarsProps {
  bazi: string;
  animate?: boolean;
}

export default function FiveElementBars({
  bazi,
  animate = false,
}: FiveElementBarsProps) {
  const parsed = parseBazi(bazi);
  if (!parsed) return null;

  const counts = countElements(parsed);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div className="panel p-5">
      <h3 className="mb-4 text-sm font-medium text-ink-600 dark:text-ink-300">
        五行能量分布
      </h3>
      <div className="space-y-3">
        {(
          Object.entries(counts) as Array<[keyof typeof counts, number]>
        ).map(([element, count], index) => (
          <ElementBar
            key={element}
            element={element}
            count={count}
            total={total}
            index={index}
            animate={animate}
          />
        ))}
      </div>
    </div>
  );
}

interface ElementBarProps {
  element: keyof typeof ELEMENT_META;
  count: number;
  total: number;
  index: number;
  animate: boolean;
}

function ElementBar({ element, count, total, index, animate }: ElementBarProps) {
  const meta = ELEMENT_META[element];
  const percentage = total > 0 ? (count / total) * 100 : 0;
  const [progress, setProgress] = useState(0);
  const [displayPercent, setDisplayPercent] = useState(0);

  useEffect(() => {
    if (!animate) {
      setProgress(percentage);
      setDisplayPercent(Math.round(percentage));
      return;
    }

    setProgress(0);
    setDisplayPercent(0);

    const delay = index * 100 + 100;
    const widthTimer = setTimeout(() => setProgress(percentage), delay);

    const duration = 800;
    const startTime = performance.now() + delay;
    let raf: number;

    const tick = (now: number) => {
      const elapsed = now - startTime;
      const ratio = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - ratio, 3);
      setDisplayPercent(Math.round(percentage * eased));
      if (ratio < 1) {
        raf = requestAnimationFrame(tick);
      }
    };

    raf = requestAnimationFrame(tick);

    return () => {
      clearTimeout(widthTimer);
      cancelAnimationFrame(raf);
    };
  }, [animate, percentage, index]);

  return (
    <div className="flex items-center gap-3">
      <span className={`w-6 text-center text-sm font-medium ${meta.color}`}>
        {meta.label}
      </span>
      <div className="flex-1 overflow-hidden rounded-full bg-ink-200/50 dark:bg-ink-700/50">
        <div
          className={`h-2 rounded-full transition-all duration-800 ease-out ${meta.bg.replace(
            "/10",
            ""
          )} ${meta.bg.replace("/20", "")}`}
          style={{ width: `${progress}%` }}
        />
      </div>
      <span className="w-10 text-right text-xs text-ink-500 dark:text-ink-400">
        {displayPercent}%
      </span>
    </div>
  );
}
