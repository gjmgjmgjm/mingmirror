import { useEffect, useState } from "react";
import {
  parseBazi,
  ELEMENT_META,
  getHiddenStems,
  type ParsedBazi,
  type Element,
} from "../lib/bazi";

interface PillarsChartProps {
  bazi: string;
  showHiddenStems?: boolean;
  animate?: boolean;
}

const PILLAR_LABELS = ["年柱", "月柱", "日柱", "时柱"];

export default function PillarsChart({
  bazi,
  showHiddenStems = true,
  animate = false,
}: PillarsChartProps) {
  const parsed = parseBazi(bazi);
  if (!parsed) return null;

  const pillars = [parsed.year, parsed.month, parsed.day, parsed.hour];

  return (
    <div
      className="relative w-full"
      style={{ perspective: "1200px" }}
    >
      {/* Decorative compass ring */}
      {animate && (
        <div
          className="pointer-events-none absolute inset-0 -m-6 md:-m-10 animate-compass-enter"
          aria-hidden="true"
        >
          <svg
            className="animate-compass-spin h-full w-full text-ink-300/30 dark:text-ink-600/30"
            viewBox="0 0 200 200"
          >
            <circle
              cx="100"
              cy="100"
              r="96"
              fill="none"
              stroke="currentColor"
              strokeWidth="0.5"
              strokeDasharray="4 4"
            />
            <circle
              cx="100"
              cy="100"
              r="88"
              fill="none"
              stroke="currentColor"
              strokeWidth="0.5"
            />
            <g transform="translate(100, 100)">
              {[0, 90, 180, 270].map((deg) => (
                <line
                  key={deg}
                  x1="0"
                  y1="-88"
                  x2="0"
                  y2="-96"
                  stroke="currentColor"
                  strokeWidth="1"
                  transform={`rotate(${deg})`}
                />
              ))}
            </g>
          </svg>
        </div>
      )}

      <div
        className={`relative ${animate ? "animate-mandala-enter" : ""}`}
        style={{ transformStyle: "preserve-3d" }}
      >
        <div className="grid grid-cols-4 gap-3 md:gap-4">
          {pillars.map((pillar, index) => (
            <PillarCard
              key={index}
              pillar={pillar}
              label={PILLAR_LABELS[index]}
              isDay={index === 2}
              showHiddenStems={showHiddenStems}
              delay={animate ? index * 120 + 260 : 0}
              animate={animate}
            />
          ))}
        </div>

        <div className="mt-4 text-center text-xs text-ink-500 dark:text-ink-400">
          日主：<span className="font-medium text-gold">{parsed.dayMaster}</span>
        </div>
      </div>

      {animate && <style>{animationStyles}</style>}
    </div>
  );
}

interface PillarCardProps {
  pillar: ParsedBazi["year"];
  label: string;
  isDay: boolean;
  showHiddenStems: boolean;
  delay: number;
  animate: boolean;
}

function PillarCard({
  pillar,
  label,
  isDay,
  showHiddenStems,
  delay,
  animate,
}: PillarCardProps) {
  const [revealed, setRevealed] = useState(!animate);

  useEffect(() => {
    if (!animate) {
      setRevealed(true);
      return;
    }
    setRevealed(false);
    const timer = setTimeout(() => setRevealed(true), delay);
    return () => clearTimeout(timer);
  }, [animate, delay]);

  const stemMeta = ELEMENT_META[pillar.stemElement];
  const branchMeta = ELEMENT_META[pillar.branchElement];
  const hidden = getHiddenStems(pillar.branch);

  return (
    <div
      className={`relative flex flex-col items-center rounded-2xl border border-ink-300/20 bg-white/60 p-3 shadow-sm backdrop-blur-sm dark:border-ink-500/20 dark:bg-ink-800/60 md:p-4 ${
        isDay ? "ring-2 ring-gold/50" : ""
      } ${animate ? (revealed ? "animate-card-reveal" : "animate-card-hide") : ""}`}
      style={{
        transformStyle: "preserve-3d",
        backfaceVisibility: "hidden",
        animationDelay: `${delay}ms`,
      }}
    >
      {isDay && (
        <div className="absolute inset-0 -z-10 animate-day-glow rounded-2xl bg-gold/10 dark:bg-gold/10" />
      )}

      <span className="mb-2 text-xs font-medium tracking-widest text-ink-500 dark:text-ink-400">
        {label}
      </span>

      <div className="mb-3 flex w-full flex-col gap-2">
        <CharacterTile char={pillar.stem} meta={stemMeta} isDay={isDay} />
        <CharacterTile char={pillar.branch} meta={branchMeta} isDay={isDay} />
      </div>

      {showHiddenStems && hidden.length > 0 && (
        <div className="flex w-full flex-wrap justify-center gap-1 border-t border-ink-300/10 pt-2 dark:border-ink-500/10">
          {hidden.map((stem) => (
            <HiddenStem key={stem} stem={stem} />
          ))}
        </div>
      )}
    </div>
  );
}

