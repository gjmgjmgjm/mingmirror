"""Static reference tables for Qi Zheng Si Yu (七政四余).

The 28-lunar-mansion boundary table uses the 郑案古宿 (Zheng'an ancient
mansions) degree system taken from the Mimori-su/qizheng-siyu-skills
knowledge base.  Precession is not applied here; a sidereal/precession
switch can be added later as a small offset to the input longitude.
"""

from typing import Dict, List, Optional, Tuple

# ── 十二宫 ──
PALACE_NAMES: List[str] = [
    "命宫", "财帛", "兄弟", "田宅", "男女", "奴仆",
    "夫妻", "疾厄", "迁移", "官禄", "福德", "相貌",
]

# 地支顺序（子丑寅卯…）
EARTHLY_BRANCHES: List[str] = [
    "子", "丑", "寅", "卯", "辰", "巳",
    "午", "未", "申", "酉", "戌", "亥",
]

# 十二宫地支 → 宫主星（果老星宗常见取法）
PALACE_LORD: Dict[str, str] = {
    "子": "土星",
    "丑": "土星",
    "寅": "木星",
    "卯": "火星",
    "辰": "金星",
    "巳": "水星",
    "午": "太阳",
    "未": "太阴",
    "申": "水星",
    "酉": "金星",
    "戌": "火星",
    "亥": "木星",
}

# 黄道星座（上升点）→ 命宫地支。
# 果老星宗以戌宫起白羊，逆行排布：白羊戌、金牛酉、双子申、巨蟹未、狮子午、处女巳、
# 天秤辰、天蝎卯、人马寅、摩羯丑、宝瓶子、双鱼亥。
ZODIAC_TO_BRANCH: Dict[str, str] = {
    "白羊": "戌",
    "金牛": "酉",
    "双子": "申",
    "巨蟹": "未",
    "狮子": "午",
    "处女": "巳",
    "天秤": "辰",
    "天蝎": "卯",
    "人马": "寅",
    "摩羯": "丑",
    "宝瓶": "子",
    "双鱼": "亥",
}


def twelve_palaces(life_palace_branch: str) -> Dict[str, str]:
    """Return a mapping of palace name to branch, starting from the life palace.

    The 12 palaces are arranged counter-clockwise starting at the life palace.
    """
    if life_palace_branch not in EARTHLY_BRANCHES:
        return {}
    start = EARTHLY_BRANCHES.index(life_palace_branch)
    result: Dict[str, str] = {}
    for i, name in enumerate(PALACE_NAMES):
        # counter-clockwise: 子->亥->戌->... in standard branch order is reverse
        idx = (start - i) % 12
        result[name] = EARTHLY_BRANCHES[idx]
    return result

# 十二宫简释
PALACE_MEANING: Dict[str, Tuple[str, str]] = {
    "命宫": ("自身", "性格、体质、一生根基"),
    "财帛": ("正财", "收入、理财、现金流"),
    "兄弟": ("同辈", "兄弟、合伙、竞争"),
    "田宅": ("家庭", "房产、家宅、祖业"),
    "男女": ("子女", "子女、学生、下属"),
    "奴仆": ("人际", "同事、朋友、小人"),
    "夫妻": ("配偶", "婚姻、感情、同居"),
    "疾厄": ("健康", "疾病、灾厄、手术"),
    "迁移": ("外出", "远行、变动、异乡"),
    "官禄": ("事业", "职位、名誉、公职"),
    "福德": ("精神", "福报、贵人、晚运"),
    "相貌": ("形象", "外貌、气质、第一印象"),
}

# ── 黄道十二宫（西方星座，中文名） ──
ZODIAC_SIGNS: List[str] = [
    "白羊", "金牛", "双子", "巨蟹", "狮子", "处女",
    "天秤", "天蝎", "人马", "摩羯", "宝瓶", "双鱼",
]

# ── 七政四余 ──
SEVEN_GOVERNORS: List[str] = ["太阳", "太阴", "木星", "火星", "土星", "金星", "水星"]
FOUR_REMAINDERS: List[str] = ["罗睺", "计都", "月孛", "紫气"]
ALL_BODIES: List[str] = SEVEN_GOVERNORS + FOUR_REMAINDERS

# 五行生克（用于星曜与地支的快速生克判断）
_GENERATING: Dict[str, str] = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_RESTRAINING: Dict[str, str] = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

