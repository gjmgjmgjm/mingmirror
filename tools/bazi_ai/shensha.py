#!/usr/bin/env python3
"""神煞(Shensha)结构层 —— 确定性查表,零 API,零 datetime。

设计目的
--------
补齐八字排盘的「神煞」一环 —— 护城河结构层(排盘/用神/六亲)之外,最缺的
硬功能。每颗星 = 查表(干/支 → 目标干支)+ 扫描四柱命中。存在性非此即彼,
所以与六亲不同:**无流派模糊**(禄/羊刃 pin 显式表,异议见各表注释)。

镜像 ``liuqin_profile`` 模式:纯函数 ``(bazi, gender) -> dict``,月支直接取自
四柱(pillars[1][1]),不需出生时间。

流派约定(便于校正)
--------------------
- **长生系**: 禄/羊刃 pin 显式通用表。羊刃取主流「阴干取阳刃后一支」
  (甲卯乙辰丙午丁未戊午己未庚酉辛戌壬子癸丑);另有「阴干逆行」一派
  (乙寅丁巳…)未取。
- **学堂/词馆**: 纳音五行长生/帝旺(对齐 bazi_knowledge/pdf_ocr_result 参考,
  如「戊辰年命为木→己亥为正学堂」)。土长生取申(水土同长生)。
- **天乙贵人**: 年干+日干双查(OCR: 年干贵人大、日干贵人小)。
- **三合系**(驿马/桃花/华盖/将星/劫煞/亡神/灾煞): 年支+日支双查。
- 其余取主流子平口径。

Usage::

    from tools.bazi_ai.shensha import shensha_profile
    prof = shensha_profile("乙卯 戊寅 庚子 丙子", gender="male")
    # prof["stars"] —— 每颗星;prof["by_pillar"] —— 反向索引;prof["summary_text"]
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from tools.bazi_ai.bazi_validator import extract_pillars
from tools.bazi_ai.bazi_structural import _BRANCH_HIDDEN_STEMS, kong_wang

# ---------------------------------------------------------------------------
# 基础标签
# ---------------------------------------------------------------------------
_PILLAR_LABELS: Tuple[str, ...] = ("年柱", "月柱", "日柱", "时柱")
_GAN_LABELS: Tuple[str, ...] = ("年干", "月干", "日干", "时干")
_ZHI_LABELS: Tuple[str, ...] = ("年支", "月支", "日支", "时支")

# ---------------------------------------------------------------------------
# 纳音五行(60 柱 → 五行)。tradition-neutral 数据,源同 tools/ziwei/chart._NAYIN。
# ---------------------------------------------------------------------------
_NAYIN_ELEMENT: Dict[str, str] = {
    "甲子": "金", "乙丑": "金", "丙寅": "火", "丁卯": "火",
    "戊辰": "木", "己巳": "木", "庚午": "土", "辛未": "土",
    "壬申": "金", "癸酉": "金", "甲戌": "火", "乙亥": "火",
    "丙子": "水", "丁丑": "水", "戊寅": "土", "己卯": "土",
    "庚辰": "金", "辛巳": "金", "壬午": "木", "癸未": "木",
    "甲申": "水", "乙酉": "水", "丙戌": "土", "丁亥": "土",
    "戊子": "火", "己丑": "火", "庚寅": "木", "辛卯": "木",
    "壬辰": "水", "癸巳": "水", "甲午": "金", "乙未": "金",
    "丙申": "火", "丁酉": "火", "戊戌": "木", "己亥": "木",
    "庚子": "土", "辛丑": "土", "壬寅": "金", "癸卯": "金",
    "甲辰": "火", "乙巳": "火", "丙午": "水", "丁未": "水",
    "戊申": "土", "己酉": "土", "庚戌": "金", "辛亥": "金",
    "壬子": "木", "癸丑": "木", "甲寅": "水", "乙卯": "水",
    "丙辰": "土", "丁巳": "土", "戊午": "火", "己未": "火",
    "庚申": "木", "辛酉": "木", "壬戌": "水", "癸亥": "水",
}

# 五行长生 / 帝旺位(纳音学堂/词馆用;土长生取申,水土同长生)
_WX_CHANGSHENG: Dict[str, str] = {"金": "巳", "木": "亥", "水": "申", "火": "寅", "土": "申"}
_WX_DIWANG: Dict[str, str] = {"金": "酉", "木": "卯", "水": "子", "火": "午", "土": "子"}

# ---------------------------------------------------------------------------
# 日干 → 支(临官/帝旺)显式 pin 表
# ---------------------------------------------------------------------------
# 禄(临官/建禄)—— 通用无异议
_LU: Dict[str, str] = {
    "甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳",
    "己": "午", "庚": "申", "辛": "酉", "壬": "亥", "癸": "子",
}
# 羊刃(帝旺/阳刃)—— 主流派:阴干取阳刃后一支
_YANGREN: Dict[str, str] = {
    "甲": "卯", "乙": "辰", "丙": "午", "丁": "未", "戊": "午",
    "己": "未", "庚": "酉", "辛": "戌", "壬": "子", "癸": "丑",
}

# ---------------------------------------------------------------------------
# 日干 → 支(吉神)
# ---------------------------------------------------------------------------
# 文昌(日干食神临官禄位)
_WENCHANG: Dict[str, str] = {
    "甲": "巳", "乙": "午", "丙": "申", "丁": "酉", "戊": "申",
    "己": "酉", "庚": "亥", "辛": "子", "壬": "寅", "癸": "卯",
}
# 金舆
_JINYU: Dict[str, str] = {
    "甲": "辰", "乙": "巳", "丙": "未", "丁": "申", "戊": "未",
    "己": "申", "庚": "戌", "辛": "亥", "壬": "丑", "癸": "寅",
}

# ---------------------------------------------------------------------------
# 干 → (阳贵, 阴贵)支 —— 天乙贵人(年干+日干双查)
# 与 tools/ziwei/chart._KUI_YUE(天魁/天钺)同源同表,交叉校验一致。
# ---------------------------------------------------------------------------
_TIANYI: Dict[str, Tuple[str, str]] = {
    "甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
    "乙": ("子", "申"), "己": ("子", "申"),
    "丙": ("亥", "酉"), "丁": ("亥", "酉"),
    "壬": ("卯", "巳"), "癸": ("卯", "巳"),
    "辛": ("午", "寅"),
}

# ---------------------------------------------------------------------------
# 月支系
# ---------------------------------------------------------------------------
# 月德贵人(月支三合 → 干):寅午戌→丙,申子辰→壬,亥卯未→甲,巳酉丑→庚
_YUEDE: Dict[str, str] = {
    "寅": "丙", "午": "丙", "戌": "丙",
    "申": "壬", "子": "壬", "辰": "壬",
    "亥": "甲", "卯": "甲", "未": "甲",
    "巳": "庚", "酉": "庚", "丑": "庚",
}
# 天德贵人(月支 → 干或支;支为八卦位坤申/乾亥/艮寅/巽巳)
_TIANDLE: Dict[str, Tuple[str, str]] = {
    "寅": ("干", "丁"), "卯": ("支", "申"), "辰": ("干", "壬"),
    "巳": ("干", "辛"), "午": ("支", "亥"), "未": ("干", "甲"),
    "申": ("干", "癸"), "酉": ("支", "寅"), "戌": ("干", "丙"),
    "亥": ("干", "乙"), "子": ("支", "巳"), "丑": ("干", "庚"),
}

# ---------------------------------------------------------------------------
# 三合系(年支/日支 → 所属三合局 → 各星目标支)
# 寅午戌火 / 申子辰水 / 亥卯未木 / 巳酉丑金
# 驿马=局长生支之冲; 桃花=沐浴位; 华盖=墓库; 将星=帝旺;
# 劫煞=绝地; 亡神=临官; 灾煞=帝旺之冲
# ---------------------------------------------------------------------------
_SANHE_STARS: Dict[frozenset, Dict[str, str]] = {
    frozenset({"寅", "午", "戌"}): {
        "驿马": "申", "桃花": "卯", "华盖": "戌", "将星": "午",
        "劫煞": "亥", "亡神": "巳", "灾煞": "子",
    },
    frozenset({"申", "子", "辰"}): {
        "驿马": "寅", "桃花": "酉", "华盖": "辰", "将星": "子",
        "劫煞": "巳", "亡神": "亥", "灾煞": "午",
    },
    frozenset({"亥", "卯", "未"}): {
        "驿马": "巳", "桃花": "子", "华盖": "未", "将星": "卯",
        "劫煞": "申", "亡神": "寅", "灾煞": "酉",
    },
    frozenset({"巳", "酉", "丑"}): {
        "驿马": "亥", "桃花": "午", "华盖": "丑", "将星": "酉",
        "劫煞": "寅", "亡神": "申", "灾煞": "卯",
    },
}


def _sanhe_group(branch: str) -> Optional[frozenset]:
    for grp in _SANHE_STARS:
        if branch in grp:
            return grp
    return None


# ---------------------------------------------------------------------------
# 年支系
# ---------------------------------------------------------------------------
# 孤辰寡宿(年支三会 → 孤辰,寡宿)。男重孤辰,女重寡宿。
# 亥子丑(冬)→孤寅寡戌; 寅卯辰(春)→孤巳寡丑;
# 巳午未(夏)→孤申寡辰; 申酉戌(秋)→孤亥寡未
_GUCHEN: Dict[str, Tuple[str, str]] = {
    "亥": ("寅", "戌"), "子": ("寅", "戌"), "丑": ("寅", "戌"),
    "寅": ("巳", "丑"), "卯": ("巳", "丑"), "辰": ("巳", "丑"),
    "巳": ("申", "辰"), "午": ("申", "辰"), "未": ("申", "辰"),
    "申": ("亥", "未"), "酉": ("亥", "未"), "戌": ("亥", "未"),
}
# 血刃(年支顺推二位)
_XUEREN: Dict[str, str] = {
    "子": "寅", "丑": "卯", "寅": "辰", "卯": "巳", "辰": "午", "巳": "未",
    "午": "申", "未": "酉", "申": "戌", "酉": "亥", "戌": "子", "亥": "丑",
}

# ---------------------------------------------------------------------------
# 日柱 / 性别系
# ---------------------------------------------------------------------------
# 魁罡(日柱恰为四格之一)
_KUIGANG = {"庚辰", "壬辰", "庚戌", "戊戌"}
# 天罗地网:男忌天罗(戌亥),女忌地网(辰巳)
_TIANLUO = {"戌", "亥"}
_DIGWANG = {"辰", "巳"}

# ---------------------------------------------------------------------------
# 太极贵人(日干 → 支对,须「有始有终」两支同现)
# 甲乙→子午;丙丁→卯酉;戊己→辰戌且丑未;庚辛→寅亥;壬癸→巳申
# ---------------------------------------------------------------------------
_TAIJI: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "甲": (("子", "午"),), "乙": (("子", "午"),),
    "丙": (("卯", "酉"),), "丁": (("卯", "酉"),),
    "戊": (("辰", "戌"), ("丑", "未")), "己": (("辰", "戌"), ("丑", "未")),
    "庚": (("寅", "亥"),), "辛": (("寅", "亥"),),
    "壬": (("巳", "申"),), "癸": (("巳", "申"),),
}

# ---------------------------------------------------------------------------
# 星释义 + 分类(category: 吉神/平星/凶神; tier: core/secondary)
# ---------------------------------------------------------------------------
_STAR_INFO: Dict[str, Tuple[str, str, str]] = {
    # 吉神
    "天乙贵人": ("吉神", "core", "逢凶化吉、贵人相助,诸煞之首、最尊贵之神。"),
    "天德贵人": ("吉神", "core", "天地秀气,逢凶化吉、心性慈祥仁厚。"),
    "月德贵人": ("吉神", "core", "月令秀气,逢凶化吉、心性光明。"),
    "文昌": ("吉神", "core", "文才学业,聪明过人、气质高雅,亦主逢凶化吉。"),
    "学堂": ("吉神", "secondary", "学业功名,主登科及第、聪明智巧(纳音长生位)。"),
    "词馆": ("吉神", "secondary", "学业精专、文章出众(纳音帝旺位)。"),
    "金舆": ("吉神", "secondary", "金车之贵,主富贵、得阴福相扶。"),
    "禄": ("吉神", "core", "建禄,自身福气根基、衣食之源(日干临官位)。"),
    "太极贵人": ("吉神", "secondary", "聪明好学、有钻劲,文史哲宗教缘分深。"),
    # 平星(动星/权星)
    "驿马": ("平星", "core", "奔波变动、外出迁移,主动态机遇(年/日支三合长生冲)。"),
    "桃花": ("平星", "core", "咸池,人缘魅力、感情姻缘,亦主艺术才艺。"),
    "华盖": ("平星", "core", "孤高才情、宗教艺术缘,主聪明而孤介。"),
    "将星": ("平星", "secondary", "权力威严、领导统御之象(三合帝旺位)。"),
    # 凶神
    "羊刃": ("凶神", "core", "刚烈急躁、易伤灾破财,需制化(日干帝旺位)。"),
    "空亡": ("凶神", "core", "真空乏力、缘分不实;逢吉减福、逢凶减祸(日柱旬空)。"),
    "劫煞": ("凶神", "secondary", "突发的意外损失、是非夺财(三合绝地)。"),
    "亡神": ("凶神", "secondary", "城府深、多疑虑,主暗损、失意(三合临官)。"),
    "灾煞": ("凶神", "secondary", "意外灾祸、病伤(三合帝旺之冲)。"),
    "孤辰": ("凶神", "secondary", "男命尤忌,主孤寂、婚缘迟(年支三会)。"),
    "寡宿": ("凶神", "secondary", "女命尤忌,主孤寂、婚缘迟(年支三会)。"),
    "魁罡": ("凶神", "secondary", "刚强果断、主掌权,亦易孤克(日柱特定)。"),
    "血刃": ("凶神", "secondary", "主血光、身体受伤之险(年支顺推)。"),
    "天罗地网": ("凶神", "secondary", "男忌天罗、女忌地网,主困厄官非。"),
}


# ---------------------------------------------------------------------------
# 扫描原语
# ---------------------------------------------------------------------------
def _scan_branches(targets, branches: List[str]) -> List[Dict[str, Any]]:
    """目标支集合 → 命中柱位(地支)。"""
    locs: List[Dict[str, Any]] = []
    for i, b in enumerate(branches):
        if b in targets:
            locs.append({"pillar": _PILLAR_LABELS[i], "position": _ZHI_LABELS[i],
                         "char": b, "kind": "支"})
    return locs


def _scan_stems(targets, stems: List[str], branches: List[str]) -> List[Dict[str, Any]]:
    """目标干集合 → 命中柱位(透干 + 藏干)。"""
    locs: List[Dict[str, Any]] = []
    for i, s in enumerate(stems):
        if s in targets:
            locs.append({"pillar": _PILLAR_LABELS[i], "position": _GAN_LABELS[i],
                         "char": s, "kind": "干"})
    for i, b in enumerate(branches):
        for h in _BRANCH_HIDDEN_STEMS.get(b, []):
            if h in targets:
                locs.append({"pillar": _PILLAR_LABELS[i],
                             "position": f"{_ZHI_LABELS[i]}藏干",
                             "char": h, "kind": "藏干"})
    return locs


def _star(name: str, rule: str, locs: List[Dict[str, Any]], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    category, tier, desc = _STAR_INFO.get(name, ("平星", "secondary", ""))
    return {
        "name": name,
        "category": category,
        "tier": tier,
        "rule": rule,
        "present": bool(locs),
        "locations": locs,
        "description": desc,
        **(extra or {}),
    }


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def shensha_profile(bazi: str, gender: str = "male") -> Optional[Dict[str, Any]]:
    """计算命局神煞(确定性查表,零 API)。

    Returns:
        ``{day_master, stars[], by_pillar, summary, summary_text}``,或 None(八字无效)。
        每颗星始终列出(无命中 present=False),让用户看到「这盘无 X」。
    """
    try:
        pillars = extract_pillars(bazi)
    except Exception:
        return None
    if len(pillars) != 4:
        return None

    stems = [p[0] for p in pillars]
    branches = [p[1] for p in pillars]
    year_stem, month_stem, day_stem, hour_stem = stems
    year_branch, month_branch, day_branch, hour_branch = branches
    day_pillar = pillars[2]
    year_pillar = pillars[0]

    stars: List[Dict[str, Any]] = []

    def add(name: str, rule: str, locs: List[Dict[str, Any]], extra: Optional[Dict[str, Any]] = None) -> None:
        stars.append(_star(name, rule, locs, extra))

    # ---- 吉神 ----
    # 天乙贵人(年干+日干双查,阳贵/阴贵分别标)
    ty_locs: List[Dict[str, Any]] = []
    for src_stem, src_label in ((year_stem, "年干"), (day_stem, "日干")):
        pair = _TIANYI.get(src_stem)
        if not pair:
            continue
        for kind, target in (("阳贵", pair[0]), ("阴贵", pair[1])):
            hits = _scan_branches({target}, branches)
            for h in hits:
                h2 = dict(h)
                h2["source"] = f"{src_label}{kind}"
                ty_locs.append(h2)
    # 去重(同柱同支只留一条,合并 source)
    ty_locs = _dedup_locs(ty_locs)
    add("天乙贵人", "年干/日干 → 阳贵/阴贵支(甲戊庚丑未…)", ty_locs)

    # 天德贵人(月支 → 干或支)
    td_rule = _TIANDLE.get(month_branch)
    td_locs: List[Dict[str, Any]] = []
    if td_rule:
        kind, target = td_rule
        td_locs = _scan_stems({target}, stems, branches) if kind == "干" else _scan_branches({target}, branches)
    add("天德贵人", f"月支{month_branch} → {td_rule[1] if td_rule else '—'}", td_locs)

    # 月德贵人(月支三合 → 干)
    yd_gan = _YUEDE.get(month_branch)
    yd_locs = _scan_stems({yd_gan}, stems, branches) if yd_gan else []
    add("月德贵人", f"月支{month_branch}三合 → {yd_gan or '—'}", yd_locs)

    # 文昌(日干 → 支)
    wc = _WENCHANG.get(day_stem, "")
    add("文昌", f"日干{day_stem} → {wc or '—'}", _scan_branches({wc}, branches) if wc else [])

    # 学堂 / 词馆(年柱纳音五行 → 长生 / 帝旺)
    nayin_el = _NAYIN_ELEMENT.get(year_pillar, "")
    if nayin_el:
        xt = _WX_CHANGSHENG[nayin_el]
        cg = _WX_DIWANG[nayin_el]
        add("学堂", f"年柱{year_pillar}纳音{nayin_el}长生 → {xt}", _scan_branches({xt}, branches))
        add("词馆", f"年柱{year_pillar}纳音{nayin_el}帝旺 → {cg}", _scan_branches({cg}, branches))
    else:
        add("学堂", "纳音未取", [])
        add("词馆", "纳音未取", [])

    # 金舆(日干 → 支)
    jy = _JINYU.get(day_stem, "")
    add("金舆", f"日干{day_stem} → {jy or '—'}", _scan_branches({jy}, branches) if jy else [])

    # 禄(日干临官)
    lu = _LU.get(day_stem, "")
    add("禄", f"日干{day_stem}临官 → {lu or '—'}", _scan_branches({lu}, branches) if lu else [])

    # 太极贵人(日干 → 支对,须两支同现)
    tj_pairs = _TAIJI.get(day_stem, ())
    tj_locs: List[Dict[str, Any]] = []
    tj_rule = ""
    for pair in tj_pairs:
        a, b = pair
        tj_rule = f"日干{day_stem} → {a}{b}须同现"
        la = _scan_branches({a}, branches)
        lb = _scan_branches({b}, branches)
        if la and lb:  # 有始有终:两支皆现
            tj_locs = la + lb
            break
    add("太极贵人", tj_rule or f"日干{day_stem} → 太极支对", _dedup_locs(tj_locs))

    # ---- 平星(三合系:年支+日支双查)----
    sanhe_names = ("驿马", "桃花", "华盖", "将星")
    for sname in sanhe_names:
        targets: Dict[str, str] = {}  # target支 → source label
        for src_b, src_label in ((year_branch, "年支"), (day_branch, "日支")):
            grp = _sanhe_group(src_b)
            if not grp:
                continue
            t = _SANHE_STARS[grp][sname]
            targets.setdefault(t, src_label)
        locs: List[Dict[str, Any]] = []
        for t, src in targets.items():
            for h in _scan_branches({t}, branches):
                h2 = dict(h)
                h2["source"] = src
                locs.append(h2)
        add(sname, f"年/日支三合 → {','.join(targets) or '—'}", _dedup_locs(locs))

    # ---- 凶神 ----
    # 羊刃(日干帝旺)
    yr = _YANGREN.get(day_stem, "")
    add("羊刃", f"日干{day_stem}帝旺 → {yr or '—'}", _scan_branches({yr}, branches) if yr else [])

    # 空亡(日柱旬空,复用 kong_wang)
    try:
        kw1, kw2 = kong_wang(day_pillar)
    except Exception:
        kw1, kw2 = "", ""
    kw_targets = {x for x in (kw1, kw2) if x}
    kw_locs = _scan_branches(kw_targets, branches)
    add("空亡", f"日柱{day_pillar}旬空 → {kw1}{kw2}", kw_locs,
        extra={"kong_wang": [kw1, kw2]})

    # 劫煞 / 亡神 / 灾煞(三合系凶神:年支+日支双查)
    for sname in ("劫煞", "亡神", "灾煞"):
        targets = {}
        for src_b, src_label in ((year_branch, "年支"), (day_branch, "日支")):
            grp = _sanhe_group(src_b)
            if not grp:
                continue
            t = _SANHE_STARS[grp][sname]
            targets.setdefault(t, src_label)
        locs = []
        for t, src in targets.items():
            for h in _scan_branches({t}, branches):
                h2 = dict(h)
                h2["source"] = src
                locs.append(h2)
        add(sname, f"年/日支三合 → {','.join(targets) or '—'}", _dedup_locs(locs))

    # 孤辰寡宿(年支三会)
    gc = _GUCHEN.get(year_branch)
    if gc:
        gu, gua = gc  # (孤辰支, 寡宿支)
        add("孤辰", f"年支{year_branch}三会 → {gu}", _scan_branches({gu}, branches))
        add("寡宿", f"年支{year_branch}三会 → {gua}", _scan_branches({gua}, branches))
    else:
        add("孤辰", "年支三会", [])
        add("寡宿", "年支三会", [])

    # 魁罡(日柱恰为四格)
    add("魁罡", f"日柱{day_pillar} ∈ 庚辰/壬辰/庚戌/戊戌",
        [{"pillar": "日柱", "position": "日柱", "char": day_pillar, "kind": "柱"}] if day_pillar in _KUIGANG else [])

    # 血刃(年支顺推)
    xr = _XUEREN.get(year_branch, "")
    add("血刃", f"年支{year_branch} → {xr or '—'}", _scan_branches({xr}, branches) if xr else [])

    # 天罗地网(性别 + 年支/日支)
    is_male = (gender or "male").strip().lower() not in ("female", "女", "f")
    tl_targets = _TIANLUO if is_male else _DIGWANG
    tl_label = "天罗(男)" if is_male else "地网(女)"
    tl_locs = _scan_branches(tl_targets, branches)
    add("天罗地网", f"{tl_label}年/日支 ∈ {''.join(sorted(tl_targets))}", tl_locs)

    # ---- 汇总 ----
    return _assemble(day_stem, stars)


def _dedup_locs(locs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """同柱同位同字合并(聚合 source 标签)。"""
    bucket: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    order: List[Tuple[str, str, str]] = []
    for loc in locs:
        key = (loc["pillar"], loc["position"], loc["char"])
        if key not in bucket:
            bucket[key] = dict(loc)
            bucket[key]["source"] = loc.get("source", "")
            order.append(key)
        else:
            src = loc.get("source", "")
            if src and src not in bucket[key]["source"]:
                bucket[key]["source"] = (bucket[key]["source"] + "+" + src) if bucket[key]["source"] else src
    return [bucket[k] for k in order]


def _assemble(day_master: str, stars: List[Dict[str, Any]]) -> Dict[str, Any]:
    present = [s for s in stars if s["present"]]
    auspicious = [s["name"] for s in present if s["category"] == "吉神"]
    neutral = [s["name"] for s in present if s["category"] == "平星"]
    malefic = [s["name"] for s in present if s["category"] == "凶神"]

    by_pillar: Dict[str, List[str]] = {lbl: [] for lbl in _PILLAR_LABELS}
    for s in present:
        for loc in s["locations"]:
            pillar = loc.get("pillar", "")
            if pillar in by_pillar and s["name"] not in by_pillar[pillar]:
                by_pillar[pillar].append(s["name"])

    counts = {"吉神": len(auspicious), "平星": len(neutral), "凶神": len(malefic)}

    # summary_text:突出关键星 + 分类计数
    bits: List[str] = []
    if auspicious:
        bits.append("吉神" + "、".join(auspicious))
    if neutral:
        bits.append("平星" + "、".join(neutral))
    if malefic:
        bits.append("凶神" + "、".join(malefic))
    summary_text = "神煞:" + ";".join(bits) + "。" if bits else "神煞:命局未见显著神煞。"

    return {
        "day_master": day_master,
        "stars": stars,
        "by_pillar": by_pillar,
        "summary": {
            "auspicious": auspicious,
            "neutral": neutral,
            "malefic": malefic,
            "counts": counts,
        },
        "summary_text": summary_text,
    }


def day_shensha(day_gan: str, day_zhi: str, gender: str = "male") -> List[Dict[str, str]]:
    """单日神煞(择日 / 黄历用):日干支自带的神煞,复用 shensha 规则表,不复制。

    判定日支是否为「该日干所主星曜」之落位。返回每条 ``{name,category,effect,info}``,
    effect ∈ {"吉","凶"}。仅取可由单日干支确定之星(天乙贵人/文昌/禄/金舆/羊刃);
    三合系(驿马/桃花/华盖…)需年支参照,不在单日判定之列。
    """
    out: List[Dict[str, str]] = []
    ty = _TIANYI.get(day_gan)
    if ty and day_zhi in ty:
        kind = "阳贵" if day_zhi == ty[0] else "阴贵"
        out.append({"name": "天乙贵人", "category": "吉神", "effect": "吉",
                    "info": f"日干{day_gan}{kind}{day_zhi}"})
    for table, sname, cat, eff in (
        (_WENCHANG, "文昌", "吉神", "吉"),
        (_LU, "禄", "吉神", "吉"),
        (_JINYU, "金舆", "吉神", "吉"),
    ):
        if table.get(day_gan) == day_zhi:
            out.append({"name": sname, "category": cat, "effect": eff,
                        "info": f"日干{day_gan}{sname}{day_zhi}"})
    if _YANGREN.get(day_gan) == day_zhi:
        out.append({"name": "羊刃", "category": "凶神", "effect": "凶",
                    "info": f"日干{day_gan}羊刃{day_zhi}"})
    return out


if __name__ == "__main__":
    import json
    demo = "乙卯 戊寅 庚子 丙子"
    prof = shensha_profile(demo, gender="male") or {}
    print(f"# 神煞自检 · {demo}\n")
    for s in prof.get("stars", []):
        mark = "✓" if s["present"] else "·"
        locs = ",".join(f"{l['pillar']}{l['position']}{l['char']}" for l in s["locations"])
        print(f"  {mark} [{s['category']}] {s['name']:<6} {s['rule']:<28} → {locs or '—'}")
    print("\n" + prof.get("summary_text", ""))
    print("\nby_pillar:", json.dumps(prof.get("by_pillar", {}), ensure_ascii=False))
