export const STEMS = [
  "甲",
  "乙",
  "丙",
  "丁",
  "戊",
  "己",
  "庚",
  "辛",
  "壬",
  "癸",
] as const;

export const BRANCHES = [
  "子",
  "丑",
  "寅",
  "卯",
  "辰",
  "巳",
  "午",
  "未",
  "申",
  "酉",
  "戌",
  "亥",
] as const;

export type Stem = (typeof STEMS)[number];
export type Branch = (typeof BRANCHES)[number];
export type Element = "wood" | "fire" | "earth" | "metal" | "water";

const STEM_ELEMENTS: Record<Stem, Element> = {
  甲: "wood",
  乙: "wood",
  丙: "fire",
  丁: "fire",
  戊: "earth",
  己: "earth",
  庚: "metal",
  辛: "metal",
  壬: "water",
  癸: "water",
};

const BRANCH_ELEMENTS: Record<Branch, Element> = {
  子: "water",
  丑: "earth",
  寅: "wood",
  卯: "wood",
  辰: "earth",
  巳: "fire",
  午: "fire",
  未: "earth",
  申: "metal",
  酉: "metal",
  戌: "earth",
  亥: "water",
};

export const ELEMENT_META: Record<
  Element,
  { label: string; color: string; bg: string; ring: string }
> = {
  wood: {
    label: "木",
    color: "text-emerald-700 dark:text-emerald-400",
    bg: "bg-emerald-100 dark:bg-emerald-900/30",
    ring: "ring-emerald-400/40",
  },
  fire: {
    label: "火",
    color: "text-vermilion",
    bg: "bg-vermilion/10 dark:bg-vermilion/20",
    ring: "ring-vermilion/40",
  },
  earth: {
    label: "土",
    color: "text-gold",
    bg: "bg-gold/10 dark:bg-gold/20",
    ring: "ring-gold/40",
  },
  metal: {
    label: "金",
    color: "text-slate-600 dark:text-slate-300",
    bg: "bg-slate-200 dark:bg-slate-700/40",
    ring: "ring-slate-400/40",
  },
  water: {
    label: "水",
    color: "text-blue-700 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-900/30",
    ring: "ring-blue-400/40",
  },
};

export interface Pillar {
  stem: Stem;
  branch: Branch;
  stemElement: Element;
  branchElement: Element;
}

export interface ParsedBazi {
  year: Pillar;
  month: Pillar;
  day: Pillar;
  hour: Pillar;
  dayMaster: Stem;
}

export function parseBazi(input: string): ParsedBazi | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  const separators = /[,，\s]+/;
  let parts = trimmed.split(separators).filter(Boolean);

  if (parts.length !== 4) {
    if (trimmed.length >= 8) {
      parts = [
        trimmed.slice(0, 2),
        trimmed.slice(2, 4),
        trimmed.slice(4, 6),
        trimmed.slice(6, 8),
      ];
    } else {
      return null;
    }
  }

  const [year, month, day, hour] = parts.map((part) => {
    const stem = part[0] as Stem;
    const branch = part[1] as Branch;
    if (!STEMS.includes(stem) || !BRANCHES.includes(branch)) {
      return null;
    }
    return {
      stem,
      branch,
      stemElement: STEM_ELEMENTS[stem],
      branchElement: BRANCH_ELEMENTS[branch],
    };
  });

  if (!year || !month || !day || !hour) return null;

  return {
    year,
    month,
    day,
    hour,
    dayMaster: day.stem,
  };
}

export function countElements(parsed: ParsedBazi): Record<Element, number> {
  const counts: Record<Element, number> = {
    wood: 0,
    fire: 0,
    earth: 0,
    metal: 0,
    water: 0,
  };

  const pillars = [parsed.year, parsed.month, parsed.day, parsed.hour];
  for (const p of pillars) {
    counts[p.stemElement] += 1;
    counts[p.branchElement] += 1;
  }

  return counts;
}

const HIDDEN_STEMS: Record<Branch, string[]> = {
  子: ["癸"],
  丑: ["己", "癸", "辛"],
  寅: ["甲", "丙", "戊"],
  卯: ["乙"],
  辰: ["戊", "乙", "癸"],
  巳: ["丙", "庚", "戊"],
  午: ["丁", "己"],
  未: ["己", "丁", "乙"],
  申: ["庚", "壬", "戊"],
  酉: ["辛"],
  戌: ["戊", "辛", "丁"],
  亥: ["壬", "甲"],
};

export function getHiddenStems(branch: Branch): string[] {
  return HIDDEN_STEMS[branch] ?? [];
}