# 地支五行
BRANCH_ELEMENT: Dict[str, str] = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# 七政四余五行
BODY_ELEMENT: Dict[str, str] = {
    "太阳": "火",
    "太阴": "水",
    "木星": "木",
    "火星": "火",
    "土星": "土",
    "金星": "金",
    "水星": "水",
    "罗睺": "火",
    "计都": "土",
    "月孛": "水",
    "紫气": "木",
}

# 七政四余吉凶（简分）
BODY_AUSPICIOUS: Dict[str, str] = {
    "太阳": "大吉",
    "太阴": "吉",
    "木星": "吉",
    "火星": "凶",
    "土星": "凶",
    "金星": "吉",
    "水星": "中",
    "罗睺": "凶",
    "计都": "凶",
    "月孛": "凶",
    "紫气": "吉",
}

# 星曜庙旺落陷（地支对应）。
# 结构：{星曜: {"庙": 地支集合, "旺": 地支集合, "陷": 地支集合, "喜": 地支集合, "乐": 地支集合}}
# 支持多地支入庙/入旺，便于兼容不同流派。
MIAO_WANG: Dict[str, Dict[str, set]] = {
    "太阳": {"庙": {"戌"}, "旺": {"午"}, "陷": {"辰"}, "喜": {"寅", "卯"}, "乐": {"午"}},
    "太阴": {"庙": {"未"}, "旺": {"卯"}, "陷": {"酉"}, "喜": {"戌", "亥"}, "乐": {"未"}},
    "木星": {"庙": {"未"}, "旺": {"亥"}, "陷": {"酉"}, "喜": {"寅", "卯"}, "乐": {"寅", "亥"}},
    "火星": {"庙": {"卯"}, "旺": {"戌"}, "陷": {"子"}, "喜": {"巳", "午"}, "乐": {"卯"}},
    "土星": {"庙": {"子"}, "旺": {"酉"}, "陷": {"卯"}, "喜": {"辰", "戌", "丑", "未"}, "乐": {"子", "丑"}},
    "金星": {"庙": {"酉"}, "旺": {"巳"}, "陷": {"卯"}, "喜": {"申", "酉"}, "乐": {"酉"}},
    "水星": {"庙": {"巳"}, "旺": {"申"}, "陷": {"午"}, "喜": {"亥", "子"}, "乐": {"巳", "申"}},
}

# 杨国正派庙旺喜乐表（依果老星宗卷一整理）。
# 来源：杨国正《七政四余论命术》讲义。
MIAO_WANG_YANG: Dict[str, Dict[str, set]] = {
    "太阳": {"庙": {"午"}, "旺": {"巳", "戌"}, "陷": {"子", "辰", "亥"}, "喜": {"寅"}, "乐": {"午", "辰"}},
    "太阴": {"庙": {"戌"}, "旺": {"酉"}, "陷": {"辰", "卯"}, "喜": {"亥", "卯"}, "乐": {"未"}},
    "木星": {"庙": {"亥"}, "旺": {"未"}, "陷": {"巳", "丑"}, "喜": {"未"}, "乐": {"寅", "亥"}},
    "火星": {"庙": {"卯"}, "旺": {"丑"}, "陷": {"酉", "未"}, "喜": {"丑", "申"}, "乐": {"卯"}},
    "土星": {"庙": {"子", "丑"}, "旺": {"卯", "辰"}, "陷": {"午", "未", "酉", "戌"}, "喜": {"午"}, "乐": {"丑", "子"}},
    "金星": {"庙": {"辰", "酉"}, "旺": {"午", "亥"}, "陷": {"戌", "卯", "子", "巳"}, "喜": {"巳"}, "乐": {"辰", "酉"}},
    "水星": {"庙": {"午"}, "旺": {"子", "巳", "申"}, "陷": {"子", "午", "亥", "寅"}, "喜": {"辰"}, "乐": {"巳", "申"}},
}

# 默认 dignity 表。评估显示默认表在 Celebrity50 上入垣一致率更高、强状态区分度更好。
DEFAULT_DIGNITY_TABLE: Dict[str, Dict[str, set]] = MIAO_WANG

# 可切换的 dignity 表名称映射。None 表示使用默认表。
DIGNITY_TABLE_NAMES: Dict[str, Optional[Dict[str, Dict[str, set]]]] = {
    "default": None,
    "yang": MIAO_WANG_YANG,
}


