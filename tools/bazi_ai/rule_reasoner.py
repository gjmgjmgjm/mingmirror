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
from typing import Dict, List, Optional, Tuple

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
    # —— 正向信号（按 logreg 系数四舍五入）——
    "stem_wuhe_daymaster": 0.9,   # 天干五合（修复死代码后）logreg +0.88
    "tian_kang_di_chong": 0.5,    # 天克地冲（流年 vs 日柱）+0.55
    "branch_sanhe_palace": 0.4,   # 流年地支半三合事件宫 +0.40
    "parent_guansha_ke": 0.4,     # 父母去世题：流年天干官杀克身 +0.37
    "dayun_stem_star": 0.3,       # 大运天干为目标十神 +0.34
    "fan_yin_day_branch": 0.3,    # 反吟：流年地支冲日支 +0.30
    "dayun_chong_palace": 0.3,    # 大运地支冲事件宫 +0.28
    "dayun_liuhe_palace": 0.2,    # 大运地支合事件宫 +0.21
    "fu_yin_day_branch": 0.2,     # 伏吟：流年地支同日支 +0.17
    "dayun_hidden_star": 0.1,     # 大运地支藏干为目标十神 +0.10
    "branch_chong_palace": 0.1,   # 流年地支冲事件宫 +0.05（接近中性）
    # —— 反向/噪声信号，置 0 防止误导 ——
    "stem_star": 0.0,             # 流年天干明现目标十神（反向 −0.18）
    "hidden_star": 0.0,           # 流年地支藏干目标十神（反向 −0.37）
    "branch_sanhui_palace": 0.0,  # 半三会（反向 −0.40）
    "dayun_sanhe_palace": 0.0,    # 大运半三合事件宫（反向 −0.23）
    "branch_liuhe_palace": 0.0,   # 流年地支合事件宫（中性 −0.06）
    "sui_yun_bing_lin": 0.0,      # 岁运并临（噪声 −0.10）
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

    # 父母去世题：流年天干官杀克身
    if qtype_kind == "parent" and year_shishen in ("七杀", "正官"):
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
        return ["偏财"], ["正印"]  # father, mother

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

    # Event kinds allowed into the soft shortlist.  ``children`` is excluded for
    # now: offline top-2 hit on contest8 is only ~25% (worse than chance for a
    # 2-of-4 shortlist), so injecting it actively misleads the LLM.
    _SHORTLIST_KINDS = frozenset({"marriage", "parent", "move", "legal", "generic"})

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
            cands = self._score_year_options(
                options, ["正官", "七杀"], self.spouse_palace, "legal"
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

# Kinds that always get shortlist (offline top-2 strong).
_SHORTLIST_ALWAYS_KINDS = frozenset({"parent", "move", "legal"})
# Kinds that need medium+ margin before injection (noisier top-2).
_SHORTLIST_GATED_KINDS = frozenset({"marriage", "generic"})


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
            # marriage/generic: need meaningful signal + non-low margin.
            # Weak medium (e.g. score 0.3 over 0.1) previously misled the LLM
            # (P018-Q7 in n50 LOO).
            if kind in _SHORTLIST_GATED_KINDS:
                if best.confidence == "low" or best.score < 0.4:
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


def format_domain_hint_block(bazi: str, question: str, *, gender: str = "male") -> str:
    """Structural reading hints for non-year MCQs — **no option ranking**.

    Offline option-ranking top-2 is only ~55% on contest8 domain questions, so
    listing A/B letters would often mislead.  Instead we inject the chart's
    十神/旺衰 implications and let the LLM map them to options.
    """
    if not bazi:
        return ""
    if is_year_asking_question(question, None):
        return ""
    try:
        from tools.bazi_ai import bazi_structural
    except Exception:
        return ""
    profile = bazi_structural.structural_profile(bazi)
    if not profile:
        return ""

    q = question
    domain = ""
    if any(k in q for k in ("职业", "工作", "事业", "从事", "行业", "职位")):
        domain = "career"
    elif any(k in q for k in ("学历", "读书", "学业", "毕业", "学校")):
        domain = "education"
    elif any(k in q for k in ("病", "疾", "健康", "身体", "受伤", "手术", "困扰")):
        domain = "health"
    elif any(k in q for k in ("财运", "财富", "有钱", "贫富", "收入", "资产", "财运")):
        domain = "wealth"
    else:
        return ""

    flags = _shishen_presence(profile)
    strength = profile.get("strength", "中和")
    useful = list(profile.get("useful_gods") or [])
    taboo = list(profile.get("taboo_gods") or [])
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
        elif flags["食伤"]:
            tips.append("食伤泄秀、官星不显 → 技术/自由/文艺倾向")
        if flags["财"] and not flags["官杀"]:
            tips.append("财星显而官弱 → 偏商业/求财，非典型公职")
        if flags["比劫"] and flags["财"]:
            tips.append("比劫见财 → 合伙/竞争/销售奔波象")
        if not tips:
            tips.append("按用神喜忌与食伤/官杀强弱，在选项中找最贴的职业象")
        lines.append("- 职业倾向：" + "；".join(tips))
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
    return "\n".join(lines)


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
    sl_opts = {c.option for c in shortlist}
    if free_pred in sl_opts:
        return free_pred, "free_in_shortlist"
    best = shortlist[0] if shortlist else None
    if best and best.confidence == "high" and best.score >= 0.5:
        return guided_pred, "guided_high_conf"
    return free_pred, "free_fallback"


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