function CharacterTile({
  char,
  meta,
  isDay,
}: {
  char: string;
  meta: (typeof ELEMENT_META)["wood"];
  isDay: boolean;
}) {
  return (
    <div
      className={`flex aspect-square w-full items-center justify-center rounded-xl text-3xl font-semibold md:text-4xl ${meta.bg} ${meta.color} ${
        isDay ? "shadow-inner" : ""
      }`}
    >
      {char}
    </div>
  );
}

function HiddenStem({ stem }: { stem: string }) {
  const element = inferElement(stem);
  const meta = element ? ELEMENT_META[element] : null;

  return (
    <span
      className={`rounded-md px-1.5 py-0.5 text-xs ${
        meta ? `${meta.bg} ${meta.color}` : "text-ink-500"
      }`}
      title={`藏干：${stem}`}
    >
      {stem}
    </span>
  );
}

function inferElement(char: string): Element | null {
  const wood = new Set(["甲", "乙", "寅", "卯"]);
  const fire = new Set(["丙", "丁", "巳", "午"]);
  const earth = new Set(["戊", "己", "辰", "戌", "丑", "未"]);
  const metal = new Set(["庚", "辛", "申", "酉"]);
  const water = new Set(["壬", "癸", "亥", "子"]);

  if (wood.has(char)) return "wood";
  if (fire.has(char)) return "fire";
  if (earth.has(char)) return "earth";
  if (metal.has(char)) return "metal";
  if (water.has(char)) return "water";
  return null;
}

const animationStyles = `
@keyframes mandala-enter {
  0% {
    transform: rotateY(0deg) rotateX(25deg) scale(0.55);
    opacity: 0;
  }
  45% {
    transform: rotateY(360deg) rotateX(-10deg) scale(1.05);
    opacity: 0.85;
  }
  70% {
    transform: rotateY(600deg) rotateX(5deg) scale(0.98);
    opacity: 1;
  }
  100% {
    transform: rotateY(720deg) rotateX(0deg) scale(1);
    opacity: 1;
  }
}

@keyframes compass-enter {
  0% {
    transform: scale(0.75);
    opacity: 0;
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes compass-spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

@keyframes card-reveal {
  0% {
    transform: rotateY(-180deg) scale(0.5);
    opacity: 0;
  }
  60% {
    transform: rotateY(20deg) scale(1.05);
    opacity: 1;
  }
  100% {
    transform: rotateY(0deg) scale(1);
    opacity: 1;
  }
}

@keyframes day-glow {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(201, 162, 39, 0);
  }
  50% {
    box-shadow: 0 0 24px 4px rgba(201, 162, 39, 0.25);
  }
}

.animate-mandala-enter {
  animation: mandala-enter 1.4s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

.animate-compass-enter {
  animation: compass-enter 0.9s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

.animate-compass-spin {
  animation: compass-spin 24s linear infinite;
}

.animate-card-reveal {
  animation: card-reveal 0.7s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

.animate-card-hide {
  transform: rotateY(-180deg) scale(0.5);
  opacity: 0;
}

.animate-day-glow {
  animation: day-glow 2.5s ease-in-out infinite;
}
`;