def resolve_dignity_table(
    name: Optional[str],
) -> Optional[Dict[str, Dict[str, set]]]:
    """Resolve a dignity table identifier to a table object.

    Supported names: ``"default"`` / ``""`` / ``None`` for the built-in default
    table, ``"yang"`` for the Yang Guozheng school table.
    """
    if not name:
        return None
    table = DIGNITY_TABLE_NAMES.get(name.strip().lower())
    if table is None and name.strip().lower() not in ("default", ""):
        raise ValueError(f"未知的 dignity 表：{name}")
    return table

# 四余不单独列庙旺，按余气论：紫气吉、罗计孛凶，落宫以宫主生克定强弱。


def body_dignity(
    body: str,
    branch: str,
    table: Optional[Dict[str, Dict[str, set]]] = None,
) -> str:
    """Return the dignity of a 七政 star in a given earthly branch palace.

    *table* defaults to ``DEFAULT_DIGNITY_TABLE``.  A different table (e.g.
    ``MIAO_WANG_YANG``) can be passed to compare traditions.
    """
    if table is None:
        table = DEFAULT_DIGNITY_TABLE
    if body not in table:
        return "平"
    entry = table[body]
    if branch in entry.get("庙", set()):
        return "庙"
    if branch in entry.get("旺", set()):
        return "旺"
    if branch in entry.get("乐", set()):
        return "乐"
    if branch in entry.get("陷", set()):
        return "陷"
    if branch in entry.get("喜", set()):
        return "得地"
    return "平"


# 入垣（入宫）：星曜入其宫主地支。四余随其五行余气同论。
RU_YUAN: Dict[str, set] = {
    "太阳": {"午"},
    "太阴": {"未"},
    "水星": {"巳", "申"},
    "金星": {"辰", "酉"},
    "火星": {"卯", "戌"},
    "木星": {"寅", "亥"},
    "土星": {"子", "丑"},
    "紫气": {"寅", "亥"},
    "罗睺": {"卯", "戌"},
    "计都": {"子", "丑"},
    "月孛": {"巳", "申"},
}

# 升殿（入宿）：星曜躔其本宿度。四余随其五行余气同论。
SHENG_DIAN: Dict[str, set] = {
    "太阳": {"星", "房", "虚", "昴"},
    "太阴": {"心", "危", "毕", "张"},
    "水星": {"箕", "壁", "参", "轸"},
    "金星": {"亢", "牛", "娄", "鬼"},
    "火星": {"尾", "室", "翼", "觜"},
    "木星": {"角", "斗", "奎", "井"},
    "土星": {"氐", "女", "胃", "柳"},
    "紫气": {"角", "斗", "奎", "井"},
    "罗睺": {"尾", "室", "翼", "觜"},
    "计都": {"氐", "女", "胃", "柳"},
    "月孛": {"箕", "壁", "参", "轸"},
}


def body_rulership(body: str, branch: str) -> str:
    """Return whether a body is in its ruling palace (入垣)."""
    if body in RU_YUAN and branch in RU_YUAN[body]:
        return "入垣"
    return "不入垣"


def body_exaltation(body: str, mansion: str) -> str:
    """Return whether a body is exalted in its mansion (升殿)."""
    if body in SHENG_DIAN and mansion in SHENG_DIAN[body]:
        return "升殿"
    return "不升殿"


def body_strength(
    body: str,
    branch: str,
    mansion: str,
    dignity_table: Optional[Dict[str, Dict[str, set]]] = None,
) -> str:
    """Return a combined strength label for a 七政 body.

    Priority: 庙 > 旺 > 乐 > 入垣升殿 > 入垣 > 升殿 > 得地 > 平 > 陷.
    For the four remainders, an element-based palace-branch relation is also
    consulted when no explicit dignity rule applies.
    """
    dignity = body_dignity(body, branch, dignity_table)
    if dignity in ("庙", "旺", "乐", "陷", "得地"):
        return dignity
    rulership = body_rulership(body, branch)
    exaltation = body_exaltation(body, mansion)
    if rulership == "入垣" and exaltation == "升殿":
        return "入垣升殿"
    if rulership == "入垣":
        return "入垣"
    if exaltation == "升殿":
        return "升殿"

    # For the four remainders, fall back to the element relation between the
    # body's own element and the palace branch element.
    if body in FOUR_REMAINDERS and dignity == "平":
        body_el = BODY_ELEMENT.get(body)
        branch_el = BRANCH_ELEMENT.get(branch)
        if body_el and branch_el:
            if branch_el == body_el or _GENERATING.get(branch_el) == body_el:
                return "得地"
            if _RESTRAINING.get(branch_el) == body_el:
                return "陷"
    return dignity


