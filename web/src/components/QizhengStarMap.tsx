import { useMemo } from "react";

interface Star {
  name: string;
  type: "七政" | "四余";
  color: string;
}

interface StarPosition {
  star: Star;
  palaceIndex: number;
  distance: number;
  isDominant: boolean;
}

const STARS: Star[] = [
  { name: "日", type: "七政", color: "#c9a227" },
  { name: "月", type: "七政", color: "#7a746a" },
  { name: "金", type: "七政", color: "#c9a227" },
  { name: "木", type: "七政", color: "#5a8f7b" },
  { name: "水", type: "七政", color: "#3b82f6" },
  { name: "火", type: "七政", color: "#c53d2f" },
  { name: "土", type: "七政", color: "#c9a227" },
  { name: "紫气", type: "四余", color: "#5a8f7b" },
  { name: "月孛", type: "四余", color: "#7a746a" },
  { name: "罗睺", type: "四余", color: "#c53d2f" },
  { name: "计都", type: "四余", color: "#c53d2f" },
];

// Traditional qizheng arrangement: clockwise starting from top (noon / 午).
const PALACES = [
  "午",
  "未",
  "申",
  "酉",
  "戌",
  "亥",
  "子",
  "丑",
  "寅",
  "卯",
  "辰",
  "巳",
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

interface QizhengStarMapProps {
  bazi: string;
  lifePalace?: string | null;
  bodyPalace?: string | null;
  dominantStars?: string[] | null;
}

export default function QizhengStarMap({
  bazi,
  lifePalace,
  bodyPalace,
  dominantStars,
}: QizhengStarMapProps) {
  const size = 320;
  const center = size / 2;
  const outerR = 140;
  const innerR = 92;
  const palaceR = 116;

  const lifePalaceIndex = useMemo(() => {
    if (!lifePalace) return -1;
    const branch = lifePalace.replace(/[^\u4e00-\u9fa5]/g, "").slice(-1);
    return PALACES.indexOf(branch);
  }, [lifePalace]);

  const bodyPalaceIndex = useMemo(() => {
    if (!bodyPalace) return -1;
    const branch = bodyPalace.replace(/[^\u4e00-\u9fa5]/g, "").slice(-1);
    return PALACES.indexOf(branch);
  }, [bodyPalace]);

  const dominantSet = useMemo(() => {
    return new Set((dominantStars ?? []).map((s) => s.replace(/星$/, "")));
  }, [dominantStars]);

  const starPositions = useMemo<StarPosition[]>(() => {
    const seed = hashString(bazi || "mingpan");
    let rolling = seed;
    const positions: StarPosition[] = [];

    STARS.forEach((star, index) => {
      rolling = (rolling * 9301 + 49297) % 233280;
      let palaceIndex = (lifePalaceIndex >= 0 ? lifePalaceIndex : 0) + index;
      palaceIndex = (palaceIndex + rolling) % 12;
      const distance = 0.55 + ((rolling >> 3) % 3) * 0.22;
      const isDominant = dominantSet.has(star.name);
      positions.push({ star, palaceIndex, distance, isDominant });
    });

    return positions;
  }, [bazi, lifePalaceIndex, dominantSet]);

  const starsByPalace = useMemo(() => {
    const map: Record<number, StarPosition[]> = {};
    for (const pos of starPositions) {
      if (!map[pos.palaceIndex]) map[pos.palaceIndex] = [];
      map[pos.palaceIndex].push(pos);
    }
    return map;
  }, [starPositions]);

  return (
    <div className="relative h-80 w-80 animate-fade-up">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="h-full w-full"
        aria-label="七政四余星盘"
      >
        {/* Background glow */}
        <circle
          cx={center}
          cy={center}
          r={outerR + 8}
          className="fill-vermilion/[0.03] dark:fill-vermilion/[0.06]"
        />

        {/* Outer ring */}
        <circle
          cx={center}
          cy={center}
          r={outerR}
          fill="none"
          className="stroke-ink-300/30 dark:stroke-ink-600/30"
          strokeWidth={1}
        />

        {/* Inner ring */}
        <circle
          cx={center}
          cy={center}
          r={innerR}
          fill="none"
          className="stroke-ink-300/20 dark:stroke-ink-600/20"
          strokeWidth={1}
          strokeDasharray="4 4"
        />

        {/* Palace dividers */}
        {PALACES.map((_, index) => {
          const angle = (index * 30 - 90) * (Math.PI / 180);
          const x2 = center + outerR * Math.cos(angle);
          const y2 = center + outerR * Math.sin(angle);
          return (
            <line
              key={index}
              x1={center}
              y1={center}
              x2={x2}
              y2={y2}
              className="stroke-ink-300/20 dark:stroke-ink-600/20"
              strokeWidth={1}
            />
          );
        })}

        {/* Palace labels */}
        {PALACES.map((palace, index) => {
          const angle = (index * 30 - 90) * (Math.PI / 180);
          const x = center + palaceR * Math.cos(angle);
          const y = center + palaceR * Math.sin(angle);
          const isLife = index === lifePalaceIndex;
          const isBody = index === bodyPalaceIndex;

          return (
            <g key={palace}>
              <text
                x={x}
                y={y}
                textAnchor="middle"
                dominantBaseline="central"
                className={`text-sm font-bold ${
                  isLife
                    ? "fill-vermilion"
                    : isBody
                      ? "fill-gold"
                      : "fill-ink-500 dark:fill-ink-400"
                }`}
              >
                {palace}
                {isLife && "·命"}
                {isBody && !isLife && "·身"}
              </text>
            </g>
          );
        })}

        {/* Central hub */}
        <g>
          <circle
            cx={center}
            cy={center}
            r={36}
            className="fill-ink-100 dark:fill-ink-800"
            stroke="currentColor"
            strokeWidth={1}
          />
          <text
            x={center}
            y={center - 6}
            textAnchor="middle"
            dominantBaseline="central"
            className="fill-ink-700 text-xs font-medium dark:fill-ink-200"
          >
            命宫
          </text>
          <text
            x={center}
            y={center + 12}
            textAnchor="middle"
            dominantBaseline="central"
            className="fill-vermilion text-lg font-bold"
          >
            {lifePalace ? lifePalace.replace(/[^\u4e00-\u9fa5]/g, "").slice(-1) : "?"}
          </text>
        </g>

        {/* Stars grouped by palace */}
        {Object.entries(starsByPalace).map(([palaceIndexStr, positions]) => {
          const palaceIndex = Number(palaceIndexStr);
          const baseAngle = (palaceIndex * 30 - 90) * (Math.PI / 180);
          const baseX = center + innerR * 0.72 * Math.cos(baseAngle);
          const baseY = center + innerR * 0.72 * Math.sin(baseAngle);
          const count = positions.length;
          const spread = Math.min(26, (count - 1) * 13);

          return positions.map((pos, idx) => {
            const offset = idx * 13 - spread / 2;
            const x = baseX + offset;
            const y = baseY;
            const { star, isDominant } = pos;

            return (
              <g key={`${star.name}-${palaceIndex}`}>
                <circle
                  cx={x}
                  cy={y}
                  r={isDominant ? 14 : 11}
                  className={`${
                    star.type === "七政"
                      ? "fill-white dark:fill-ink-900"
                      : "fill-ink-100 dark:fill-ink-800"
                  }`}
                  stroke={star.color}
                  strokeWidth={isDominant ? 2 : 1}
                />
                <text
                  x={x}
                  y={y}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={isDominant ? 11 : 10}
                  fontWeight={isDominant ? 700 : 500}
                  fill={star.color}
                >
                  {star.name}
                </text>
              </g>
            );
          });
        })}
      </svg>

      {/* Legend */}
      <div className="absolute -bottom-2 left-1/2 flex -translate-x-1/2 gap-3 text-xs text-ink-500 dark:text-ink-400">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-vermilion" />
          命宫
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-gold" />
          身宫
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full border border-ink-400" />
          七政四余
        </span>
      </div>
    </div>
  );
}
