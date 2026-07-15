import { useMemo } from "react";

interface Star {
  name: string;
  type: "主星" | "辅星" | "煞星";
  brightness: number;
}

interface StarInPalace {
  star: Star;
  palaceIndex: number;
}

const PALACES = [
  "命宫",
  "兄弟",
  "夫妻",
  "子女",
  "财帛",
  "疾厄",
  "迁移",
  "交友",
  "官禄",
  "田宅",
  "福德",
  "父母",
];

// Traditional ziwei arrangement: 命宫 at bottom-right, then counter-clockwise.
const PALACE_POSITIONS = [
  "巳", "午", "未", "申",
  "辰",          "酉",
  "卯",          "戌",
  "寅", "丑", "子", "亥",
];

const MAIN_STARS: Star[] = [
  { name: "紫微", type: "主星", brightness: 5 },
  { name: "天府", type: "主星", brightness: 5 },
  { name: "太阳", type: "主星", brightness: 4 },
  { name: "太阴", type: "主星", brightness: 4 },
  { name: "贪狼", type: "主星", brightness: 4 },
  { name: "巨门", type: "主星", brightness: 3 },
  { name: "天相", type: "主星", brightness: 4 },
  { name: "天梁", type: "主星", brightness: 4 },
  { name: "七杀", type: "主星", brightness: 4 },
  { name: "破军", type: "主星", brightness: 4 },
  { name: "廉贞", type: "主星", brightness: 4 },
  { name: "武曲", type: "主星", brightness: 4 },
];

const AUX_STARS: Star[] = [
  { name: "左辅", type: "辅星", brightness: 3 },
  { name: "右弼", type: "辅星", brightness: 3 },
  { name: "文昌", type: "辅星", brightness: 3 },
  { name: "文曲", type: "辅星", brightness: 3 },
  { name: "天魁", type: "辅星", brightness: 3 },
  { name: "天钺", type: "辅星", brightness: 3 },
  { name: "禄存", type: "辅星", brightness: 4 },
  { name: "天马", type: "辅星", brightness: 3 },
];

const SHA_STARS: Star[] = [
  { name: "火星", type: "煞星", brightness: 2 },
  { name: "铃星", type: "煞星", brightness: 2 },
  { name: "擎羊", type: "煞星", brightness: 2 },
  { name: "陀罗", type: "煞星", brightness: 2 },
  { name: "地空", type: "煞星", brightness: 1 },
  { name: "地劫", type: "煞星", brightness: 1 },
];

function hashString(input: string): number {
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    const char = input.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0;
  }
  return Math.abs(hash);
}

function distributeStars(bazi: string): StarInPalace[] {
  const seed = hashString(bazi || "mingpan");
  let rolling = seed;
  const allStars = [...MAIN_STARS, ...AUX_STARS, ...SHA_STARS];
  const result: StarInPalace[] = [];

  allStars.forEach((star) => {
    rolling = (rolling * 9301 + 49297) % 233280;
    const palaceIndex = rolling % 12;
    result.push({ star, palaceIndex });
  });

  return result;
}

interface ZiweiStarMapProps {
  bazi: string;
}

export default function ZiweiStarMap({ bazi }: ZiweiStarMapProps) {
  const starMap = useMemo(() => {
    const stars = distributeStars(bazi);
    const map: Record<number, StarInPalace[]> = {};
    for (const item of stars) {
      if (!map[item.palaceIndex]) map[item.palaceIndex] = [];
      map[item.palaceIndex].push(item);
    }
    for (const key of Object.keys(map)) {
      map[Number(key)].sort((a, b) => b.star.brightness - a.star.brightness);
    }
    return map;
  }, [bazi]);

  const lifePalaceIndex = useMemo(() => hashString(bazi) % 12, [bazi]);

  return (
    <div className="relative mx-auto w-full max-w-2xl animate-fade-up">
      <div className="grid grid-cols-4 gap-2 md:gap-3">
        {PALACES.map((palace, index) => {
          const stars = starMap[index] || [];
          const isLife = index === lifePalaceIndex;
          const position = PALACE_POSITIONS[index];

          return (
            <div
              key={palace}
              className={`relative rounded-xl border p-2 transition hover:-translate-y-0.5 md:p-3 ${
                isLife
                  ? "border-vermilion/40 bg-vermilion/5 dark:border-vermilion/50 dark:bg-vermilion/10"
                  : "border-ink-300/20 bg-white/60 dark:border-ink-600/30 dark:bg-ink-800/60"
              }`}
              style={{ animationDelay: `${index * 40}ms` }}
            >
              <div className="mb-1 flex items-center justify-between">
                <span
                  className={`text-xs font-bold ${
                    isLife ? "text-vermilion" : "text-ink-500 dark:text-ink-400"
                  }`}
                >
                  {palace}
                </span>
                <span className="text-[10px] text-ink-400 dark:text-ink-500">
                  {position}
                </span>
              </div>
              <div className="flex flex-wrap gap-1">
                {stars.slice(0, 4).map((item) => {
                  const { star } = item;
                  const colorClass =
                    star.type === "主星"
                      ? "text-vermilion bg-vermilion/10 dark:bg-vermilion/20"
                      : star.type === "辅星"
                        ? "text-gold bg-gold/10 dark:bg-gold/20"
                        : "text-ink-500 bg-ink-200/60 dark:bg-ink-700/60 dark:text-ink-300";
                  return (
                    <span
                      key={star.name}
                      className={`rounded px-1 py-0.5 text-[10px] font-medium md:text-xs ${colorClass}`}
                    >
                      {star.name}
                    </span>
                  );
                })}
              </div>
              {isLife && (
                <div className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-vermilion text-[8px] text-white md:h-5 md:w-5 md:text-[10px]">
                  命
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-3 flex flex-wrap justify-center gap-3 text-xs text-ink-500 dark:text-ink-400">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded bg-vermilion/70" />
          主星
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded bg-gold/70" />
          辅星
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded bg-ink-400" />
          煞星
        </span>
      </div>
    </div>
  );
}