# ── 二十八宿（郑案古宿度数边界） ──
# 表为「宿末黄经」，从娄宿起算（0° 白羊附近为娄宿起点）。
# 用法：将黄经落在 (previous_end, end] 区间的度数归为当前宿。
_LUNAR_MANSION_BOUNDARIES: List[Tuple[str, float]] = [
    ("娄", 15.00),
    ("胃", 26.50),
    ("昴", 42.03),
    ("毕", 53.10),
    ("觜", 70.16),
    ("参", 71.08),
    ("井", 81.02),
    ("鬼", 113.73),
    ("柳", 115.94),
    ("星", 128.96),
    ("张", 135.15),
    ("翼", 152.35),
    ("轸", 170.89),
    ("角", 188.07),
    ("亢", 200.03),
    ("氐", 208.93),
    ("房", 225.21),
    ("心", 230.70),
    ("尾", 236.98),
    ("箕", 255.74),
    ("斗", 265.93),
    ("牛", 290.60),
    ("女", 297.84),
    ("虚", 308.89),
    ("危", 317.70),
    ("室", 333.06),
    ("壁", 349.97),
    ("奎", 358.44),
]


MANSION_SEQUENCE: List[str] = [name for name, _ in _LUNAR_MANSION_BOUNDARIES]


def mansion_for_degree(degree: float, precession_offset: float = 0.0) -> str:
    """Return the 28-mansion name for an ecliptic longitude.

    The input degree is normalised to [0, 360).  *precession_offset* is the
    ayanamsha value to subtract for sidereal mode (default 0, i.e. tropical).
    """
    degree = (degree - precession_offset) % 360.0
    prev_end = 0.0
    for name, end in _LUNAR_MANSION_BOUNDARIES:
        if prev_end <= degree < end:
            return name
        prev_end = end
    # 358.44 ~ 360.0 归入娄宿（下一循环起点）
    return "娄"


# ── 相位 ──
# (名称, 角度, 容许度, 吉凶)
ASPECTS: List[Tuple[str, float, float, str]] = [
    ("合相", 0.0, 8.0, "中"),
    ("六合", 60.0, 5.0, "吉"),
    ("刑", 90.0, 5.0, "凶"),
    ("拱", 120.0, 6.0, "大吉"),
    ("冲", 180.0, 6.0, "凶"),
]


def angular_gap(a: float, b: float) -> float:
    """Return the smallest angular distance between two ecliptic degrees."""
    gap = abs((a - b) % 360.0)
    if gap > 180.0:
        gap = 360.0 - gap
    return gap


# ── 常见格局 ──
# 格局名 + 简短说明
PATTERN_CATALOG: Dict[str, str] = {
    "日月并明": "日月同照命身或官福，主大贵，名利双全",
    "日月拱照": "日月三合，贵气临身",
    "日月合璧": "日月同宫或同度，光明之象",
    "官福拱命": "官禄、福德二宫主星拱照命宫",
    "官福朝拱": "官禄、福德二宫主星三方或对照拱照命宫",
    "君臣庆会": "日月同宫或三合，且庙旺得力，主大贵",
    "金水会垣": "金水同宫于巳申辰酉，聪明科甲",
    "木火通明": "木火同宫或三合，文明奋发",
    "土金相生": "土金同宫或三合，厚重生财",
    "木气朝垣": "木星入命宫，一生富贵",
    "紫气朝垣": "紫气入命宫或官禄宫，福寿清贵",
    "月孛守命": "月孛入命宫，性情机巧，多变动",
    "罗计夹命": "罗睺、计都夹拱命宫，主波折而贵",
    "罗计拦截": "罗睺、计都截出吉星，主贵显但过程波折",
    "五星连珠": "多星同宫或同度，能量集中",
    "金水相生": "金水同宫，聪明智慧、利文书交际",
    "火土相刑": "火土对冲或相刑，防口舌是非、意外",
    "土计掩月": "土星、计都掩太阴，主母病、财破、情绪抑郁",
    "紫气临命": "紫气入命，福寿双全",
}
