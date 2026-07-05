import { useEffect, useState } from "react";

interface CouncilLoaderProps {
  systems: string[];
}

const SYSTEM_LABELS: Record<string, string> = {
  bazi: "八字",
  ziwei: "紫微",
  qizheng: "七政",
};

const MESSAGES = [
  "正在起盘……",
  "各体系交换意见中……",
  "校验五行生克……",
  "形成议会共识……",
];

export default function CouncilLoader({ systems }: CouncilLoaderProps) {
  const [messageIndex, setMessageIndex] = useState(0);
  const labels = systems.map((id) => SYSTEM_LABELS[id] ?? id);

  useEffect(() => {
    const interval = setInterval(() => {
      setMessageIndex((idx) => (idx + 1) % MESSAGES.length);
    }, 1800);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="panel p-8 md:p-10">
      <div className="relative mx-auto flex h-48 w-full max-w-md flex-col items-center justify-center">
        {/* Orbit ring */}
        <div
          className="absolute h-32 w-32 rounded-full border border-dashed border-ink-300/40 dark:border-ink-500/40"
          aria-hidden="true"
        />
        <div
          className="absolute h-40 w-40 rounded-full border border-ink-200/30 dark:border-ink-600/30"
          aria-hidden="true"
        />

        {/* Orbiting bodies for selected systems */}
        {labels.map((label, index) => (
          <div
            key={label}
            className="absolute flex h-9 w-9 items-center justify-center rounded-full bg-ink-100 text-xs font-medium text-ink-700 shadow-sm dark:bg-ink-800 dark:text-ink-200"
            style={{
              animation: `orbit 2.4s linear infinite`,
              animationDelay: `${index * (2.4 / labels.length)}s`,
            }}
          >
            {label}
          </div>
        ))}

        {/* Center hub */}
        <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-vermilion/10 dark:bg-vermilion/20">
          <div className="h-10 w-10 animate-hub-pulse rounded-full bg-vermilion/20 dark:bg-vermilion/30" />
          <span className="absolute text-lg font-semibold text-vermilion">议</span>
        </div>
      </div>

      <div className="mt-6 space-y-3 text-center">
        <p className="h-5 text-sm font-medium text-ink-600 dark:text-ink-300">
          {labels.join(" · ")} 议会审议中
        </p>
        <p className="h-5 text-xs text-ink-500 transition-opacity duration-300 dark:text-ink-400">
          {MESSAGES[messageIndex]}
        </p>
      </div>

      <style>{`
        @keyframes orbit {
          0% {
            transform: rotate(0deg) translateX(64px) rotate(0deg);
          }
          100% {
            transform: rotate(360deg) translateX(64px) rotate(-360deg);
          }
        }

        @keyframes hub-pulse {
          0%, 100% {
            transform: scale(0.8);
            opacity: 0.5;
          }
          50% {
            transform: scale(1.2);
            opacity: 1;
          }
        }

        .animate-hub-pulse {
          animation: hub-pulse 2s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}
