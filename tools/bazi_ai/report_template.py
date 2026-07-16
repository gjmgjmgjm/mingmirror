#!/usr/bin/env python3
"""可解释命盘报告渲染器 —— 把确定性结构层翻译成用户可读的报告。

设计目的
--------
把项目最稀缺的资产(确定性、可验证、不胡说的命理结构层)翻译成用户能
**感知**的专业感与信任。详见战略:护城河不在"算得准",在"算的东西能拿出来
给人看依据"。

核心设计
--------
- **结构层**(`structural_profile` + `liuqin_profile`)全部确定性、零 API,
  任意八字都能生成一份可信骨架。这是"可解释报告"的基石。
- 若传入 LLM `result`(`analyze_bazi` 的返回),在其上叠加取象 / 领域 / 性格 /
  里程碑等 AI 章节。
- 每一节标注**来源**:``✅ 确定性``(可验证)或 ``◐ AI 推理``(趋势参考),
  让用户分清"算出来的"和"推出来的"。这是把 100%/90% 的真 accuracy 变成
  用户眼里"专业感"的唯一通道。
- **章节号动态连续**:AI 章节缺失时编号自动重排,不出现跳号。

Usage::

    from tools.bazi_ai.report_template import render_report
    md = render_report("乙卯 戊寅 庚子 丙子", gender="male")  # 零 API
    # 带完整 LLM 解读:
    # md = render_report(bazi, gender, result=await analyze_bazi(...))
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from tools.bazi_ai.bazi_structural import (
    liuqin_profile,
    shishen_for_stem,
    structural_profile,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 章节 label 不含序号 —— 序号由 render_report 按实际输出顺序动态注入。
_PILLAR_LABELS: Tuple[str, ...] = ("年柱", "月柱", "日柱", "时柱")
_PALACE_LABELS: Tuple[str, ...] = ("祖上 / 父母宫", "父母 / 兄弟宫", "夫妻宫", "子女宫")

_LIUQIN_MEMBERS: List[Tuple[str, str]] = [
    ("father", "父亲"), ("mother", "母亲"), ("spouse", "配偶"),
    ("son", "儿子"), ("daughter", "女儿"),
    ("brother", "兄弟"), ("sister", "姐妹"),
]

# 地支本气藏干(标准):用于排盘表格的"地支本气十神",得到细十神(正财/偏财…)。
_ZHI_MAIN_GAN: Dict[str, str] = {
    "子": "癸", "丑": "己", "寅": "甲", "卯": "乙", "辰": "戊",
    "巳": "丙", "午": "丁", "未": "己", "申": "庚", "酉": "辛",
    "戌": "戊", "亥": "壬",
}

# 日主一句话定性(取象入门版),结构层展示用。
_DAYMASTER_TRAITS: Dict[str, str] = {
    "甲": "参天大树 —— 刚直向上、自立性强,不善屈居人下",
    "乙": "藤萝花草 —— 柔韧灵活、善借势,以柔克刚",
    "丙": "太阳之火 —— 热情外放、光明磊落,易露锋芒",
    "丁": "灯烛之火 —— 温文细腻、外柔内秀,洞察入微",
    "戊": "城墙厚土 —— 厚重可靠、包容沉稳,守成稳重",
    "己": "田园沃土 —— 谦和涵养、能载能育,默默成事",
    "庚": "顽金刀剑 —— 果断刚毅、重义好胜,宁折不弯",
    "辛": "珠玉首饰 —— 精致敏锐、外柔内刚,追求完美",
    "壬": "江河之水 —— 智慧灵动、奔放不羁,应变力强",
    "癸": "雨露之水 —— 柔顺细腻、敏感多思,润物无声",
}

_CN_NUM: List[str] = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def _norm_gender(gender: str) -> str:
    g = (gender or "male").strip().lower()
    return "female" if g in ("female", "女", "f") else "male"


def _safe(text: Any) -> str:
    if text is None:
        return ""
    return str(text).strip()


def _has_content(*parts: Any) -> bool:
    return any(_safe(p) for p in parts)


# ---------------------------------------------------------------------------
# 各章节 —— 返回 (label, body),label 不含序号
# ---------------------------------------------------------------------------

def _section_chart(structural: Dict[str, Any]) -> Tuple[str, str]:
    """命局画像 + 四柱排盘(确定性)。"""
    day_master = _safe(structural.get("day_master"))
    month_branch = _safe(structural.get("month_branch"))
    stems: List[str] = structural.get("stems") or ["", "", "", ""]
    branches: List[str] = structural.get("branches") or ["", "", "", ""]
    geju = _safe(structural.get("geju")) or "月令比劫,需另寻透干格局"
    strength = _safe(structural.get("strength")) or "—"
    elem = _safe(structural.get("element_weighted_text")) or _safe(structural.get("element_counts_text"))
    trait = _DAYMASTER_TRAITS.get(day_master, "")

    # 排盘表格 —— 天干十神自算(日干标"日主"),地支本气十神用本气藏干推。
    stem_ss = [shishen_for_stem(day_master, s) if s else "" for s in stems]
    stem_ss[2] = "日主"  # 日柱天干即命主自身
    branch_ss = [shishen_for_stem(day_master, _ZHI_MAIN_GAN.get(b, "")) for b in branches]

    def _row(name: str, cells: List[str]) -> str:
        return "| " + name + " | " + " | ".join(c or "—" for c in cells) + " |"

    table = "\n".join([
        "|      | 年柱 | 月柱 | 日柱 | 时柱 |",
        "|------|:----:|:----:|:----:|:----:|",
        _row("天干", stems),
        _row("地支", branches),
        _row("天干十神", stem_ss),
        _row("地支本气", branch_ss),
        _row("宫位", list(_PALACE_LABELS)),
    ])

    body = "\n".join([
        f"- **日主**:「{day_master}」　{trait}".rstrip(),
        f"- **月令**:{month_branch}　|　**格局**:{geju}(月令定格,程序判定)",
        f"- **旺衰**:{strength}　|　**五行分布(天干0.5+地支1.0加权)**:{elem or '—'}",
        "",
        "### 四柱排盘",
        "",
        table,
        "",
        "> 排盘对齐 iztro 预制命盘(项目验证 32/32=100%),子时按「归次日」现代通行约定。",
    ])
    return ("命局画像　`✅ 确定性 · 零 API`", body)


def _section_yongshen(structural: Dict[str, Any]) -> Tuple[str, str]:
    """用神与忌神(确定性,对齐穷通宝鉴口径)。"""
    useful = _safe(structural.get("useful_gods")) or "需细断"
    taboo = _safe(structural.get("taboo_gods")) or "需细断"
    strength = _safe(structural.get("strength"))
    elem = _safe(structural.get("element_weighted_text"))
    basis = "扶抑+调候+通关 engine 判定"

    body = "\n".join([
        f"- **用神**:{useful}　—— 生扶日主、调和命局的成长引擎,人生顺势的方向",
        f"- **忌神**:{taboo}　—— 克泄太过、带来压力与隐患的领域,需规避或化解",
        f"- **判定依据**:{basis}(参考旺衰「{strength or '—'}」、五行「{elem or '—'}」)",
        "",
        "> 用神算法在 **n=92 真实命主**上与《穷通宝鉴》调候用神 **90.2% 一致**"
        "(`validate_yongshen_full.py`),跨数据集稳定,可 cite。",
    ])
    return ("用神与忌神　`✅ 确定性 · 对齐穷通宝鉴`", body)


def _section_quxiang(result: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """关键取象(AI 推理,可选)。"""
    qx = result.get("quxiang")
    if not isinstance(qx, dict) or not qx:
        return None
    blocks = []
    labels = [("day_master", "日主取象"), ("key_shishen", "关键十神取象"),
              ("career", "职业取象"), ("health", "健康取象")]
    for k, label in labels:
        text = _safe(qx.get(k))
        if text:
            blocks.append(f"**{label}**\n{text}")
    if not blocks:
        return None
    return ("关键取象　`◐ AI 推理`", "\n\n".join(blocks))


def _section_liuqin(liuqin: Dict[str, Any]) -> Tuple[str, str]:
    """六亲缘分(确定性星宫同参)。"""
    rows = []
    for key, label in _LIUQIN_MEMBERS:
        info = liuqin.get(key) or {}
        strength = _safe(info.get("strength")) or "—"
        desc = _safe(info.get("description"))
        mark = "强" if strength == "强" else ("弱" if strength == "弱" else "—")
        rows.append(f"| {label} | {mark} | {desc or '—'} |")

    palace_bits = []
    for k, label in [("spouse_palace", "夫妻宫"), ("parents_palace", "父母宫"), ("children_palace", "子女宫")]:
        p = liuqin.get(k) or {}
        d = _safe(p.get("description"))
        if d:
            palace_bits.append(f"- **{label}**:{d}")

    body_lines = [
        "| 六亲 | 强弱 | 依据 |",
        "|------|:----:|------|",
        *rows,
        "",
    ]
    if palace_bits:
        body_lines += ["**宫位**"] + palace_bits + [""]
    body_lines.append(
        "> 六亲强弱由「星根是否被冲 / 合化坏」确定性判定(项目 det 层 n=39 验证 77%);"
        "「星」看十神落柱,「宫」看地支位置,二者同参。"
    )
    return ("六亲缘分　`✅ 确定性 · 星宫同参`", "\n".join(body_lines))


def _section_structure_detail(structural: Dict[str, Any]) -> Tuple[str, str]:
    """格局细节:合化 / 冲刑害 / 空亡 / 宫位(确定性)。"""
    tg_he = _safe(structural.get("tian_gan_he_text")) or "无"
    dz_rel = _safe(structural.get("di_zhi_relations_text")) or "无"
    dz_comp = _safe(structural.get("di_zhi_comprehensive_text")) or "无特殊组合"
    kw = _safe(structural.get("kong_wang")) or "无"
    palace = _safe(structural.get("palace_text")) or "—"

    body = "\n".join([
        f"- **天干合化**:{tg_he}",
        f"- **地支六冲 / 六合 / 刑害**:{dz_rel}",
        "- **地支综合关系**(含三合 / 半合 / 三会 / 藏干合 / 冲合互解):",
        "",
        "```\n" + dz_comp + "\n```",
        f"- **空亡**:{kw}",
        f"- **宫位**:{palace}",
    ])
    return ("格局与刑冲合化　`✅ 确定性`", body)


def _section_life(result: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """人生篇章:性格 / 四领域 / 财富婚姻(AI 推理,可选)。"""
    personality = _safe(result.get("personality"))
    da = result.get("domain_analysis") or {}
    career = _safe(da.get("career"))
    wealth = _safe(da.get("wealth"))
    marriage = _safe(da.get("marriage"))
    health = _safe(da.get("health"))
    wealth_level = _safe(result.get("wealth_level"))
    wealth_ev = _safe(result.get("wealth_evidence"))
    mar_status = _safe(result.get("marriage_status"))
    mar_ev = _safe(result.get("marriage_evidence"))

    if not _has_content(personality, career, wealth, marriage, health, wealth_level, mar_status):
        return None

    lines: List[str] = []
    if personality:
        lines += [f"**性格底色**: {personality}", ""]
    for label, text in [("事业", career), ("财运", wealth), ("婚姻 / 感情", marriage), ("健康", health)]:
        if text:
            lines += [f"**{label}**:{text}", ""]
    if wealth_level or wealth_ev:
        lines.append("**原局财富潜力**:" + (wealth_level or "—"))
        if wealth_ev:
            lines.append(f"> 依据:{wealth_ev}")
        lines.append("")
    if mar_status or mar_ev:
        lines.append("**婚姻基调**:" + (mar_status or "—"))
        if mar_ev:
            lines.append(f"> 依据:{mar_ev}")
        lines.append("")
    return ("人生篇章　`◐ AI 推理 · 趋势参考`", "\n".join(lines))


def _section_dayun(
    bazi: str, gender: str, birth_info: Optional[Dict[str, Any]],
    result: Dict[str, Any],
) -> Tuple[str, str]:
    """大运走势(结构层排盘,需出生日期;否则回退 result 摘要或占位)。"""
    dy_summary = _safe(result.get("dayun_summary"))
    pillars: List[str] = []
    if birth_info and birth_info.get("birth_date"):
        try:
            from tools.bazi_ai.calendar import dayun_list
            dayun = dayun_list(
                bazi, gender,
                birth_info.get("birth_date"),
                birth_info.get("birth_time"),
                birth_info.get("calendar_type") or "solar",
                until_age=80,
            )
            for d in dayun[:8]:
                pillars.append(f"- {d['start_age']:.0f}–{d['end_age']:.0f}岁:{d['pillar']}")
        except Exception:
            pillars = []

    if pillars:
        return ("大运走势　`✅ 结构层排盘`", "\n".join(pillars))
    if dy_summary:
        return ("大运走势　`◐ AI 摘要`", dy_summary)
    return ("大运走势", "_提供出生公历/农历日期可确定性排大运(零 API);此处略。_")


def _section_milestones(result: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """关键节点(里程碑,AI 推理,趋势非断言)。"""
    ms = result.get("milestones") or []
    if not ms:
        return None
    rows = []
    for m in ms[:8]:
        if not isinstance(m, dict):
            continue
        year = _safe(m.get("year")) or "—"
        age = _safe(m.get("age")) or "—"
        mtype = _safe(m.get("type")) or "—"
        desc = _safe(m.get("description")) or "—"
        rows.append(f"| {year} | {age} | {mtype} | {desc} |")
    if not rows:
        return None
    body = (
        "| 年份 | 年龄 | 类型 | 说明 |\n|------|:----:|------|------|\n"
        + "\n".join(rows)
    )
    return ("关键节点　`◐ AI 推理 · 趋势非断言`", body)


def _section_summary(result: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """综合断语与误差说明(AI 推理,可选)。"""
    summary = result.get("summary") or []
    caveats = result.get("caveats") or []
    if isinstance(summary, str):
        summary = [summary]
    if isinstance(caveats, str):
        caveats = [caveats]
    summary = [_safe(s) for s in summary if _safe(s)]
    caveats = [_safe(c) for c in caveats if _safe(c)]
    if not summary and not caveats:
        return None

    lines: List[str] = []
    if summary:
        lines.append("**核心断语**")
        lines += [f"{i}. {s}" for i, s in enumerate(summary, 1)]
        lines.append("")
    if caveats:
        lines.append("**可能的误差来源**")
        lines += [f"- {c}" for c in caveats]
    return ("综合断语与误差说明　`◐ AI 推理`", "\n".join(lines))


# ---------------------------------------------------------------------------
# 主渲染函数
# ---------------------------------------------------------------------------

def render_report(
    bazi: str,
    gender: str = "male",
    result: Optional[Dict[str, Any]] = None,
    birth_info: Optional[Dict[str, Any]] = None,
) -> str:
    """渲染一份可解释的命盘解读报告(markdown)。

    Args:
        bazi: 四柱八字,空格分隔,如 ``"乙卯 戊寅 庚子 丙子"``。
        gender: ``"male"``/``"男"`` 或 ``"female"``/``"女"``。
        result: ``analyze_bazi`` 的返回 dict(可选)。有则叠加 AI 解读章节。
        birth_info: ``{"birth_date","birth_time","calendar_type"}`` 用于确定性排
            大运(可选)。

    Returns:
        markdown 字符串。**结构层确定性、零 API 即可生成**;AI 章节随 result 叠加。
        章节号按实际输出动态连续编号,AI 章节缺失不跳号。
    """
    bazi = (bazi or "").strip()
    gender = _norm_gender(gender)
    result = result or {}

    structural = structural_profile(bazi) or {}
    liuqin = liuqin_profile(bazi, gender=gender) or {}

    gender_label = "男命" if gender == "male" else "女命"
    has_llm = bool(result and (result.get("domain_analysis") or result.get("quxiang")
                               or result.get("personality") or result.get("summary")))

    # 按逻辑阅读顺序收集章节(过滤可选章节)。
    sections: List[Tuple[str, str]] = []
    sections.append(_section_chart(structural))
    sections.append(_section_yongshen(structural))
    qx = _section_quxiang(result)
    if qx:
        sections.append(qx)
    if liuqin:
        sections.append(_section_liuqin(liuqin))
    sections.append(_section_structure_detail(structural))
    life = _section_life(result)
    if life:
        sections.append(life)
    sections.append(_section_dayun(bazi, gender, birth_info, result))
    ms = _section_milestones(result)
    if ms:
        sections.append(ms)
    sm = _section_summary(result)
    if sm:
        sections.append(sm)

    # ---- 组装 ----
    out: List[str] = [
        f"# 命盘解读报告　·　{bazi}　·　{gender_label}\n",
        "> **可信度分层**　`✅ 确定性`=程序严格计算、可验证(排盘 / 格局 / 用神 / "
        "忌神 / 六亲 / 刑冲合化);`◐ AI 推理`=大模型趋势性解读,参考而非断言。",
        "> 本报告**不构成医疗 / 法律 / 投资建议**。\n",
    ]

    for idx, (label, body) in enumerate(sections, start=1):
        num = _CN_NUM[idx] if idx < len(_CN_NUM) else str(idx)
        out.append(f"## {num}、{label}\n")
        out.append(body)
        out.append("")

    # ---- 页脚 ----
    out.append("---\n")
    if not has_llm:
        out.append(
            "_本报告仅含**结构层**(确定性,零 API 生成)。提供完整出生信息并接入"
            "解读模型后,可叠加取象、四领域分析、性格、关键节点等 AI 章节。_"
        )
    else:
        out.append(
            "_结构层由确定性算法计算(排盘 / 用神对齐穷通宝鉴 / 六亲星宫同参),"
            "AI 章节为趋势性参考。具体年份事件为概率倾向,非确定性预言。_"
        )

    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------
# 结构化报告(供 /api/v1/bazi/report 与前端消费)
# ---------------------------------------------------------------------------

def _parse_element_counts(text: str) -> Dict[str, int]:
    """解析 element_counts_text「木2,火1,…」为 {五行: 计数}。"""
    counts: Dict[str, int] = {}
    for part in (text or "").split(","):
        part = part.strip()
        if len(part) >= 2 and part[0] in "木火土金水":
            try:
                counts[part[0]] = int(part[1:])
            except ValueError:
                counts.setdefault(part[0], 0)
    for k in ["木", "火", "土", "金", "水"]:
        counts.setdefault(k, 0)
    return counts


def _split_gods(text: str) -> List[str]:
    if not text or text == "需细断":
        return []
    parts = text.replace("、", ",").split(",")
    return [p.strip() for p in parts if p.strip()]


def build_report(
    bazi: str,
    gender: str = "male",
    result: Optional[Dict[str, Any]] = None,
    birth_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """结构化报告数据,供 ``/api/v1/bazi/report`` 与前端消费。

    与 :func:`render_report` 平行,共享结构层(``structural_profile`` /
    ``liuqin_profile``)。返回 ``{"meta": ..., "sections": [...]}``,每个 section =
    ``{"id", "title", "trust"(certain|ai), "data": {...}}``。章节按实际数据动态
    生成,缺失不出现;trust 标注来源,与渲染层 ✅/◐ 对应。
    """
    bazi = (bazi or "").strip()
    gender = _norm_gender(gender)
    result = result or {}
    structural = structural_profile(bazi) or {}
    liuqin = liuqin_profile(bazi, gender=gender) or {}
    gender_label = "男命" if gender == "male" else "女命"

    day_master = _safe(structural.get("day_master"))
    stems = structural.get("stems") or ["", "", "", ""]
    branches = structural.get("branches") or ["", "", "", ""]
    stem_ss = [shishen_for_stem(day_master, s) if s else "" for s in stems]
    if len(stem_ss) >= 3:
        stem_ss[2] = "日主"
    branch_ss = [shishen_for_stem(day_master, _ZHI_MAIN_GAN.get(b, "")) for b in branches]

    elem_counts = _parse_element_counts(_safe(structural.get("element_counts_text")))
    elem_total = sum(elem_counts.values()) or 1
    pillars = []
    for i in range(4):
        pillars.append({
            "label": _PILLAR_LABELS[i] if i < len(_PILLAR_LABELS) else f"柱{i + 1}",
            "stem": stems[i] if i < len(stems) else "",
            "branch": branches[i] if i < len(branches) else "",
            "stem_shishen": stem_ss[i] if i < len(stem_ss) else "",
            "branch_shishen": branch_ss[i] if i < len(branch_ss) else "",
            "palace": _PALACE_LABELS[i] if i < len(_PALACE_LABELS) else "",
        })
    elements = [
        {"element": k, "count": elem_counts.get(k, 0),
         "percent": round(elem_counts.get(k, 0) / elem_total * 100)}
        for k in ["木", "火", "土", "金", "水"]
    ]

    sections: List[Dict[str, Any]] = []

    # 1 命局画像(确定性)
    sections.append({
        "id": "chart", "title": "命局画像", "trust": "certain",
        "data": {
            "day_master": day_master,
            "daymaster_trait": _DAYMASTER_TRAITS.get(day_master, ""),
            "month_branch": _safe(structural.get("month_branch")),
            "geju": _safe(structural.get("geju")),
            "strength": _safe(structural.get("strength")),
            "pillars": pillars,
            "elements": elements,
        },
    })

    # 2 用神忌神(确定性)
    sections.append({
        "id": "yongshen", "title": "用神与忌神", "trust": "certain",
        "data": {
            "useful_gods": _split_gods(_safe(structural.get("useful_gods"))),
            "taboo_gods": _split_gods(_safe(structural.get("taboo_gods"))),
        },
    })

    # 3 六亲(条件)
    if liuqin:
        members = []
        for key, label in _LIUQIN_MEMBERS:
            info = liuqin.get(key) or {}
            members.append({
                "key": key, "label": label,
                "strength": _safe(info.get("strength")),
                "description": _safe(info.get("description")),
            })
        if members:
            sections.append({
                "id": "liuqin", "title": "六亲缘分",
                "trust": "certain" if any(m["strength"] for m in members) else "ai",
                "data": {
                    "members": members,
                    "liuqin_analysis": _safe(result.get("liuqin_analysis")),
                },
            })

    # 4 取象(AI,条件)
    qx = result.get("quxiang")
    if isinstance(qx, dict) and any(_safe(qx.get(k)) for k in ("day_master", "key_shishen", "career", "health")):
        sections.append({
            "id": "quxiang", "title": "关键取象", "trust": "ai",
            "data": {k: _safe(qx.get(k)) for k in ("day_master", "key_shishen", "career", "health")},
        })

    # 5 人生篇章(AI,条件)
    da = result.get("domain_analysis") or {}
    personality = _safe(result.get("personality"))
    events = [e for e in (result.get("events") or []) if _safe(e)]
    domain_items = [
        {"key": k, "label": label, "text": _safe(da.get(k))}
        for k, label in (("career", "事业"), ("wealth", "财运"), ("marriage", "婚姻"), ("health", "健康"))
    ]
    domain_items = [d for d in domain_items if d["text"]]
    if personality or domain_items or events:
        sections.append({
            "id": "life", "title": "人生篇章", "trust": "ai",
            "data": {"personality": personality, "domains": domain_items, "events": events},
        })

    # 6 财富婚姻(AI,条件)
    wealth_level = _safe(result.get("wealth_level"))
    marriage_status = _safe(result.get("marriage_status"))
    if wealth_level or marriage_status:
        sections.append({
            "id": "wealth_marriage", "title": "财富与婚姻", "trust": "ai",
            "data": {
                "wealth_level": wealth_level,
                "wealth_evidence": _safe(result.get("wealth_evidence")),
                "marriage_status": marriage_status,
                "marriage_evidence": _safe(result.get("marriage_evidence")),
            },
        })

    # 7 大运(确定性排盘优先,回退 AI 摘要)
    dayun_pillars: List[Dict[str, Any]] = []
    if birth_info and birth_info.get("birth_date"):
        try:
            from tools.bazi_ai.calendar import dayun_list
            dy = dayun_list(
                bazi, gender, birth_info.get("birth_date"),
                birth_info.get("birth_time"), birth_info.get("calendar_type") or "solar",
                until_age=80,
            )
            dayun_pillars = [
                {"start_age": round(d["start_age"]), "end_age": round(d["end_age"]), "pillar": d["pillar"]}
                for d in dy[:8]
            ]
        except Exception:
            dayun_pillars = []
    if dayun_pillars:
        sections.append({"id": "dayun", "title": "大运走势", "trust": "certain",
                         "data": {"pillars": dayun_pillars}})
    elif _safe(result.get("dayun_summary")):
        sections.append({"id": "dayun", "title": "大运走势", "trust": "ai",
                         "data": {"summary": _safe(result.get("dayun_summary"))}})

    # 8 关键节点(AI,条件)
    ms = []
    for m in (result.get("milestones") or [])[:8]:
        if isinstance(m, dict):
            ms.append({
                "year": m.get("year"), "age": m.get("age"),
                "type": _safe(m.get("type")), "description": _safe(m.get("description")),
            })
    if ms:
        sections.append({"id": "milestones", "title": "关键节点", "trust": "ai",
                         "data": {"milestones": ms}})

    # 9 断语与误差(AI,条件)
    summary = [s for s in (result.get("summary") or []) if _safe(s) and not s.startswith("参考相似案例")]
    caveats = [c for c in (result.get("caveats") or []) if _safe(c) and not c.startswith("参考相似案例")]
    if summary or caveats:
        sections.append({"id": "summary", "title": "核心断语与误差", "trust": "ai",
                         "data": {"summary": summary, "caveats": caveats}})

    return {"meta": {"bazi": bazi, "gender": gender, "gender_label": gender_label},
            "sections": sections}


if __name__ == "__main__":
    # 自检:零 API 生成结构层 markdown + 结构化 JSON。
    import json
    print(render_report("乙卯 戊寅 庚子 丙子", gender="male"))
    print("\n--- structured sections ---\n")
    data = build_report("乙卯 戊寅 庚子 丙子", gender="male")
    print(json.dumps([s["id"] + ":" + s["trust"] for s in data["sections"]], ensure_ascii=False))
