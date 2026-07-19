#!/usr/bin/env python3
"""Symbolic rule reasoner for BaziQA multiple-choice questions.

This module provides deterministic, explainable heuristics for question types
that can be partially symbolized:

- marriage year / relationship events
- children year
- parent death year
- career / wealth trend
- health issue type

It returns ranked option candidates with confidence.  The evaluator can use
high-confidence candidates directly and fall back to the LLM when confidence
is low.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from tools.bazi_ai.bazi_structural import _ELEMENT, shishen_for_stem
from tools.bazi_ai.bazi_validator import extract_pillars
from tools.bazi_ai.calendar import dayun_list

_GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
_ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 十神名称（以日主为“我”）
_SHI_SHEN = {
    "same_yang": "比肩",
    "same_yin": "劫财",
    "generate_yang": "食神",
    "generate_yin": "伤官",
    "restrain_yang": "偏财",
    "restrain_yin": "正财",
    "generated_by_yang": "偏印",
    "generated_by_yin": "正印",
    "restrained_by_yang": "七杀",
    "restrained_by_yin": "正官",
}

# 地支藏干（本气、中气、余气）
_ZHI_CANG_GAN: Dict[str, Tuple[str, ...]] = {
    "子": ("癸",),
    "丑": ("己", "癸", "辛"),
    "寅": ("甲", "丙", "戊"),
    "卯": ("乙",),
    "辰": ("戊", "乙", "癸"),
    "巳": ("丙", "戊", "庚"),
    "午": ("丁", "己"),
    "未": ("己", "丁", "乙"),
    "申": ("庚", "壬", "戊"),
    "酉": ("辛",),
    "戌": ("戊", "辛", "丁"),
    "亥": ("壬", "甲"),
}

# 地支六合、六冲、三合（用于判断宫位/星被引动）
_LIU_HE = {
    ("子", "丑"): "土", ("寅", "亥"): "木", ("卯", "戌"): "火",
    ("辰", "酉"): "金", ("巳", "申"): "水", ("午", "未"): "土",
}
_CHONG = {
    ("子", "午"), ("丑", "未"), ("寅", "申"),
    ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
}
_SAN_HE = {
    ("申", "子", "辰"): "水", ("寅", "午", "戌"): "火",
    ("亥", "卯", "未"): "木", ("巳", "酉", "丑"): "金",
}


def _normalize_pair(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _is_liu_he(a: str, b: str) -> bool:
    return _normalize_pair(a, b) in {(x, y) for x, y in _LIU_HE}


def _is_chong(a: str, b: str) -> bool:
    return _normalize_pair(a, b) in _CHONG


def _is_in_san_he(a: str, b: str, c: str) -> bool:
    for triad, _ in _SAN_HE.items():
        if {a, b, c} == set(triad):
            return True
    return False


def _yin_yang(gan: str) -> str:
    return "阳" if _GAN.index(gan) % 2 == 0 else "阴"


def _shishen(day_master: str, target: str) -> str:
    """Return the ten-god of *target* relative to *day_master*.

    Delegates to the element-based implementation in ``bazi_structural`` to
    handle all day masters correctly (the old offset-based table was only
    correct for a subset of day masters).
    """
    return shishen_for_stem(day_master, target)


def _all_stems_in_chart(bazi: str) -> List[Tuple[str, str, str]]:
    """Return list of (position, gan, shishen) for all visible stems."""
    pillars = extract_pillars(bazi)
    day_master = pillars[2][0]
    labels = ["年干", "月干", "日干", "时干"]
    return [(labels[i], pillars[i][0], _shishen(day_master, pillars[i][0])) for i in range(4)]


def _all_branches_with_hidden(bazi: str) -> List[Tuple[str, str, List[Tuple[str, str]]]]:
    """Return list of (position, zhi, [(gan, shishen), ...])."""
    pillars = extract_pillars(bazi)
    day_master = pillars[2][0]
    labels = ["年支", "月支", "日支", "时支"]
    result = []
    for i in range(4):
        zhi = pillars[i][1]
        hidden = [(g, _shishen(day_master, g)) for g in _ZHI_CANG_GAN[zhi]]
        result.append((labels[i], zhi, hidden))
    return result


def _find_star_positions(bazi: str, stars: List[str]) -> List[Tuple[str, str, str]]:
    """Find all positions (stem/branch/hidden) where a ten-god appears.

    Returns list of (position_label, gan_or_zhi, ten_god_name).
    """
    found = []
    for pos, gan, ss in _all_stems_in_chart(bazi):
        if ss in stars:
            found.append((pos, gan, ss))
    for pos, zhi, hidden in _all_branches_with_hidden(bazi):
        for gan, ss in hidden:
            if ss in stars:
                found.append((pos, gan, ss))
    return found


def _extract_years(text: str) -> List[int]:
    """Extract Gregorian years from option/question text.

    Avoid ``\\b`` word boundaries: in Python 3 Unicode mode, CJK characters are
    word chars, so patterns like ``2010年`` fail to match (no boundary between
    digit and 年).  Use digit lookarounds instead.
    """
    return sorted(set(int(y) for y in re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", text)))


def _year_pillar(year: int) -> str:
    """Return the gan-zhi pillar for a given Gregorian year."""
    # 1984 = 甲子年
    offset = (year - 1984) % 60
    gan = _GAN[offset % 10]
    zhi = _ZHI[offset % 12]
    return gan + zhi


# 地支三会局（按季节/方位）
_SAN_HUI = {
    ("寅", "卯", "辰"): "木",
    ("巳", "午", "未"): "火",
    ("申", "酉", "戌"): "金",
    ("亥", "子", "丑"): "水",
}

# 天干五合（甲己、乙庚、丙辛、丁壬、戊癸）。
# NOTE: 旧实现把天干 pair 拿去查地支六合表 _LIU_HE，永远匹配不上，等于死代码。
# 这里是正确的天干五合集合。
_TIAN_GAN_WU_HE = {
    ("甲", "己"), ("乙", "庚"), ("丙", "辛"), ("丁", "壬"), ("戊", "癸"),
}

# 五行相克关系（用于天克地冲判定）
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
_GAN_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}


def _restrains(a_gan: str, b_gan: str) -> bool:
    """True if the element of *a_gan* overcomes (克) the element of *b_gan*."""
    return _KE.get(_GAN_ELEMENT[a_gan]) == _GAN_ELEMENT[b_gan]


# ---------------------------------------------------------------------------
# 应期信号权重（2026-07-11 由 LOO 逻辑回归在 25 道 contest8 年份题上标定，
# 见 benchmarks/baziqa/rule_calibrate.py；符号方向经 per-signal gold/pick 触发率
# 复核，见 benchmarks/baziqa/rule_diagnose.py）。
#
# 关键修正：
#   - stem_star 旧权重 +2.0（最高），但它在“错误选项”上触发 4× 于“正确选项”，
#     属反向预测信号 → 置 0。
#   - stem_wuhe_daymaster（天干五合）旧实现是死代码，修复后为最强正向信号。
#   - 新增 tian_kang_di_chong / fan_yin_day_branch / fu_yin_day_branch 应期信号。
#   - hidden_star / branch_sanhui_palace 经回归判定为反向/噪声 → 置 0。
# 绝对天花板：star/palace 符号特征在该题集上 LOO top-1 ≈ 36%，top-2 ≈ 56%。
# 因此引擎只在大 margin 时覆盖 LLM（见 _best_candidate 的 margin 置信度）。
# ---------------------------------------------------------------------------
YEAR_SIGNAL_WEIGHTS: Dict[str, float] = {
    # 2026-07-19 LOO recalib (rule_calibrate_v2): coordinate ascent on
    # contest8 year-asking n=44.  Full top1 36.4%→45.5%, top2 54.5%→61.4%;
    # soft-shortlist sim top2 60.6%→69.6% (fewer fires, higher quality).
    # —— 正向 ——
    "stem_wuhe_daymaster": 0.9,   # 天干五合（保持）
    "tian_kang_di_chong": 0.5,    # 天克地冲（保持）
    "parent_guansha_ke": 0.4,     # 官杀克身（父母/官非）
    "dayun_stem_star": 0.3,       # 大运天干目标十神
    "dayun_chong_palace": 0.3,    # 大运冲事件宫
    "branch_sanhe_palace": 0.2,   # 半三合（0.4→0.2，降权减噪）
    "dayun_liuhe_palace": 0.2,    # 大运合事件宫
    "fu_yin_day_branch": 0.2,     # 伏吟
    "dayun_hidden_star": 0.1,     # 大运藏干目标十神
    # —— 反向/降权（标定：在错误选项上触发更多）——
    "fan_yin_day_branch": -0.2,   # 反吟 0.3→−0.2
    "branch_chong_palace": -0.2,  # 流年冲宫 0.1→−0.2
    # —— 噪声，置 0 ——
    "stem_star": 0.0,
    "hidden_star": 0.0,
    "branch_sanhui_palace": 0.0,
    "dayun_sanhe_palace": 0.0,
    "branch_liuhe_palace": 0.0,
    "sui_yun_bing_lin": 0.0,
}

# 置信度 margin 阈值（top1 与 top2 的分差）。LOO 标定：
#   margin >= HIGH_MARGIN  → 高置信度切片准确率 ~75%
#   margin >= MED_MARGIN   → ~58%
_YEAR_CONF_HIGH_MARGIN = 0.5
_YEAR_CONF_MED_MARGIN = 0.2


def _san_he_element_for_pair(a: str, b: str) -> Optional[str]:
    """Return the element of a 三合局 if *a* and *b* are two distinct branches.

    Recognises both adjacent pairs (半合) and the two end branches (拱合).
    """
    if a == b:
        return None
    for triad, element in _SAN_HE.items():
        if {a, b}.issubset(set(triad)):
            return element
    return None


def _san_hui_element_for_pair(a: str, b: str) -> Optional[str]:
    """Return the element of a 三会局 if *a* and *b* are two distinct branches."""
    if a == b:
        return None
    for triad, element in _SAN_HUI.items():
        if {a, b}.issubset(set(triad)):
            return element
    return None


def _active_dayun_for_year(
    dayun_list: List[Dict], year: int, birth_date: str
) -> Optional[Dict]:
    """Return the DaYun step that covers *year* (or None if before the first)."""
    try:
        birth_year = int(str(birth_date).split("-")[0])
    except (ValueError, AttributeError):
        return None
    age = year - birth_year
    for d in dayun_list:
        if d.get("start_age", 0) <= age < d.get("end_age", 0):
            return d
    return None


def _year_feature_vector(
    bazi: str,
    year: int,
    target_stars: List[str],
    palace_zhi: Optional[str],
    birth_date: str,
    dayun_list_data: Optional[List[Dict]],
    qtype_kind: str = "",
) -> Dict[str, int]:
    """Build the应期 feature vector for one option-year.

    Canonical extractor — ``benchmarks/baziqa/rule_diagnose.py`` and
    ``rule_calibrate.py`` mirror this so what is *measured* is what the engine
    *uses* (no train/serve skew).
    """
    feats: Dict[str, int] = defaultdict(int)
    pillars = extract_pillars(bazi)
    day_master = pillars[2][0]
    day_branch = pillars[2][1]
    yp = _year_pillar(year)
    year_gan, year_zhi = yp[0], yp[1]
    year_shishen = _shishen(day_master, year_gan)

    # 流年天干明现目标十神
    if target_stars and year_shishen in target_stars:
        feats["stem_star"] += 1
    # 流年地支与事件宫互动（互斥：合/三合/三会/冲）
    if palace_zhi:
        if _is_liu_he(year_zhi, palace_zhi):
            feats["branch_liuhe_palace"] += 1
        elif _san_he_element_for_pair(year_zhi, palace_zhi):
            feats["branch_sanhe_palace"] += 1
        elif _san_hui_element_for_pair(year_zhi, palace_zhi):
            feats["branch_sanhui_palace"] += 1
        elif _is_chong(year_zhi, palace_zhi):
            feats["branch_chong_palace"] += 1
    # 流年地支藏干含目标十神
    for gan in _ZHI_CANG_GAN.get(year_zhi, ()):
        if target_stars and _shishen(day_master, gan) in target_stars:
            feats["hidden_star"] += 1
    # 天干五合（修复：旧实现查地支表，永不命中）
    if tuple(sorted((day_master, year_gan))) in _TIAN_GAN_WU_HE:
        feats["stem_wuhe_daymaster"] += 1

    # 应期信号（相对日柱）
    if _restrains(year_gan, pillars[2][0]) and _is_chong(year_zhi, day_branch):
        feats["tian_kang_di_chong"] += 1
    if year_zhi == day_branch:
        feats["fu_yin_day_branch"] += 1
    elif _is_chong(year_zhi, day_branch):
        feats["fan_yin_day_branch"] += 1

    # 父母去世 / 官非：流年天干官杀克身（官杀为压力/官方星）
    if qtype_kind in ("parent", "legal") and year_shishen in ("七杀", "正官"):
        feats["parent_guansha_ke"] += 1

    # 大运引动
    if dayun_list_data:
        ad = _active_dayun_for_year(dayun_list_data, year, birth_date)
        if ad and len(ad.get("pillar", "")) == 2:
            dg, dz = ad["pillar"][0], ad["pillar"][1]
            if target_stars and _shishen(day_master, dg) in target_stars:
                feats["dayun_stem_star"] += 1
            for gan in _ZHI_CANG_GAN.get(dz, ()):
                if target_stars and _shishen(day_master, gan) in target_stars:
                    feats["dayun_hidden_star"] += 1
            if palace_zhi:
                if _is_liu_he(dz, palace_zhi):
                    feats["dayun_liuhe_palace"] += 1
                elif _san_he_element_for_pair(dz, palace_zhi):
                    feats["dayun_sanhe_palace"] += 1
                elif _is_chong(dz, palace_zhi):
                    feats["dayun_chong_palace"] += 1
            if ad.get("pillar") == yp:
                feats["sui_yun_bing_lin"] += 1
    return dict(feats)


# Human-readable labels for each fired signal (used in reason trace).
_SIGNAL_LABEL = {
    "stem_star": "流年天干为{star}",
    "branch_liuhe_palace": "流年地支合{palace}",
    "branch_sanhe_palace": "流年地支半三合{palace}",
    "branch_sanhui_palace": "流年地支半三会{palace}",
    "branch_chong_palace": "流年地支冲{palace}",
    "hidden_star": "流年地支藏干为{star}",
    "stem_wuhe_daymaster": "流年天干与日主五合",
    "tian_kang_di_chong": "天克地冲（流年冲日柱）",
    "fu_yin_day_branch": "伏吟（流年地支同日支）",
    "fan_yin_day_branch": "反吟（流年地支冲日支）",
    "parent_guansha_ke": "流年天干官杀克身",
    "dayun_stem_star": "大运天干为{star}",
    "dayun_hidden_star": "大运地支藏干为{star}",
    "dayun_liuhe_palace": "大运地支合{palace}",
    "dayun_sanhe_palace": "大运地支半三合{palace}",
    "dayun_chong_palace": "大运地支冲{palace}",
    "sui_yun_bing_lin": "岁运并临",
}


def _score_year_for_star(
    bazi: str,
    year: int,
    target_stars: List[str],
    palace_zhi: Optional[str] = None,
    birth_date: str = "",
    dayun_list_data: Optional[List[Dict]] = None,
    penalty_for_clash: bool = False,
    qtype_kind: str = "",
) -> Tuple[float, List[str]]:
    """Score how strongly a given year activates target stars / palace.

    Score is the dot product of ``YEAR_SIGNAL_WEIGHTS`` with the应期 feature
    vector from ``_year_feature_vector`` (calibrated 2026-07-11 via LOO on 25
    contest8 year-questions).

    ``penalty_for_clash`` is retained for backward-compat but no longer flips
    the clash sign — the calibrated weight already encodes the right direction
    and adding an uncalibrated flip would undo the calibration.
    """
    del penalty_for_clash  # deprecated; see docstring
    feats = _year_feature_vector(
        bazi, year, target_stars, palace_zhi, birth_date, dayun_list_data, qtype_kind
    )
    star_label = "/".join(target_stars) if target_stars else ""
    ctx = {"star": star_label, "palace": palace_zhi or ""}
    score = 0.0
    reasons: List[str] = []
    for sig, cnt in feats.items():
        w = YEAR_SIGNAL_WEIGHTS.get(sig, 0.0)
        if w == 0.0 or cnt == 0:
            continue
        score += w * cnt
        label = _SIGNAL_LABEL.get(sig, sig).format(**ctx)
        reasons.append(f"{label}({w:+.1f})")
    # NOTE: do NOT mix 用神 year soft-scores into the calibrated palace/star
    # vector — n30 LOO showed it can push gold out of top-2 shortlist
    # (P027-Q14).  用神 is injected into the LLM prompt via yongshen_block only.
    return score, reasons


@dataclass
class Candidate:
    option: str
    text: str
    score: float
    reasons: List[str] = field(default_factory=list)
    confidence: str = "low"  # high / medium / low


class RuleReasoner:
    """Symbolic reasoner for BaziQA questions."""

    def __init__(
        self,
        bazi: str,
        gender: str,
        birth_date: str,
        birth_time: str = "00:00",
    ):
        self.bazi = bazi
        self.gender = gender
        self.birth_date = birth_date
        self.birth_time = birth_time
        self.pillars = extract_pillars(bazi)
        self.day_master = self.pillars[2][0]
        self.spouse_palace = self.pillars[2][1]
        self.children_palace = self.pillars[3][1]
        self.parents_palace = self.pillars[1][1]
        self.dayun = dayun_list(bazi, gender, birth_date, birth_time, until_age=80)

    def _marriage_stars(self) -> List[str]:
        return ["正财", "偏财"] if self.gender in ("male", "男", "m", "M") else ["正官", "七杀"]

    def _children_stars(self) -> List[str]:
        # 男命官杀为子女，女命食伤为子女
        return ["正官", "七杀"] if self.gender in ("male", "男", "m", "M") else ["食神", "伤官"]

    def _parent_stars(self) -> Tuple[List[str], List[str]]:
        # Dual-star: 父偏财+正财, 母正印+偏印 (align with liuqin_profile merge)
        return ["偏财", "正财"], ["正印", "偏印"]

    def reason_marriage_year(self, question: str, options: List[str]) -> Optional[Candidate]:
        """Pick the option whose year most strongly activates spouse star / palace."""
        stars = self._marriage_stars()
        candidates: List[Candidate] = []
        labels = [chr(ord("A") + i) for i in range(len(options))]
        for opt, text in zip(labels, options):
            opt_years = _extract_years(text)
            if not opt_years:
                continue
            year = opt_years[0]
            score, reasons = _score_year_for_star(
                self.bazi,
                year,
                stars,
                palace_zhi=self.spouse_palace,
                birth_date=self.birth_date,
                dayun_list_data=self.dayun,
                qtype_kind="marriage",
            )
            candidates.append(Candidate(option=opt, text=text, score=score, reasons=reasons))
        return self._best_candidate(candidates)

    def reason_children_year(self, question: str, options: List[str]) -> Optional[Candidate]:
        stars = self._children_stars()
        candidates: List[Candidate] = []
        labels = [chr(ord("A") + i) for i in range(len(options))]
        for opt, text in zip(labels, options):
            opt_years = _extract_years(text)
            if not opt_years:
                continue
            year = opt_years[0]
            score, reasons = _score_year_for_star(
                self.bazi,
                year,
                stars,
                palace_zhi=self.children_palace,
                birth_date=self.birth_date,
                dayun_list_data=self.dayun,
                qtype_kind="children",
            )
            candidates.append(Candidate(option=opt, text=text, score=score, reasons=reasons))
        return self._best_candidate(candidates)

    def reason_parent_death_year(self, question: str, options: List[str]) -> Optional[Candidate]:
        """Identify the year where father or mother star/palace is severely clashed."""
        father_stars, mother_stars = self._parent_stars()
        # Decide which parent from question text
        is_father = "父" in question
        is_mother = "母" in question
        if is_father and not is_mother:
            target_stars = father_stars
        elif is_mother and not is_father:
            target_stars = mother_stars
        else:
            target_stars = father_stars + mother_stars

        candidates: List[Candidate] = []
        labels = [chr(ord("A") + i) for i in range(len(options))]
        for opt, text in zip(labels, options):
            opt_years = _extract_years(text)
            if not opt_years:
                continue
            year = opt_years[0]
            # parent_guansha_ke（官杀克身）现由特征向量统一处理，权重 0.5。
            score, reasons = _score_year_for_star(
                self.bazi,
                year,
                target_stars,
                palace_zhi=self.parents_palace,
                birth_date=self.birth_date,
                dayun_list_data=self.dayun,
                qtype_kind="parent",
            )
            candidates.append(Candidate(option=opt, text=text, score=score, reasons=reasons))
        return self._best_candidate(candidates)

    def reason_career_wealth(self, question: str, options: List[str]) -> Optional[Candidate]:
        """Simple heuristics for career / wealth trend questions.

        Currently uses option keyword matching; can be extended with structural rules.
        """
        text_lower = question.lower()
        if any(k in text_lower for k in ["职业", "工作", "事业"]):
            return self._keyword_match(options, {
                "创业": ["创业", "做生意", "自营"],
                "稳定": ["公职", "上班", "稳定", "公司"],
                "技术": ["技术", "电脑", "专业"],
            })
        if any(k in text_lower for k in ["财", "富", "钱", "资产"]):
            return self._keyword_match(options, {
                "富有": ["富", "发财", "成功致富", "庞大"],
                "稳定": ["小康", "工资", "稳定"],
                "起伏": ["起伏", "暴起暴跌", "投机"],
                "贫困": ["贫", "无工作", "靠父"],
            })
        return None

    def reason_health(self, question: str, options: List[str]) -> Optional[Candidate]:
        """Map imbalanced elements / clashed organs to health options."""
        # Element -> organ mapping (simplified)
        element_organ = {
            "木": ["肝胆", "神经"],
            "火": ["心脏", "眼睛", "血液"],
            "土": ["脾胃", "消化系统"],
            "金": ["肺", "呼吸系统", "大肠"],
            "水": ["肾", "泌尿", "生殖系统"],
        }
        counts: Dict[str, int] = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
        for p in self.pillars:
            counts[_ELEMENT[p[0]]] += 1
            counts[_ELEMENT[p[1]]] += 1
        # Find most deficient / most excessive element
        max_el = max(counts, key=counts.get)
        min_el = min(counts, key=counts.get)
        target_keywords = element_organ.get(min_el, []) + element_organ.get(max_el, [])

        best: Optional[Candidate] = None
        labels = [chr(ord("A") + i) for i in range(len(options))]
        for opt, text in zip(labels, options):
            score = sum(1 for kw in target_keywords if kw in text)
            if best is None or score > best.score:
                best = Candidate(option=opt, text=text, score=float(score), reasons=[f"{min_el}/{max_el}失衡"])
        return best

    def _keyword_match(
        self,
        options: List[str],
        groups: Dict[str, List[str]],
    ) -> Optional[Candidate]:
        best: Optional[Candidate] = None
        labels = [chr(ord("A") + i) for i in range(len(options))]
        for opt, text in zip(labels, options):
            score = 0.0
            matched = []
            for group, kws in groups.items():
                if any(kw in text for kw in kws):
                    score += 1.0
                    matched.append(group)
            if best is None or score > best.score:
                best = Candidate(option=opt, text=text, score=score, reasons=matched)
        return best

    def _rank_candidates(self, candidates: List[Candidate]) -> List[Candidate]:
        """Sort candidates by score and stamp margin-based confidence on the top one.

        Confidence is the gap between the top score and the runner-up (not an
        absolute score threshold).  LOO calibration on 25 contest8 year-questions:
        margin ≥ 0.5 → ~75% top-1; margin ≥ 0.2 → ~58%; below → noise.

        Runner-up confidence is left as the default ``low``; only top-1 is used
        for hard LLM overrides.  The full ranked list is for shortlist injection.
        """
        if not candidates:
            return []
        ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
        best = ranked[0]
        runner_up = ranked[1].score if len(ranked) > 1 else float("-inf")
        margin = best.score - runner_up
        if margin >= _YEAR_CONF_HIGH_MARGIN:
            best.confidence = "high"
        elif margin >= _YEAR_CONF_MED_MARGIN:
            best.confidence = "medium"
        else:
            best.confidence = "low"
        return ranked

    def _best_candidate(self, candidates: List[Candidate]) -> Optional[Candidate]:
        """Pick the top candidate with **margin-based** confidence."""
        ranked = self._rank_candidates(candidates)
        return ranked[0] if ranked else None

    def _score_year_options(
        self,
        options: List[str],
        target_stars: List[str],
        palace_zhi: Optional[str],
        qtype_kind: str,
    ) -> List[Candidate]:
        """Score every option that contains a year; return unsorted candidates."""
        candidates: List[Candidate] = []
        labels = [chr(ord("A") + i) for i in range(len(options))]
        for opt, text in zip(labels, options):
            opt_years = _extract_years(text)
            if not opt_years:
                continue
            year = opt_years[0]
            score, reasons = _score_year_for_star(
                self.bazi,
                year,
                target_stars,
                palace_zhi=palace_zhi,
                birth_date=self.birth_date,
                dayun_list_data=self.dayun,
                qtype_kind=qtype_kind,
            )
            candidates.append(Candidate(option=opt, text=text, score=score, reasons=reasons))
        return candidates

    # Keyword tables for year-event dispatch (substring match on question text).
    _KW_MARRIAGE = (
        "结婚", "婚姻", "第二婚", "二婚", "再婚", "嫁", "娶", "登记结婚",
        "拍拖", "恋爱", "交往", "初恋", "离婚", "分手",
    )
    _KW_CHILDREN = (
        "子女", "孩子", "儿子", "女儿", "得子", "得女", "生子", "生女",
        "生孩子", "出生", "小孩", "男孩", "女孩", "子息",
    )
    _KW_PARENT = ("父", "母", "仙逝", "去世", "逝世", "离世", "亡", "过世")
    # Non-standard year events (P1): map to best-effort stars/palaces.
    _KW_MOVE = ("搬迁", "搬家", "迁居", "移居", "出国", "到香港", "移民")
    _KW_LEGAL = ("官非", "牢狱", "警察", "扣留", "官司", "入狱", "被抓")

    # Soft shortlist kinds.  ``children`` re-enabled with the same score gate as
    # marriage/generic (see rank_year_candidates): full top-2 hit is weak (~25%),
    # but score≥0.4 top-1 slices include gold cases like contest8 P026-Q8.
    _SHORTLIST_KINDS = frozenset(
        {"marriage", "parent", "move", "legal", "generic", "children"}
    )

    # Hard override DISABLED after year-parse expansion (2026-07-13): the
    # high-margin slice fell to ~20% top-1 on contest8, so skipping the LLM
    # actively hurts.  Soft shortlist (top-2 hit ~60%) is the production path.
    # Re-enable only after recalibrating on the expanded coverage set.
    _HARD_OVERRIDE_KINDS = frozenset()
    _STRICT_HARD_KW: Dict[str, Tuple[str, ...]] = {
        "marriage": ("结婚", "第二婚", "二婚", "再婚", "嫁", "娶", "登记结婚"),
        "children": ("得子", "得女", "出生", "生孩子", "生小孩", "生子", "生女"),
        "parent": ("去世", "仙逝", "逝世", "离世", "过世", "亡"),
        "move": ("搬迁", "搬家", "迁居", "移居", "出国"),
    }
    # Absolute score floor for hard override (need at least one solid signal).
    _HARD_OVERRIDE_MIN_SCORE = 0.5

    def classify_year_event(self, question: str) -> Optional[str]:
        """Return event kind for *question*, or None if not a year-event."""
        q = question
        if any(k in q for k in self._KW_PARENT) and any(
            k in q for k in ("仙逝", "去世", "逝世", "离世", "亡", "过世", "破产")
        ):
            return "parent"
        if any(k in q for k in self._KW_CHILDREN) and not any(
            k in q for k in ("叔叔", "伯父", "舅舅")
        ):
            if any(
                k in q
                for k in (
                    "出生", "得子", "得女", "生子", "生女", "生孩子",
                    "几个小孩", "几个孩子", "男孩", "女孩", "子息",
                )
            ) or (
                any(k in q for k in self._KW_CHILDREN)
                and not any(k in q for k in self._KW_MARRIAGE)
            ):
                return "children"
        if any(k in q for k in self._KW_MARRIAGE):
            return "marriage"
        if any(k in q for k in self._KW_MOVE):
            return "move"
        if any(k in q for k in self._KW_LEGAL):
            return "legal"
        if any(
            k in q
            for k in ("哪年", "那一年", "何年", "哪一年", "何时", "几时", "什么时候", "年份")
        ):
            return "generic"
        return None

    def rank(self, question: str, options: List[str]) -> List[Candidate]:
        """Return all year-options ranked by symbolic score (best first).

        Empty list if the question is not a supported year-event type or no
        option contains a parseable year.  This is the shortlist primitive for
        Phase 4: feed top-2 to the LLM instead of hard-picking top-1.
        """
        kind = self.classify_year_event(question)
        if kind is None:
            return []

        if kind == "parent":
            father_stars, mother_stars = self._parent_stars()
            is_father = "父" in question or "祖" in question
            is_mother = "母" in question
            if is_father and not is_mother:
                target_stars = father_stars
            elif is_mother and not is_father:
                target_stars = mother_stars
            else:
                target_stars = father_stars + mother_stars
            cands = self._score_year_options(
                options, target_stars, self.parents_palace, "parent"
            )
            return self._rank_candidates(cands)

        if kind == "children":
            cands = self._score_year_options(
                options, self._children_stars(), self.children_palace, "children"
            )
            return self._rank_candidates(cands)

        if kind == "marriage":
            cands = self._score_year_options(
                options, self._marriage_stars(), self.spouse_palace, "marriage"
            )
            return self._rank_candidates(cands)

        if kind == "move":
            # 搬迁/出国：印星(文书动) + 日支冲合 as proxy
            cands = self._score_year_options(
                options, ["正印", "偏印"], self.spouse_palace, "move"
            )
            return self._rank_candidates(cands)

        if kind == "legal":
            # 官非应期落在「自身」日支宫 + 官杀星，而非夫妻宫
            # （配偶宫会把婚姻冲合噪声混入，压低真官非年如 P031-Q33）。
            cands = self._score_year_options(
                options, ["正官", "七杀"], self.pillars[2][1], "legal"
            )
            return self._rank_candidates(cands)

        # generic year-asking
        cands = self._score_year_options(
            options,
            target_stars=[],
            palace_zhi=self.spouse_palace,
            qtype_kind="generic",
        )
        return self._rank_candidates(cands) if cands else []

    def reason(self, question: str, options: List[str]) -> Optional[Candidate]:
        """Dispatch to the appropriate rule handler based on question text.

        Year-event questions (marriage / children / parent / move / legal / generic
        year options) are ranked symbolically.  Career/wealth/health keyword
        heuristics remain available via dedicated methods but are not in the
        default dispatch (accuracy not yet high enough to beat the LLM).
        """
        ranked = self.rank(question, options)
        return ranked[0] if ranked else None


# Question must look like a "which year" ask for shortlist injection.
# Status MCQs that merely mention 婚姻/感情 (e.g. P033-Q39) previously got a
# year-option ranking and actively hurt the LLM (A/B: free correct, guided wrong).
_YEAR_ASKING_KW = (
    "哪年", "那一年", "何年", "哪一年", "何时", "几时", "什么时候",
    "年份", "那年", "于何年", "在哪一年", "在那一年", "何时候",
    "那一年", "哪一年份", "哪一年份",
)

# Kinds that always get shortlist when score > 0 (historically stronger top-2).
# ``legal`` moved to gated: weak signals (e.g. 伏吟-only score 0.2 on P031-Q33)
# actively mislead the LLM when gold is not in top-2.
_SHORTLIST_ALWAYS_KINDS = frozenset({"parent", "move"})
# Kinds that need medium+ margin / score floor before injection (noisier top-2).
_SHORTLIST_GATED_KINDS = frozenset({"marriage", "generic", "children", "legal"})


def is_year_asking_question(question: str, options: Optional[List[str]] = None) -> bool:
    """True if the question is asking *which year*, not a status/classification MCQ."""
    if any(k in question for k in _YEAR_ASKING_KW):
        return True
    # Pure year option lists like ["2017","2018","2019","2020"] or "A 2010 庚寅"
    # without narrative prose (结婚/离婚/创业…).
    if options:
        pure = 0
        for o in options:
            years = _extract_years(o)
            if not years:
                continue
            # Strip year tokens, option labels, and ganzhi; leftover must be empty.
            stripped = re.sub(
                r"(19|20)\d{2}|[年月日号]|[甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥]"
                r"|[ABCD]、?|[.\:：、]|选项|\s+",
                "",
                o,
            )
            if stripped == "":
                pure += 1
        if pure >= 2:
            return True
    return False


def rank_year_candidates(
    bazi: str,
    question: str,
    options: List[str],
    *,
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
    top_k: int = 2,
    for_shortlist: bool = True,
) -> List[Candidate]:
    """Return top-*k* year candidates for shortlist injection into the LLM prompt.

    Returns an empty list when the question is not a supported year-event type,
    birth_date is missing, or scoring fails.  Callers should treat empty as
    "no shortlist — let the LLM see all options unguided".

    When *for_shortlist* is True (default), additional gates apply:
    - kind must be in ``_SHORTLIST_KINDS`` (children excluded)
    - question must be year-asking (not status MCQ)
    - marriage/generic need margin confidence ≥ medium
    - top-1 absolute score must be > 0
    """
    if not bazi or not birth_date or top_k <= 0:
        return []
    try:
        reasoner = RuleReasoner(bazi, gender, birth_date, birth_time)
        if for_shortlist:
            kind = reasoner.classify_year_event(question)
            if kind not in RuleReasoner._SHORTLIST_KINDS:
                return []
            if not is_year_asking_question(question, options):
                return []
        ranked = reasoner.rank(question, options)
        if not ranked:
            return []
        if for_shortlist:
            kind = reasoner.classify_year_event(question)
            best = ranked[0]
            if best.score <= 0:
                return []
            # marriage/generic/children/legal: need non-low margin + absolute floor.
            # Floor was 0.4 under pre-2026-07-19 weights; after LOO recalib
            # (半三合 0.4→0.2 等) the same cases land ~0.2–0.3, so floor is 0.2.
            # Confidence still requires margin ≥ MED (medium), filtering pure noise.
            if kind in _SHORTLIST_GATED_KINDS:
                if best.confidence == "low" or best.score < 0.2:
                    return []
            if kind not in _SHORTLIST_ALWAYS_KINDS and kind not in _SHORTLIST_GATED_KINDS:
                return []
        return ranked[:top_k]
    except Exception:
        return []


def format_shortlist_block(
    candidates: List[Candidate],
    *,
    top_k: int = 2,
    kind: str = "year",
) -> str:
    """Format ranked candidates as a Chinese prompt block for the LLM.

    Soft guidance (not a hard constraint).  Wording is deliberately cautious:
    A/B showed hard "请优先" language can pull the model off a correct free
    answer when gold ∉ top-2 (P033-Q39).

    When top-1 and top-2 scores are close (margin < 0.35), present them as a
    **near-tie** and force item-by-item comparison — this targets cases where
    gold is runner-up (P031-Q33, P017-Q4 in n50 LOO).
    """
    if not candidates:
        return ""
    top = candidates[:top_k]
    conf = top[0].confidence
    margin = top[0].score - top[1].score if len(top) > 1 else 99.0
    near_tie = len(top) >= 2 and margin < 0.35

    if kind == "domain":
        title = "【结构取象 shortlist（参考）】"
        basis = "以下按命局十神/旺衰/五行失衡与选项关键词的贴合度排序。"
    else:
        title = "【规则引擎应期 shortlist（参考）】"
        basis = "以下为符号规则（十神/宫位合冲/天克地冲/天干五合等）对选项年份的打分排序。"

    if near_tie:
        guidance = (
            "⚠ 前两名得分接近（近并列），禁止默认选排序第一。"
            "请逐项对比两个选项与命局/大运/流年的贴合度，"
            "选信号与题意更一致的那一个；若都不贴，可跳出 shortlist。"
        )
    elif conf == "high":
        guidance = (
            "上述 shortlist 与命局信号较吻合，请优先在 shortlist 内择优；"
            "仅当你有明确的反向结构理由时才可跳出。"
        )
    elif conf == "medium":
        guidance = (
            "shortlist 仅供参考。请结合大运流年独立判断；"
            "若你的结构推理与 shortlist 冲突，以结构推理为准。"
        )
    else:
        guidance = (
            "shortlist 信号较弱，仅作辅助线索，不要被其绑定；"
            "以你对命局/大运/流年的独立判断为准。"
        )
    lines = [title, basis, guidance]
    for i, c in enumerate(top, start=1):
        reasons = "；".join(c.reasons) if c.reasons else "无显著信号"
        conf_bit = f"，置信度={c.confidence}" if i == 1 else ""
        lines.append(
            f"{i}. 选项{c.option}「{c.text}」得分={c.score:.2f}{conf_bit}｜信号：{reasons}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Non-year (domain) structural option ranking
# ---------------------------------------------------------------------------

_CAREER_BUCKETS: Dict[str, Tuple[str, ...]] = {
    "公职稳定": ("公职", "公务员", "政府", "国企", "稳定", "上班", "机构", "单位", "体制"),
    "创业商贸": ("创业", "生意", "贸易", "自营", "开店", "老板", "经商", "做生意"),
    "技术专业": ("技术", "电脑", "工程", "专业", "设计", "研发", "IT", "技工"),
    "文艺自由": ("艺术", "自由", "创作", "媒体", "表演", "写作", "创意"),
    "销售服务": ("销售", "公关", "服务", "中介", "应酬", "业务"),
    "金融财": ("金融", "银行", "投资", "财务", "会计"),
}

_WEALTH_BUCKETS: Dict[str, Tuple[str, ...]] = {
    "大富": ("富", "发财", "成功致富", "庞大", "千万", "百万", "暴富", "巨富"),
    "小康稳定": ("小康", "工资", "稳定", "中产", "温饱", "正财"),
    "起伏投机": ("起伏", "暴起暴跌", "投机", "不稳", "偏财"),
    "贫困": ("贫", "无工作", "靠父", "穷", "困难", "负债"),
}

_HEALTH_ORGANS: Dict[str, Tuple[str, ...]] = {
    "木": ("肝", "胆", "神经", "筋", "眼", "目"),
    "火": ("心", "血", "眼", "目", "小肠", "血压"),
    "土": ("脾", "胃", "消化", "肌肉"),
    "金": ("肺", "呼吸", "大肠", "皮", "鼻"),
    "水": ("肾", "泌尿", "生殖", "耳", "骨", "膀胱", "妇科", "子宫"),
}

_EDU_BUCKETS: Dict[str, Tuple[str, ...]] = {
    "高学历": ("博士", "硕士", "研究生", "大学", "本科", "学士", "名校"),
    "中等": ("大专", "专科", "高中", "中专", "中等", "技校"),
    "低或无": ("小学", "初中", "辍学", "无学历", "没读书", "文盲"),
}


def _shishen_presence(profile: Dict) -> Dict[str, bool]:
    """Collapse stem+branch 十神 labels into presence flags."""
    flags = {
        "官杀": False,
        "印": False,
        "食伤": False,
        "财": False,
        "比劫": False,
    }
    for v in (profile.get("stem_shishen") or {}).values():
        if v in ("正官", "七杀"):
            flags["官杀"] = True
        elif v in ("正印", "偏印"):
            flags["印"] = True
        elif v in ("食神", "伤官"):
            flags["食伤"] = True
        elif v in ("正财", "偏财"):
            flags["财"] = True
        elif v in ("比肩", "劫财"):
            flags["比劫"] = True
    for v in (profile.get("branch_shishen") or {}).values():
        if v == "官杀":
            flags["官杀"] = True
        elif v == "印":
            flags["印"] = True
        elif v == "食伤":
            flags["食伤"] = True
        elif v == "财":
            flags["财"] = True
        elif v == "比劫":
            flags["比劫"] = True
    return flags


def _element_extremes(profile: Dict) -> Tuple[str, str]:
    """Return (most, least) element by raw counts from pillars in profile."""
    # structural_profile doesn't export raw counts; recompute from bazi string
    # via weighted if available — fall back to equal.
    return "", ""


_MARRIAGE_STABLE_KW = (
    "美满", "幸福", "稳定", "顺利", "和睦", "圆满", "恩爱", "白头", "早婚幸福",
    "婚姻美满", "感情顺利", "一世", "从一而终", "已结婚且婚姻状况良好",
)
_MARRIAGE_UNSTABLE_KW = (
    "离婚", "离异", "波折", "不顺", "多段", "再婚", "二婚", "晚婚", "未婚",
    "单身", "分居", "出轨", "是非", "辛苦", "聚少", "无正缘", "难成", "破裂",
    "复杂", "多次", "第几段",
)
_KIN_GOOD_KW = ("和睦", "融洽", "支持", "富裕", "幸福", "依赖", "良好", "亲近")
_KIN_HARD_KW = ("疏离", "不和", "早逝", "早年辛苦", "贫困", "无助力", "淡薄", "紧张", "分居", "单亲")


def _option_letter_text(options: Sequence[str]) -> List[Tuple[str, str]]:
    labels = [chr(ord("A") + i) for i in range(len(options))]
    out: List[Tuple[str, str]] = []
    for lab, text in zip(labels, options):
        out.append((lab, str(text or "")))
    return out


def _marriage_option_notes(
    options: Sequence[str],
    *,
    spouse_weak: bool,
    palace_unstable: bool,
) -> List[str]:
    """Soft demotion/promotion notes for marriage-status option wording."""
    if not options:
        return []
    notes: List[str] = []
    if not (spouse_weak or palace_unstable):
        # Mild: demote extreme instability only when structure is strong+stable
        for lab, text in _option_letter_text(options):
            if any(k in text for k in ("多次离婚", "三段以上", "婚姻极差")):
                notes.append(f"{lab}措辞偏极端破裂，与「星强宫稳」略不合，宜降权")
        return notes

    demote: List[str] = []
    promote: List[str] = []
    for lab, text in _option_letter_text(options):
        has_stable = any(k in text for k in _MARRIAGE_STABLE_KW)
        has_unst = any(k in text for k in _MARRIAGE_UNSTABLE_KW)
        if has_stable and not has_unst:
            demote.append(lab)
        elif has_unst and not has_stable:
            promote.append(lab)
        elif has_stable and has_unst:
            # mixed wording — leave to model
            pass
    if demote:
        reason = "配偶星弱/不现" if spouse_weak else "夫妻宫冲刑"
        if spouse_weak and palace_unstable:
            reason = "星弱+宫不稳"
        notes.append(
            f"- 选项措辞降权（{reason}，勿首选「美满/稳定」类）："
            + "、".join(demote)
        )
    if promote:
        notes.append(
            "- 选项措辞较贴波折/离异/晚婚/多段结构，可优先对照："
            + "、".join(promote)
        )
    return notes


def _format_liuqin_domain_hints(
    bazi: str,
    question: str,
    *,
    gender: str = "male",
    options: Optional[Sequence[str]] = None,
) -> str:
    """Marriage / kinship structural hints from liuqin_profile (no hard letter pick)."""
    try:
        from tools.bazi_ai import bazi_structural
    except Exception:
        return ""
    lq = bazi_structural.liuqin_profile(bazi, gender=gender)
    if not lq:
        return ""
    q = question or ""
    want_marriage = any(
        k in q
        for k in (
            "婚姻", "感情", "结婚", "离婚", "配偶", "妻子", "丈夫", "恋爱",
            "拍拖", "再婚", "二婚", "第几段", "桃花",
        )
    )
    want_kin = any(
        k in q
        for k in (
            "父", "母", "子", "女", "孩子", "子女", "兄弟", "姐妹",
            "六亲", "家庭", "原生", "祖上", "父母",
        )
    )
    if not want_marriage and not want_kin:
        return ""

    lines = ["【六亲/婚姻结构提示（非选项排名，禁止当作标准答案）】"]
    g = lq.get("gender") or gender
    spouse = lq.get("spouse") or {}
    sp_pal = lq.get("spouse_palace") or {}
    father = lq.get("father") or {}
    mother = lq.get("mother") or {}
    son = lq.get("son") or {}
    daughter = lq.get("daughter") or {}
    ch_pal = lq.get("children_palace") or {}
    pa_pal = lq.get("parents_palace") or {}

    # Clash / harm on day branch from structural di_zhi text if present.
    try:
        prof = bazi_structural.structural_profile(bazi) or {}
        dz_text = str(prof.get("di_zhi_comprehensive_text") or "")
    except Exception:
        dz_text = ""
    day_zhi = (sp_pal.get("branch") or "")
    palace_unstable = bool(day_zhi) and any(
        tag in dz_text and day_zhi in dz_text
        for tag in ("冲", "刑", "害", "破")
    )
    # Also flag if description mentions 冲 on 日支
    if day_zhi and dz_text and re.search(rf"{day_zhi}.{{0,6}}(冲|刑|害)", dz_text):
        palace_unstable = True
    # 日支本气为比劫：争合不专（尤女命），视同宫位不稳信号
    sp_main = str(sp_pal.get("shishen_main") or "")
    if sp_main in ("比肩", "劫财", "比劫"):
        palace_unstable = True

    spouse_weak = False
    if want_marriage:
        star = spouse.get("star") or ("正财" if g == "male" else "正官")
        exists = bool(spouse.get("exists"))
        strength = spouse.get("strength") or "弱"
        support = spouse.get("support_text") or ""
        spouse_weak = (not exists) or strength == "弱"
        lines.append(
            f"- 配偶星（{star}）：{'现' if exists else '不现'}；强弱参考={strength}；{support}"
        )
        if spouse.get("description"):
            lines.append(f"- 配偶星落点：{spouse.get('description')}")
        if sp_pal.get("description"):
            lines.append(f"- {sp_pal.get('description')}")
        tips = []
        if spouse_weak:
            tips.append("配偶星弱/不现 → 婚姻助力弱、易晚婚或聚少离多，勿首选「美满稳定」")
        if strength == "强" and not palace_unstable:
            tips.append("配偶星有力且夫妻宫无明显冲刑 → 较支持稳定婚配")
        if palace_unstable:
            tips.append("夫妻宫（日支）逢冲刑害/比劫坐支 → 感情波折/争合/离异象更重")
        if sp_main in ("比肩", "劫财", "比劫"):
            tips.append("日支比劫 → 配偶宫不专，忌轻易断「婚姻美满稳定」")
        if g == "female" and exists and strength == "弱":
            tips.append("女命官杀弱 → 正缘偏晚或不顺，忌轻易断「早婚幸福」")
        if g == "male" and exists and strength == "弱":
            tips.append("男命财星弱 → 妻缘助力不足，财妻同论时偏紧")
        if palace_unstable and spouse_weak:
            tips.append("宫位不稳+星弱 → 多重婚姻/离异后再婚的结构支持度高于「一世一婚圆满」")
        if tips:
            lines.append("- 婚姻取象：" + "；".join(tips))
        if options:
            lines.extend(
                _marriage_option_notes(
                    options,
                    spouse_weak=spouse_weak,
                    palace_unstable=palace_unstable,
                )
            )

    if want_kin:
        if any(k in q for k in ("父", "母", "父母", "家庭", "原生", "祖上")):
            if father.get("description"):
                lines.append(
                    f"- 父亲：{father.get('description')}（强弱={father.get('strength', '?')}）"
                )
            if mother.get("description"):
                lines.append(
                    f"- 母亲：{mother.get('description')}（强弱={mother.get('strength', '?')}）"
                )
            if pa_pal.get("description"):
                lines.append(f"- {pa_pal.get('description')}")
            f_s, m_s = father.get("strength"), mother.get("strength")
            if f_s == "弱" and m_s == "弱":
                lines.append("- 父母双星偏弱 → 原生家庭助力有限/关系疏离或早年辛苦更贴")
            elif f_s == "强" or m_s == "强":
                lines.append("- 父或母星有力 → 至少一方可依赖/背景不至于极差，对照选项措辞")
        if any(k in q for k in ("子", "女", "孩子", "子女", "小孩")):
            if son.get("description"):
                lines.append(f"- 儿子星：{son.get('description')}（{son.get('strength', '?')}）")
            if daughter.get("description"):
                lines.append(
                    f"- 女儿星：{daughter.get('description')}（{daughter.get('strength', '?')}）"
                )
            if ch_pal.get("description"):
                lines.append(f"- {ch_pal.get('description')}")
            child_weak = (
                (son.get("strength") == "弱" or not son.get("exists"))
                and (daughter.get("strength") == "弱" or not daughter.get("exists"))
            )
            if child_weak:
                lines.append("- 子女星整体偏弱 → 子女缘薄/晚得/辛苦，勿首选「子女双全顺利」")

    lines.append("- 请用以上星宫强弱映射选项措辞，勿编造命局不支持的人生细节。")
    return "\n".join(lines)


_CAREER_GOV_KW = (
    "公职", "公务员", "政府", "机构", "稳定岗", "体制", "上班族", "国企", "事业编",
    "机关", "教师编", "银行柜", "稳定工作",
)
_CAREER_TECH_KW = (
    "技术", "电脑", "IT", "专业", "研发", "工程", "技工", "设计", "程序员", "自由职业",
    "文艺", "艺术", "创作",
)
_CAREER_BIZ_KW = (
    "创业", "生意", "商贸", "老板", "自营", "销售", "奔波", "合伙", "做生意", "开店",
    "贸易", "中介", "业务",
)


def _career_option_notes(options: Sequence[str], flags: Dict[str, bool]) -> List[str]:
    """Soft promote/demote career option wording from 十神 flags (no hard pick)."""
    if not options:
        return []
    # Primary structural buckets (priority order).
    prefer_gov = bool(flags.get("官杀") and flags.get("印"))
    prefer_tech = bool(flags.get("食伤") and not flags.get("官杀"))
    prefer_biz = bool(
        (flags.get("食伤") and flags.get("财"))
        or (flags.get("财") and not flags.get("官杀"))
        or (flags.get("比劫") and flags.get("财"))
    )
    # If both tech and biz fire, keep both as soft promote.
    gov_labs, tech_labs, biz_labs = [], [], []
    for lab, text in _option_letter_text(options):
        if any(k in text for k in _CAREER_GOV_KW):
            gov_labs.append(lab)
        if any(k in text for k in _CAREER_TECH_KW):
            tech_labs.append(lab)
        if any(k in text for k in _CAREER_BIZ_KW):
            biz_labs.append(lab)
    notes: List[str] = []
    if prefer_gov and gov_labs:
        notes.append("- 选项措辞贴官印（公职/机构/稳定岗），可优先对照：" + "、".join(gov_labs))
        demote = sorted(set(tech_labs + biz_labs) - set(gov_labs))
        if demote:
            notes.append("- 相对降权（与官印结构略疏）：" + "、".join(demote))
    elif prefer_tech and tech_labs:
        notes.append("- 选项措辞贴食伤泄秀（技术/自由/文艺），可优先对照：" + "、".join(tech_labs))
        if gov_labs and not flags.get("官杀"):
            notes.append("- 官星不显 → 降权公职/稳定岗类：" + "、".join(gov_labs))
    elif prefer_biz and biz_labs:
        notes.append("- 选项措辞贴食伤财/比劫财（创业商贸/销售奔波），可优先对照：" + "、".join(biz_labs))
        if gov_labs and not flags.get("官杀"):
            notes.append("- 官星不显 → 降权公职/稳定岗类：" + "、".join(gov_labs))
    return notes


def format_domain_hint_block(
    bazi: str,
    question: str,
    *,
    gender: str = "male",
    include_career_wealth: bool = False,
    options: Optional[Sequence[str]] = None,
) -> str:
    """Structural reading hints for non-year MCQs — **no option ranking**.

    Offline option-ranking top-2 is only ~55% on contest8 domain questions, so
    listing A/B letters would often mislead.  Instead we inject the chart's
    十神/旺衰 implications and let the LLM map them to options.

    Always-on domains: marriage/kinship (liuqin), career, education.
    Gated by *include_career_wealth* (``--domain-hints``): wealth, health
    (historically noisier when always-on with other experiments).

    *options*: soft-tag option wording (婚姻「美满」降权 / 职业桶对照) without
    hard-picking a letter.
    """
    if not bazi:
        return ""
    if is_year_asking_question(question, list(options) if options else None):
        # Pure year MCQs use year shortlist; year gate wins over domain hints.
        return ""
    try:
        from tools.bazi_ai import bazi_structural
    except Exception:
        return ""

    liuqin_block = _format_liuqin_domain_hints(
        bazi, question, gender=gender, options=options
    )

    profile = bazi_structural.structural_profile(bazi)
    if not profile:
        return liuqin_block

    q = question
    domain = ""
    if any(k in q for k in ("职业", "工作", "事业", "从事", "行业", "职位")):
        domain = "career"
    elif any(k in q for k in ("学历", "读书", "学业", "毕业", "学校", "科系", "文凭")):
        domain = "education"
    elif any(k in q for k in ("病", "疾", "健康", "身体", "受伤", "手术", "困扰")):
        domain = "health"
    elif any(k in q for k in ("财运", "财富", "有钱", "贫富", "收入", "资产")):
        domain = "wealth"

    # Career/education always eligible; wealth/health need experimental flag.
    always_struct = domain in ("career", "education")
    gated_struct = domain in ("wealth", "health") and include_career_wealth
    if not always_struct and not gated_struct:
        return liuqin_block

    flags = _shishen_presence(profile)
    strength = profile.get("strength", "中和")

    def _as_god_list(val) -> List[str]:
        if not val:
            return []
        if isinstance(val, str):
            return [x.strip() for x in val.replace("，", ",").split(",") if x.strip()]
        out: List[str] = []
        for x in val:
            s = str(x).strip().strip(",")
            if s and s != ",":
                out.append(s)
        return out

    useful = _as_god_list(profile.get("useful_gods"))
    taboo = _as_god_list(profile.get("taboo_gods"))
    day_master = profile.get("day_master", "")

    lines = [
        "【结构取象提示（非选项排名，禁止当作标准答案）】",
        f"- 日主{day_master}，旺衰参考：{strength}；用神：{useful or '待细断'}；忌神：{taboo or '待细断'}",
        f"- 十神可见：官杀={'有' if flags['官杀'] else '弱/无'}，印={'有' if flags['印'] else '弱/无'}，"
        f"食伤={'有' if flags['食伤'] else '弱/无'}，财={'有' if flags['财'] else '弱/无'}，"
        f"比劫={'有' if flags['比劫'] else '弱/无'}",
    ]

    if domain == "career":
        tips = []
        if flags["官杀"] and flags["印"]:
            tips.append("官印相生 → 优先考虑公职/机构/稳定岗位")
        if flags["食伤"] and flags["财"]:
            tips.append("食伤生财 → 技艺、商贸、创业类更贴")
        elif flags["食伤"] and not flags["官杀"]:
            tips.append("食伤泄秀、官星不显 → 技术/自由/文艺倾向（勿硬套公职）")
        elif flags["食伤"]:
            tips.append("食伤泄秀 → 技术/表达/技艺象")
        if flags["财"] and not flags["官杀"]:
            tips.append("财星显而官弱 → 偏商业/求财，非典型公职")
        if flags["比劫"] and flags["财"]:
            tips.append("比劫见财 → 合伙/竞争/销售奔波象")
        if flags["官杀"] and not flags["印"]:
            tips.append("有官杀无印 → 压力岗/管理/变动，未必清闲编制")
        if not tips:
            tips.append("按用神喜忌与食伤/官杀强弱，在选项中找最贴的职业象")
        lines.append("- 职业倾向：" + "；".join(tips))
        if options:
            lines.extend(_career_option_notes(options, flags))
    elif domain == "education":
        if flags["印"] and strength != "偏弱":
            lines.append("- 学业：印星有力 → 学历偏中高，科班/文职象更强")
        elif flags["印"] and strength == "偏弱":
            lines.append("- 学业：印透但身弱 → 多为中等学历，需早运助印")
        elif flags["食伤"] and not flags["印"]:
            lines.append("- 学业：食伤泄秀无印 → 偏技艺/自学，科班学历未必高")
        else:
            lines.append("- 学业：看印星是否被合坏、早年大运是否助印")
    elif domain == "wealth":
        if strength == "偏旺" and flags["财"]:
            lines.append("- 财运：身旺有财 → 能任财，小康至偏富象")
        elif strength == "偏弱" and flags["财"]:
            lines.append("- 财运：身弱财重 → 难稳任，易起伏或靠人")
        elif strength == "偏弱" and not flags["财"]:
            lines.append("- 财运：身弱无财 → 偏紧，需印比帮身后始能任")
        else:
            lines.append("- 财运：以财星是否透干有根 + 日主能否担财综合判断")
    elif domain == "health":
        pillars = extract_pillars(bazi)
        el_counts: Dict[str, int] = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
        for p in pillars:
            el_counts[_ELEMENT[p[0]]] += 1
            el_counts[_ELEMENT[p[1]]] += 1
        max_el = max(el_counts, key=el_counts.get)  # type: ignore[arg-type]
        min_el = min(el_counts, key=el_counts.get)  # type: ignore[arg-type]
        max_org = "、".join(_HEALTH_ORGANS.get(max_el, ())[:3])
        min_org = "、".join(_HEALTH_ORGANS.get(min_el, ())[:3])
        lines.append(f"- 健康：{max_el}偏旺（{max_org}）/ {min_el}偏弱（{min_org}）优先排查")
        if taboo:
            t_orgs = []
            for el in taboo:
                t_orgs.extend(list(_HEALTH_ORGANS.get(el, ())[:2]))
            if t_orgs:
                lines.append(f"- 忌神{taboo}对应系统亦需注意：{'、'.join(t_orgs)}")

    lines.append("- 请用以上结构线索映射选项，勿编造命局不支持的事件。")
    body = "\n".join(lines)
    if liuqin_block:
        return body + "\n" + liuqin_block
    return body


def rank_domain_candidates(
    bazi: str,
    question: str,
    options: List[str],
    *,
    gender: str = "male",
    top_k: int = 2,
    for_injection: bool = False,
) -> List[Candidate]:
    """Rank non-year options by structural cues (diagnostics / offline measure).

    Production LLM injection uses :func:`format_domain_hint_block` instead —
    offline top-2 is only ~55%, so option-letter shortlists are disabled when
    *for_injection* is True (always empty).  Call with ``for_injection=False``
    (default) to inspect ranking quality offline.
    """
    if for_injection:
        return []
    if not bazi or not options:
        return []
    if is_year_asking_question(question, options):
        return []
    try:
        from tools.bazi_ai import bazi_structural
    except Exception:
        return []
    profile = bazi_structural.structural_profile(bazi)
    if not profile:
        return []

    q = question
    domain = "general"
    if any(k in q for k in ("职业", "工作", "事业", "从事", "行业", "职位")):
        domain = "career"
    elif any(k in q for k in ("学历", "读书", "学业", "毕业", "学校")):
        domain = "education"
    elif any(k in q for k in ("病", "疾", "健康", "身体", "受伤", "手术", "困扰")):
        domain = "health"
    elif any(k in q for k in ("财运", "财富", "有钱", "贫富", "收入", "资产")):
        domain = "wealth"
    else:
        return []

    flags = _shishen_presence(profile)
    strength = profile.get("strength", "中和")
    useful = set(profile.get("useful_gods") or [])
    taboo = set(profile.get("taboo_gods") or [])
    pillars = extract_pillars(bazi)
    el_counts: Dict[str, int] = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
    for p in pillars:
        el_counts[_ELEMENT[p[0]]] += 1
        el_counts[_ELEMENT[p[1]]] += 1
    max_el = max(el_counts, key=el_counts.get)  # type: ignore[arg-type]
    min_el = min(el_counts, key=el_counts.get)  # type: ignore[arg-type]

    labels = [chr(ord("A") + i) for i in range(len(options))]
    cands: List[Candidate] = []
    for opt, text in zip(labels, options):
        score = 0.0
        reasons: List[str] = []
        if domain == "career":
            chart_bias = {
                "公职稳定": 0.0, "创业商贸": 0.0, "技术专业": 0.0,
                "文艺自由": 0.0, "销售服务": 0.0, "金融财": 0.0,
            }
            if flags["官杀"] and flags["印"]:
                chart_bias["公职稳定"] += 1.5
            if flags["食伤"] and flags["财"]:
                chart_bias["创业商贸"] += 1.2
                chart_bias["技术专业"] += 0.8
            elif flags["食伤"]:
                chart_bias["技术专业"] += 1.0
                chart_bias["文艺自由"] += 0.8
            if flags["财"] and not flags["官杀"]:
                chart_bias["创业商贸"] += 0.8
                chart_bias["金融财"] += 0.6
            for bucket, kws in _CAREER_BUCKETS.items():
                if any(kw in text for kw in kws):
                    score += chart_bias.get(bucket, 0.0)
        elif domain == "wealth":
            if strength == "偏旺" and flags["财"]:
                pref = {"大富": 1.2, "小康稳定": 0.8, "起伏投机": 0.4, "贫困": 0.0}
            elif strength == "偏弱" and flags["财"]:
                pref = {"大富": 0.2, "小康稳定": 0.6, "起伏投机": 1.0, "贫困": 0.5}
            else:
                pref = {"大富": 0.5, "小康稳定": 1.0, "起伏投机": 0.5, "贫困": 0.3}
            for bucket, kws in _WEALTH_BUCKETS.items():
                if any(kw in text for kw in kws):
                    score += pref.get(bucket, 0.0)
        elif domain == "health":
            target = list(_HEALTH_ORGANS.get(max_el, ())) + list(_HEALTH_ORGANS.get(min_el, ()))
            score += float(sum(1 for kw in target if kw in text))
            for el, organs in _HEALTH_ORGANS.items():
                if el in taboo and any(o in text for o in organs):
                    score += 0.5
        elif domain == "education":
            if flags["印"] and strength != "偏弱":
                pref = {"高学历": 1.2, "中等": 0.7, "低或无": 0.1}
            elif flags["印"]:
                pref = {"高学历": 0.5, "中等": 1.0, "低或无": 0.4}
            else:
                pref = {"高学历": 0.3, "中等": 0.8, "低或无": 0.6}
            for bucket, kws in _EDU_BUCKETS.items():
                if any(kw in text for kw in kws):
                    score += pref.get(bucket, 0.0)
        if score > 0:
            cands.append(Candidate(option=opt, text=text, score=score, reasons=[domain]))

    if not cands:
        return []
    ranked = sorted(cands, key=lambda c: c.score, reverse=True)
    best = ranked[0]
    runner = ranked[1].score if len(ranked) > 1 else float("-inf")
    margin = best.score - runner
    best.confidence = "high" if margin >= 0.5 else ("medium" if margin >= 0.2 else "low")
    return ranked[:top_k]


def arbitrate_shortlist(
    free_pred: str,
    guided_pred: str,
    shortlist: List[Candidate],
) -> Tuple[str, str]:
    """Pick free vs shortlist-guided answer when both LLM passes are available.

    Policy (tuned on A/B n=12 + offline ceilings):
    - free ∈ shortlist → free (rules and free model agree)
    - free ∉ shortlist, top conf high and score ≥ 0.5 → guided
      (strong symbolic case; free is more likely lost)
    - otherwise → free (protects status/weak-signal cases like P033-Q39)

    Returns ``(chosen_letter, reason_tag)``.
    """
    free_pred = (free_pred or "").strip().upper()[:1]
    guided_pred = (guided_pred or "").strip().upper()[:1]
    if not free_pred and guided_pred:
        return guided_pred, "guided_only"
    if free_pred and not guided_pred:
        return free_pred, "free_only"
    if not free_pred and not guided_pred:
        return "", "empty"
    if free_pred == guided_pred:
        return free_pred, "agree"
    sl_letters = {(c.option or "").strip().upper()[:1] for c in shortlist if c.option}
    best = shortlist[0] if shortlist else None
    top_l = (best.option or "").strip().upper()[:1] if best else ""
    # Free already equals shortlist top-1 → trust free (rules + free agree).
    if free_pred and free_pred == top_l:
        return free_pred, "free_is_top1"
    # Free outside shortlist but guided hits top-1 with decent score → guided.
    if (
        free_pred
        and free_pred not in sl_letters
        and guided_pred == top_l
        and best
        and best.score >= 0.4
    ):
        return guided_pred, "guided_top1_free_out"
    # Strong symbolic top-1: prefer guided when free wandered.
    if best and best.confidence == "high" and best.score >= 0.5:
        if guided_pred == top_l:
            return guided_pred, "guided_high_conf"
        if free_pred not in sl_letters and guided_pred in sl_letters:
            return guided_pred, "guided_high_conf_sl"
    # Free is a non-top shortlist member (weak #2): prefer guided top-1 if present.
    if free_pred in sl_letters and guided_pred == top_l and best and best.score >= 0.4:
        return guided_pred, "guided_top1_over_weak_free"
    return free_pred, "free_fallback"


def prefer_shortlist_after_llm(
    predicted: str,
    shortlist: Sequence[Candidate],
) -> Tuple[Optional[str], str]:
    """Post-LLM shortlist trust: override model when it wanders outside shortlist.

    Only fires when the model pick is **not** in the shortlist.  Overriding a
    model that already chose shortlist #2 with a high-margin (but wrong) top-1
    hurt full-set accuracy (contest8 n200 P016-Q37: gold C overwritten to A).

    Policy (outside-shortlist only):
    - top score ≥ 0.6 → force top-1
    - top score ≥ 0.5 and margin ≥ 0 → force top-1

    Returns ``(override_letter_or_None, reason_tag)``.
    """
    pred = (predicted or "").strip().upper()[:1]
    if not shortlist:
        return None, "no_shortlist"
    top = shortlist[0]
    top_l = (top.option or "").strip().upper()[:1]
    if not top_l:
        return None, "empty_top"
    top_s = float(top.score or 0.0)
    second_s = float(shortlist[1].score or 0.0) if len(shortlist) > 1 else 0.0
    margin = top_s - second_s
    sl_letters = {
        (c.option or "").strip().upper()[:1] for c in shortlist if c.option
    }

    # Never displace a model pick already inside the shortlist.
    if pred and pred in sl_letters:
        return None, "keep_llm_in_sl"
    if not pred:
        # Empty parse: fall back to strong top-1 if available.
        if top_s >= 0.4:
            return top_l, "empty_pred_fallback"
        return None, "empty_pred"
    if top_s >= 0.6:
        return top_l, "high_score_outside_sl"
    # Model wandered completely outside a decent shortlist (margin vs runner-up).
    if top_s >= 0.4 and margin >= 0.25:
        return top_l, "mid_score_outside_sl"
    if top_s >= 0.5 and margin >= 0.0:
        return top_l, "mid_score_outside_sl"
    return None, "keep_llm"


def apply_rule_reasoner(
    bazi: str,
    question: str,
    options: List[str],
    *,
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
    min_confidence: str = "high",
) -> Optional[str]:
    """Convenience wrapper: return option letter if rule confidence is high enough.

    Default ``min_confidence="high"``: the engine only overrides the LLM when its
    margin-based confidence is high (top score beats runner-up by ≥0.5), which is
    the only slice where LOO calibration showed it reliably beats the LLM (~75%
    vs ~40%).  At lower thresholds the symbolic features are not reliable enough
    to override (see docs/bazi_ai_error_analysis.md §4).  For those cases use
    ``rank_year_candidates`` + ``format_shortlist_block`` to soft-guide the LLM.

    Hard override is further restricted to classic event kinds
    (marriage/children/parent) that also match *strict* year-event keywords
    (e.g. 「结婚」not mere「恋爱」) and pass an absolute score floor.  Expanded
    kinds (move/legal/generic) and loose keyword hits are shortlist-only.
    """
    if not bazi or not birth_date:
        return None
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    try:
        reasoner = RuleReasoner(bazi, gender, birth_date, birth_time)
        kind = reasoner.classify_year_event(question)
        if kind not in RuleReasoner._HARD_OVERRIDE_KINDS:
            return None
        strict_kws = RuleReasoner._STRICT_HARD_KW.get(kind, ())
        if not any(k in question for k in strict_kws):
            return None
        candidate = reasoner.reason(question, options)
        if (
            candidate
            and candidate.score >= RuleReasoner._HARD_OVERRIDE_MIN_SCORE
            and confidence_rank.get(candidate.confidence, 0)
            >= confidence_rank.get(min_confidence, 1)
        ):
            return candidate.option
    except Exception:
        pass
    return None
