"""Qi Zheng Si Yu analysis engine.

Provides a DeepSeek-compatible LLM wrapper plus a deterministic mock fallback
when no API key is available. The output schema mirrors the bazi engine so that
the multi-system destiny layer can consume it uniformly.

Environment:
    DEEPSEEK_API_KEY      - required for real inference
    DEEPSEEK_BASE_URL     - defaults to https://api.deepseek.com/v1
    DEEPSEEK_MODEL        - defaults to deepseek-chat
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles

from tools.qizheng import calendar as qz_calendar
from tools.qizheng import star_tables
from tools.qizheng.prompts import (
    build_system_prompt,
    build_user_prompt,
    build_yearly_system_prompt,
    build_yearly_user_prompt,
)
from utils.logger import setup_logger

logger = setup_logger("QiZhengAnalyzer")

# Four pillars: e.g. "甲子 丙寅 戊辰 庚午"
_CHART_RE = re.compile(
    r"^[\u4e00-\u9fa5]{2}\s+[\u4e00-\u9fa5]{2}\s+[\u4e00-\u9fa5]{2}\s+[\u4e00-\u9fa5]{2}$"
)

_DOMAIN_KEYS = ("career", "wealth", "marriage", "health")


def _normalize_chart(chart: str) -> Optional[str]:
    """Normalize and validate a four-pillar chart string."""
    if not isinstance(chart, str):
        return None
    chart = chart.strip()
    if not chart:
        return None
    # Normalize multiple spaces to single space.
    chart = re.sub(r"\s+", " ", chart)
    if _CHART_RE.match(chart):
        return chart
    return None


async def _load_cases(cases_path: Optional[Path]) -> List[Dict[str, Any]]:
    if cases_path is None or not cases_path.exists():
        return []
    cases: List[Dict[str, Any]] = []
    try:
        async with aiofiles.open(cases_path, "r", encoding="utf-8") as handle:
            async for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    cases.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        logger.warning("Failed to load qizheng cases from %s: %s", cases_path, exc)
    return cases


def _score_case_relevance(case: Dict[str, Any], chart: str, question: str) -> int:
    score = 0
    if case.get("chart") == chart:
        score += 100
    text = " ".join(
        [
            case.get("chart", ""),
            case.get("analysis", ""),
            " ".join(str(v) for v in (case.get("domains") or {}).values()),
        ]
    )
    if question:
        for kw in re.split(r"[，。！？、\s]", question):
            kw = kw.strip()
            if len(kw) >= 2 and kw in text:
                score += 10
    return score


async def _retrieve_similar_cases(
    chart: str,
    question: str,
    cases_path: Optional[Path],
    top_k: int,
) -> List[Dict[str, Any]]:
    cases = await _load_cases(cases_path)
    if not cases:
        return []
    scored = [(_score_case_relevance(c, chart, question), c) for c in cases]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def _build_mock_result(
    chart: str,
    question: str,
    similar_cases: List[Dict[str, Any]],
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    refs = [c.get("chart") for c in similar_cases[:2] if c.get("chart")]
    # Take day master from the third pillar's first character.
    pillars = chart.split()
    day_master = pillars[2][0] if len(pillars) == 4 and pillars[2] else ""

    domain_texts = {
        "career": "七政得时，适合稳健型职业，中年后渐入佳境。",
        "wealth": "财星有根，正财为主，不宜高风险投机。",
        "marriage": "夫妻宫平和，配偶得力，宜晚婚。",
        "health": "注意脾胃消化与肝胆调养。",
    }

    if question:
        # When a domain-specific question is asked, leave unrelated domains
        # with a placeholder so the caller can see the focus.
        domain_analysis = {
            k: (v if any(kw in question for kw in _domain_keywords(k)) else "待详细排盘后补充")
            for k, v in domain_texts.items()
        }
    else:
        domain_analysis = dict(domain_texts)

    result: Dict[str, Any] = {
        "basic_info": {
            "chart": chart,
            "day_master": day_master,
            "life_palace": "待模型分析",
            "body_palace": "待模型分析",
            "dominant_stars": [],
        },
        "reasoning": (
            "当前未配置 DEEPSEEK_API_KEY，仅返回七政四余基础结构与 RAG 检索信息。"
            "设置环境变量后可获得完整模型分析。"
        ),
        "domain_analysis": domain_analysis,
        "summary": [f"参考相似案例：{', '.join(refs)}" if refs else "未找到相似案例"],
        "confidence": "low",
        "caveats": ["未调用真实模型", "请配置 DEEPSEEK_API_KEY"],
        "_mock": True,
    }
    if profile and profile.get("astro"):
        result["astro_profile"] = profile["astro"]
        result["aspects"] = profile.get("aspects", [])
        result["patterns"] = profile.get("patterns", [])
    return result


def _domain_keywords(domain: str) -> List[str]:
    mapping = {
        "career": ["事业", "工作", "职业", "创业", "上班", "行业", "升迁"],
        "wealth": ["财", "钱", "富", "收入", "资产", "赚钱"],
        "marriage": ["婚姻", "感情", "桃花", "老公", "老婆", "配偶", "恋爱", "结婚"],
        "health": ["健康", "病", "身体", "手术", "肾", "肝胆", "脾胃"],
    }
    return mapping.get(domain, [])


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse a datetime value from chart_info."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _resolve_profile(
    chart_info: Dict[str, Any],
    dignity_table: Optional[Dict[str, Dict[str, set]]] = None,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Resolve the chart string and structural profile from chart_info.

    Priority:
        1. birth_datetime + latitude + longitude → real astronomical profile.
        2. chart / bazi string → traditional four-pillar profile.
    """
    birth_dt = _parse_datetime(chart_info.get("birth_datetime"))
    lat = chart_info.get("latitude")
    lon = chart_info.get("longitude")
    tz_offset = chart_info.get("timezone_offset")
    precession_mode = chart_info.get("precession_mode", "tropical")

    if birth_dt is not None and lat is not None and lon is not None:
        profile = qz_calendar.astro_structural_profile(
            birth_datetime=birth_dt,
            latitude=float(lat),
            longitude=float(lon),
            timezone_offset_hours=tz_offset,
            precession_mode=str(precession_mode),
            dignity_table=dignity_table,
        )
        if profile:
            chart = profile.get("chart", "")
            normalized = _normalize_chart(chart)
            if normalized:
                return normalized, profile
            # Computed chart failed validation; keep it but note it is unvalidated.
            return chart, profile

    chart = str(chart_info.get("chart") or chart_info.get("bazi") or "").strip()
    normalized = _normalize_chart(chart)
    if normalized is None:
        return None, None
    profile = qz_calendar.structural_profile(normalized)
    return normalized, profile


def _parse_json(content: str, chart: str) -> Dict[str, Any]:
    content = content.strip()
    if not content:
        return {"basic_info": {"chart": chart}, "parse_error": True, "raw_content": ""}

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    obj_match = re.search(r"(\{.*\})", content, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except json.JSONDecodeError:
            pass

    return {"basic_info": {"chart": chart}, "parse_error": True, "raw_content": content}


def _merge_structural_profile(result: Dict[str, Any], profile: Optional[Dict[str, Any]]) -> None:
    """Inject computed structural facts into the result's basic_info."""
    if not profile:
        return
    basic = result.setdefault("basic_info", {})
    for key in (
        "day_master",
        "life_palace",
        "body_palace",
        "body_lord",
        "nayin",
        "five_element_pattern",
        "twelve_palaces",
    ):
        if key not in basic or not basic[key]:
            basic[key] = profile.get(key)

    astro = profile.get("astro")
    if astro:
        basic["ascendant"] = round(astro["ascendant"], 2)
        basic["ascendant_zodiac"] = astro.get("ascendant_zodiac")
        basic["ascendant_mansion"] = astro.get("ascendant_mansion")
        basic["midheaven"] = round(astro["midheaven"], 2)


def _ensure_domain_analysis(result: Dict[str, Any]) -> Dict[str, Any]:
    """Make sure the result contains the canonical domain keys."""
    domains = result.get("domain_analysis") or {}
    if not isinstance(domains, dict):
        domains = {}
    for key in _DOMAIN_KEYS:
        if key not in domains or not domains[key]:
            domains[key] = "待详细分析"
    result["domain_analysis"] = domains
    return result


class QiZhengAnalyzer:
    """Analyze a Qi Zheng Si Yu chart via LLM or mock fallback."""

    def __init__(
        self,
        *,
        rule_primer_path: Optional[Path] = None,
        cases_path: Optional[Path] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        top_k: int = 3,
        dignity_table: Optional[Dict[str, Dict[str, set]]] = None,
    ):
        self.rule_primer_path = rule_primer_path
        self.cases_path = cases_path
        package_dir = Path(__file__).resolve().parent
        self.examples_path = package_dir / "examples.jsonl"
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.top_k = max(0, min(top_k, 10))
        self.dignity_table = dignity_table

    async def analyze(
        self,
        chart_info: Dict[str, Any],
        question: str = "",
    ) -> Dict[str, Any]:
        """Analyze a Qi Zheng Si Yu chart.

        Args:
            chart_info: dict containing either:
                - "birth_datetime" + "latitude" + "longitude" for real
                  astronomical calculation (preferred main entry).
                - "chart" / "bazi" with the four pillars as fallback,
                  e.g. "甲子 丙寅 戊辰 庚午".
            question: optional user question.

        Returns:
            Structured analysis result matching the bazi engine schema.
        """
        chart, profile = _resolve_profile(chart_info, dignity_table=self.dignity_table)
        if chart is None:
            raw_chart = str(
                chart_info.get("chart") or chart_info.get("bazi") or ""
            ).strip()
            return {
                "basic_info": {"chart": raw_chart},
                "error": "无效的命盘格式，需要四柱六十甲子（如：甲子 丙寅 戊辰 庚午）"
                "或提供 birth_datetime + latitude + longitude",
                "reasoning": "",
                "domain_analysis": {},
                "summary": [],
                "confidence": "low",
                "caveats": ["输入命盘无法解析为四柱，且未提供有效的出生时间地点"],
            }

        similar_cases = await _retrieve_similar_cases(
            chart, question, self.cases_path, self.top_k
        )
        system_prompt = await build_system_prompt(self.rule_primer_path)
        from tools.qizheng.prompts import _load_few_shot_examples

        few_shot_examples = _load_few_shot_examples(self.examples_path)
        user_prompt = build_user_prompt(
            chart, question, similar_cases,
            profile=profile,
            few_shot_examples=few_shot_examples,
        )

        key = (
            self.api_key
            or os.environ.get("DOUYIN_BAZI_AI_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
        )
        if not key:
            return _ensure_domain_analysis(
                _build_mock_result(chart, question, similar_cases, profile)
            )

        base = (
            self.base_url
            or os.environ.get("DOUYIN_BAZI_AI_BASE_URL")
            or os.environ.get("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com/v1"
        ).rstrip("/")
        mdl = (
            self.model
            or os.environ.get("DOUYIN_BAZI_AI_MODEL")
            or os.environ.get("DEEPSEEK_MODEL")
            or "deepseek-chat"
        )

        try:
            import aiohttp
        except ImportError as exc:  # pragma: no cover
            raise ImportError("需要 aiohttp 来调用 DeepSeek API") from exc

        payload = {
            "model": mdl,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 2500,
            "response_format": {"type": "json_object"},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = _parse_json(content, chart)
                parsed.setdefault("basic_info", {}).setdefault("chart", chart)
                _merge_structural_profile(parsed, profile)
                return _ensure_domain_analysis(parsed)


# ── Yearly luck analysis (dayun + liunian) ──

_STEM_ELEMENT = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

_BRANCH_ELEMENT = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

_GENERATING = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_RESTRAINING = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

_PALACE_DOMAIN = {
    "命宫": ("自身根基", "心态与整体气运"),
    "财帛": ("正财偏财", "收入与理财"),
    "兄弟": ("同辈竞争", "合作与分夺"),
    "田宅": ("家庭房产", "居住环境"),
    "男女": ("子女晚辈", "下属关系"),
    "奴仆": ("人际同事", "朋友助力"),
    "夫妻": ("感情婚姻", "配偶关系"),
    "疾厄": ("健康隐患", "身体调养"),
    "迁移": ("外出变动", "远方机遇"),
    "官禄": ("事业地位", "职场发展"),
    "福德": ("精神状态", "福报贵人"),
    "相貌": ("外在形象", "人际第一印象"),
}


async def analyze_yearly(
    chart: str,
    *,
    gender: str = "",
    birth_year: Optional[int] = None,
    mode: str = "10y",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    rule_primer_path: Optional[Path] = None,
    dignity_table: Optional[Dict[str, Dict[str, set]]] = None,
) -> Dict[str, Any]:
    """Analyze yearly luck for a Qi Zheng Si Yu chart.

    *mode* can be ``"10y"`` for the next 10 years, or ``"lifetime"`` for a
    full reading until age 80.

    *dignity_table* selects the planetary dignity tradition used when
    evaluating the palace lord star in the rule-based fallback.  Defaults to
    the built-in table; pass ``star_tables.MIAO_WANG_YANG`` for the Yang
    Guozheng school.
    """
    normalized = _normalize_chart(chart)
    if normalized is None:
        return {
            "error": "无效的命盘格式",
            "dayun_summary": [],
            "yearly_analysis": [],
            "overall_guidance": "",
        }
    chart = normalized

    current_year = datetime.now().year
    birth_year = birth_year or current_year

    dayun = qz_calendar.dayun_list(chart, gender, until_age=80)

    if mode == "10y":
        start_year = current_year
        end_year = current_year + 9
    else:
        start_year = birth_year
        end_year = birth_year + 79

    liunian = qz_calendar.liunian_list(start_year, end_year)

    # Populate start/end years for dayun when birth year is known.
    for d in dayun:
        d["start_year"] = birth_year + int(d["start_age"])
        d["end_year"] = birth_year + int(d["end_age"]) - 1

    # Filter dayun to those overlapping the analyzed years.
    dayun_active = [
        d
        for d in dayun
        if d["end_age"] >= (start_year - birth_year)
        and d["start_age"] <= (end_year - birth_year)
    ]

    primer = ""
    if rule_primer_path is not None and rule_primer_path.exists():
        async with aiofiles.open(rule_primer_path, "r", encoding="utf-8") as handle:
            primer = (await handle.read())[:12000]

    profile = qz_calendar.structural_profile(chart) or {}
    yearly_rels = []
    for y in liunian:
        age = y["year"] - birth_year
        active = next(
            (d for d in dayun_active if d["start_age"] <= age < d["end_age"]),
            dayun_active[-1] if dayun_active else None,
        )
        if active is None:
            continue
        rel = qz_calendar.yearly_relations(chart, active["pillar"], y["pillar"])
        if rel is not None:
            rel["year"] = y["year"]
            rel["age"] = age
            rel["palace"] = active.get("palace", "")
            yearly_rels.append(rel)

    system_prompt = build_yearly_system_prompt(primer)
    user_prompt = build_yearly_user_prompt(
        chart, gender, dayun_active, liunian, mode, profile, yearly_rels, birth_year
    )

    key = (
        api_key
        or os.environ.get("DOUYIN_BAZI_AI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
    )
    if not key:
        return _rule_based_yearly(
            chart,
            dayun_active,
            liunian,
            birth_year,
            profile=profile,
            dignity_table=dignity_table,
        )

    base = (
        base_url
        or os.environ.get("DOUYIN_BAZI_AI_BASE_URL")
        or os.environ.get("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com/v1"
    ).rstrip("/")
    mdl = (
        model
        or os.environ.get("DOUYIN_BAZI_AI_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or "deepseek-chat"
    )

    try:
        import aiohttp
    except ImportError as exc:  # pragma: no cover
        raise ImportError("需要 aiohttp 来调用 DeepSeek API") from exc

    payload = {
        "model": mdl,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.25,
        "max_tokens": 5000,
        "response_format": {"type": "json_object"},
    }

    last_error: Optional[Exception] = None
    for attempt in range(1, 3):
        try:
            timeout = aiohttp.ClientTimeout(total=90)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = _parse_json_yearly(content)
                    if parsed.get("parse_error"):
                        raw_snippet = (parsed.get("raw_content") or "")[:500]
                        logger.warning(
                            "七政流年分析 JSON 解析失败，使用兜底分析。原始输出片段：%s",
                            raw_snippet,
                        )
                        return _rule_based_yearly(
                            chart,
                            dayun_active,
                            liunian,
                            birth_year,
                            Exception(f"AI 输出无法解析，已切换兜底。片段：{raw_snippet}"),
                            profile=profile,
                            dignity_table=dignity_table,
                        )
                    parsed.setdefault("dayun_summary", [])
                    parsed.setdefault("yearly_analysis", [])
                    parsed.setdefault("overall_guidance", "")
                    parsed.setdefault("confidence", "low")
                    parsed["caveats"] = list(parsed.get("caveats", []))
                    parsed["caveats"].append("算法排盘，结果仅供参考")

                    if mode == "lifetime":
                        rule_fallback = _rule_based_yearly(
                            chart,
                            dayun_active,
                            liunian,
                            birth_year,
                            profile=profile,
                            dignity_table=dignity_table,
                        )
                        parsed["yearly_analysis"] = rule_fallback.get("yearly_analysis", [])
                        if not parsed.get("overall_guidance"):
                            parsed["overall_guidance"] = rule_fallback.get("overall_guidance", "")
                        existing = set(parsed["caveats"])
                        for c in rule_fallback.get("caveats", []):
                            if "当前为本地规则分析" in c:
                                continue
                            if c not in existing:
                                parsed["caveats"].append(c)
                                existing.add(c)
                        return parsed

                    return _validate_yearly_output(
                        parsed,
                        chart,
                        dayun_active,
                        liunian,
                        birth_year,
                        profile=profile,
                        dignity_table=dignity_table,
                    )
        except Exception as exc:
            last_error = exc
            logger.warning("七政流年分析请求失败 (attempt %d/2): %s", attempt, exc)
            if attempt < 2:
                await asyncio.sleep(2.0)

    return _rule_based_yearly(
        chart,
        dayun_active,
        liunian,
        birth_year,
        Exception(f"AI 服务暂时不可用：{last_error}"),
        profile=profile,
        dignity_table=dignity_table,
    )


def _parse_json_yearly(content: str) -> Dict[str, Any]:
    """Parse model output as JSON for yearly analysis, with fallback."""
    content = content.strip()
    if not content:
        return {"parse_error": True, "raw_content": ""}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    obj_match = re.search(r"(\{.*\})", content, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except json.JSONDecodeError:
            pass
    return {"parse_error": True, "raw_content": content}


def _validate_yearly_output(
    result: Dict[str, Any],
    chart: str,
    dayun: List[Dict[str, Any]],
    liunian: List[Dict[str, Any]],
    birth_year: int,
    profile: Optional[Dict[str, Any]] = None,
    dignity_table: Optional[Dict[str, Dict[str, set]]] = None,
) -> Dict[str, Any]:
    """Sanity-check yearly output; fall back to rule-based if too generic."""
    yearly = result.get("yearly_analysis", [])
    required = ("year", "pillar", "overview", "career", "wealth", "marriage", "health", "caution")
    if not yearly or len(yearly) < len(liunian) * 0.8 or not all(all(k in y for k in required) for y in yearly):
        logger.warning("七政流年分析字段缺失或年份不足，使用兜底分析")
        return _rule_based_yearly(
            chart,
            dayun,
            liunian,
            birth_year,
            Exception("AI 返回字段缺失或年份不足，已切换兜底"),
            profile=profile,
            dignity_table=dignity_table,
        )
    return result


def _rule_based_yearly(
    chart: str,
    dayun: List[Dict[str, Any]],
    liunian: List[Dict[str, Any]],
    birth_year: int,
    last_error: Optional[Exception] = None,
    profile: Optional[Dict[str, Any]] = None,
    dignity_table: Optional[Dict[str, Dict[str, set]]] = None,
) -> Dict[str, Any]:
    """Return a structured fallback combining dayun and liunian.

    If *profile* contains an ``astro`` section, the original natal bodies are
    used to evaluate the strength of the active palace.  Otherwise the palace
    lord star is evaluated from the branch alone.
    """
    if profile is None:
        profile = qz_calendar.structural_profile(chart) or {}
    day_master_stem = profile.get("day_master", "")
    dm_element = _STEM_ELEMENT.get(day_master_stem, "")

    bodies = (profile.get("astro") or {}).get("bodies", {})

    def _palace_star_info(
        palace: str, branch: str
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str, str]:
        """Return (strongest_star, stars_in_palace, star_impact, lord_relation)."""
        palace_lord = star_tables.PALACE_LORD.get(branch, "")
        stars: List[Dict[str, Any]] = []

        # Natal bodies that fall in this palace (when astro data is available).
        for name, info in bodies.items():
            if info.get("house_palace") == palace:
                stars.append(
                    {
                        "name": name,
                        "strength": info.get("strength", "平"),
                        "dignity": info.get("dignity", "平"),
                        "rulership": info.get("rulership", "不入垣"),
                    }
                )

        # Always include the palace lord, evaluating it from the branch if no
        # astro data is present.
        if palace_lord and not any(s["name"] == palace_lord for s in stars):
            dignity = star_tables.body_dignity(palace_lord, branch, dignity_table)
            rulership = star_tables.body_rulership(palace_lord, branch)
            stars.append(
                {
                    "name": palace_lord,
                    "strength": star_tables.body_strength(
                        palace_lord, branch, "", dignity_table=dignity_table
                    ),
                    "dignity": dignity,
                    "rulership": rulership,
                }
            )

        if not stars:
            strongest = {"name": palace_lord or "", "strength": "平"}
        else:
            stars.sort(key=lambda s: _strength_rank(s["strength"]), reverse=True)
            strongest = {"name": stars[0]["name"], "strength": stars[0]["strength"]}

        # 宫主星与宫位地支的五行生克关系。
        lord_relation = ""
        lord_element = star_tables.BODY_ELEMENT.get(palace_lord)
        branch_element = _BRANCH_ELEMENT.get(branch)
        if lord_element and branch_element:
            if branch_element == lord_element:
                lord_relation = "同气得助"
            elif _GENERATING.get(branch_element) == lord_element:
                lord_relation = "地支生扶"
            elif _RESTRAINING.get(branch_element) == lord_element:
                lord_relation = "地支受克"
            elif _GENERATING.get(lord_element) == branch_element:
                lord_relation = "泄耗地支"
            elif _RESTRAINING.get(lord_element) == branch_element:
                lord_relation = "克制地支"
            else:
                lord_relation = "生克平和"

        focus_a = _PALACE_DOMAIN.get(palace, ("运势", "综合"))[0]
        if strongest["strength"] in ("庙", "旺", "乐", "入垣升殿"):
            impact = f"{palace}宫主{palace_lord}得势，星曜有力，该年{focus_a}顺遂"
        elif strongest["strength"] in ("入垣", "升殿", "得地"):
            impact = f"{palace}宫主{palace_lord}得地，{focus_a}小有助力"
        elif strongest["strength"] == "陷":
            impact = f"{palace}宫主{palace_lord}落陷，该年{focus_a}多阻滞，宜守"
        else:
            impact = f"{palace}宫主{palace_lord}状态平和，按常规节奏即可"

        if lord_relation:
            impact += f"（宫主{palace_lord}与地支{branch}{lord_relation}）"

        return strongest, stars, impact, lord_relation

    def _element_relation(target_element: str) -> str:
        if not dm_element or not target_element:
            return "平"
        if target_element == dm_element:
            return "比劫"
        if _GENERATING.get(dm_element) == target_element:
            return "泄耗"
        if _GENERATING.get(target_element) == dm_element:
            return "生助"
        if _RESTRAINING.get(dm_element) == target_element:
            return "克制"
        if _RESTRAINING.get(target_element) == dm_element:
            return "受克"
        return "平"

    def _branch_interaction(b1: str, b2: str) -> Optional[str]:
        pair = (b1, b2)
        chong = {
            ("子", "午"), ("丑", "未"), ("寅", "申"),
            ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
        }
        he = {
            ("子", "丑"): "土", ("寅", "亥"): "木", ("卯", "戌"): "火",
            ("辰", "酉"): "金", ("巳", "申"): "水", ("午", "未"): "土",
        }
        if pair in chong or pair[::-1] in chong:
            return "冲"
        for h, el in he.items():
            if pair == h or pair[::-1] == h:
                return f"合({el})"
        return None

    def _adjust_star_level_by_relation(level: str, relation: str) -> str:
        """Adjust the star level based on the palace lord's branch relation."""
        if relation in ("同气得助", "地支生扶"):
            if level == "bad":
                return "neutral"
            if level == "neutral":
                return "favourable"
            if level == "favourable":
                return "good"
        if relation == "地支受克":
            if level == "good":
                return "favourable"
            if level in ("favourable", "neutral"):
                return "bad"
        return level

    def _taishui_impact(active_branch: str, liunian_branch: str) -> str:
        """Describe the impact of the yearly branch (tai sui) on the active palace."""
        interaction = _branch_interaction(active_branch, liunian_branch)
        if interaction:
            if interaction.startswith("冲"):
                return f"太岁{liunian_branch}冲{active_branch}宫，变动明显"
            if interaction.startswith("合"):
                return f"太岁{liunian_branch}合{active_branch}宫，机缘人缘增"
        active_el = _BRANCH_ELEMENT.get(active_branch)
        ly_el = _BRANCH_ELEMENT.get(liunian_branch)
        if active_el and ly_el:
            if _GENERATING.get(ly_el) == active_el:
                return f"太岁{liunian_branch}生{active_branch}宫，助力"
            if _RESTRAINING.get(ly_el) == active_el:
                return f"太岁{liunian_branch}克{active_branch}宫，压力"
            if _GENERATING.get(active_el) == ly_el:
                return f"太岁{liunian_branch}泄{active_branch}宫，耗力"
        return f"太岁{liunian_branch}与{active_branch}宫气场平和"

    def _is_day_birth(hour_branch: str) -> Optional[bool]:
        if hour_branch in ("卯", "辰", "巳", "午", "未", "申"):
            return True
        if hour_branch in ("子", "丑", "寅", "酉", "戌", "亥"):
            return False
        return None

    def _four_remainder_overlay(palace: str, hour_branch: str) -> str:
        """Return a short note for four-remainder influences in the active palace."""
        notes: List[str] = []
        day = _is_day_birth(hour_branch)
        for name, info in bodies.items():
            if info.get("house_palace") != palace:
                continue
            if name == "紫气":
                notes.append("紫气临宫，清高福寿")
            elif name == "罗睺":
                if day is True:
                    notes.append("昼生罗睺临宫，防破耗争斗")
                else:
                    notes.append("罗睺临宫，仍有波动")
            elif name == "计都":
                if day is False:
                    notes.append("夜生计都临宫，防暗耗小人")
                else:
                    notes.append("计都临宫，留意阻滞")
            elif name == "月孛":
                notes.append("月孛临宫，感情暗财多变动")
        return "；".join(notes)

    def _pattern_overlay(palace: str) -> str:
        """Return a note if the active palace is affected by classical patterns."""
        pattern_names = {p.get("name", "") for p in profile.get("patterns", [])}
        if "罗计拦截" in pattern_names or "罗计夹命" in pattern_names:
            # Check whether the active palace sits between Rahu and Ketu.
            rah_palace = (bodies.get("罗睺") or {}).get("house_palace")
            ket_palace = (bodies.get("计都") or {}).get("house_palace")
            if rah_palace and ket_palace and palace in (rah_palace, ket_palace):
                return "罗计夹/截此宫，主波折而贵"
        if "土计掩月" in pattern_names and palace in (
            (bodies.get("土星") or {}).get("house_palace"),
            (bodies.get("计都") or {}).get("house_palace"),
            (bodies.get("太阴") or {}).get("house_palace"),
        ):
            return "土计掩月波及此宫，注意健康情绪"
        if "紫气临命" in pattern_names and palace == "命宫":
            return "紫气临命，福寿清高"
        if "紫气朝垣" in pattern_names and palace == "官禄":
            return "紫气朝垣，官福清贵"
        return ""

    def _dayun_theme(palace: str, branch: str) -> Tuple[str, str]:
        domain = _PALACE_DOMAIN.get(palace, ("运势", "综合"))
        element = _BRANCH_ELEMENT.get(branch, "")
        return domain[0], f"{palace}（{branch}，{element}）主{domain[1]}"

    dayun_summary = []
    for d in dayun:
        theme, focus = _dayun_theme(d["palace"], d["pillar"])
        dayun_summary.append(
            {
                "pillar": d["pillar"],
                "palace": d["palace"],
                "start_age": d["start_age"],
                "end_age": d["end_age"],
                "theme": f"{d['palace']}大限，{theme}当令",
                "focus": focus,
            }
        )

    yearly_analysis = []
    for y in liunian:
        age = y["year"] - birth_year
        active = next(
            (d for d in dayun if d["start_age"] <= age < d["end_age"]),
            dayun[-1] if dayun else None,
        )
        if active is None:
            continue

        ly_stem = y["pillar"][0]
        ly_branch = y["pillar"][1]
        ly_stem_rel = _element_relation(_STEM_ELEMENT.get(ly_stem, ""))
        ly_branch_rel = _element_relation(_BRANCH_ELEMENT.get(ly_branch, ""))
        interaction = _branch_interaction(active["pillar"], ly_branch)

        overview_parts = [f"流年{y['pillar']}（{active['palace']}大限）"]
        if interaction:
            overview_parts.append(f"大限宫支与流年支{interaction}")
        else:
            overview_parts.append(f"天干{ly_stem_rel}、地支{ly_branch_rel}")
        overview = "，".join(overview_parts)

        active_palace = active["palace"]
        active_branch = active["pillar"]
        palace_lord = star_tables.PALACE_LORD.get(active_branch, "")
        (
            strongest_star,
            stars_in_palace,
            star_impact,
            lord_relation,
        ) = _palace_star_info(active_palace, active_branch)
        star_level = _star_level_from_strength(strongest_star["strength"])
        if strongest_star.get("name") == palace_lord:
            star_level = _adjust_star_level_by_relation(star_level, lord_relation)

        domains = _yearly_domain_text(
            active_palace,
            ly_stem_rel,
            ly_branch_rel,
            interaction,
            age,
            star_level=star_level,
        )

        taishui = _taishui_impact(active_branch, ly_branch)
        four_note = _four_remainder_overlay(active_palace, profile.get("hour_branch", ""))
        pattern_note = _pattern_overlay(active_palace)
        overlay_notes = " ".join(n for n in (four_note, pattern_note) if n)
        if overlay_notes:
            star_impact += f" [{overlay_notes}]"

        if interaction and interaction.startswith("冲"):
            caution = f"{active_palace}宫逢冲，变动明显；{taishui}"
        elif ly_stem_rel == "受克" or ly_branch_rel == "受克":
            caution = f"流年克耗日主，宜稳守；{taishui}"
        elif ly_stem_rel == "生助" or ly_branch_rel == "生助":
            caution = f"得助之年，可适度进取；{taishui}"
        else:
            caution = f"平运，按部就班；{taishui}"
        if overlay_notes:
            caution += f" [{overlay_notes}]"

        yearly_analysis.append(
            {
                "year": y["year"],
                "pillar": y["pillar"],
                "active_palace": active_palace,
                "palace_lord": palace_lord,
                "palace_lord_relation": lord_relation,
                "stars_in_palace": stars_in_palace,
                "strongest_star": strongest_star,
                "star_impact": star_impact,
                "taishui_impact": taishui,
                "four_remainder_note": four_note,
                "pattern_note": pattern_note,
                "overview": overview,
                "career": domains["career"],
                "wealth": domains["wealth"],
                "marriage": domains["marriage"],
                "health": domains["health"],
                "caution": caution,
            }
        )

    caveats = ["当前为本地规则分析，建议配置稳定 AI 服务以获取更深度流年解读。"]
    if last_error:
        caveats.append(str(last_error))

    return {
        "dayun_summary": dayun_summary,
        "yearly_analysis": yearly_analysis,
        "overall_guidance": "当前为本地规则兜底分析，已将大限宫位与流年干支结合推断；建议配置稳定 AI 服务以获取更深度解读。",
        "confidence": "low",
        "caveats": caveats,
        "_rule_based": True,
    }


_STRENGTH_RANK = {
    "庙": 8,
    "旺": 7,
    "乐": 6,
    "入垣升殿": 5,
    "入垣": 4,
    "升殿": 3,
    "得地": 2,
    "平": 1,
    "陷": 0,
}


def _strength_rank(strength: str) -> int:
    return _STRENGTH_RANK.get(strength, 1)


def _star_level_from_strength(strength: str) -> str:
    if strength in ("庙", "旺", "乐", "入垣升殿"):
        return "good"
    if strength in ("入垣", "升殿", "得地"):
        return "favourable"
    if strength == "陷":
        return "bad"
    return "neutral"


def _yearly_domain_text(
    palace: str,
    stem_rel: str,
    branch_rel: str,
    interaction: Optional[str],
    age: int,
    star_level: str = "neutral",
) -> Dict[str, str]:
    """Generate domain texts for the rule-based yearly fallback."""
    good = stem_rel in ("生助", "比劫") or branch_rel in ("生助", "比劫")
    bad = stem_rel == "受克" or branch_rel == "受克"
    chong = interaction and interaction.startswith("冲")

    if chong:
        level = "chong"
    elif bad:
        level = "bad"
    elif good:
        level = "good"
    else:
        level = "flat"

    # Adjust the base level according to the strength of the palace stars.
    if star_level == "good":
        if level == "bad":
            level = "flat"
        elif level == "flat":
            level = "good"
    elif star_level == "bad":
        if level == "good":
            level = "flat"
        elif level == "flat":
            level = "bad"

    palace_focus = {
        "命宫": ("自身", "心态"),
        "财帛": ("收入", "理财"),
        "兄弟": ("同事", "合作"),
        "田宅": ("家庭", "房产"),
        "男女": ("子女", "下属"),
        "奴仆": ("人际", "朋友"),
        "夫妻": ("感情", "配偶"),
        "疾厄": ("健康", "身体"),
        "迁移": ("外出", "变动"),
        "官禄": ("事业", "职场"),
        "福德": ("精神", "贵人"),
        "相貌": ("形象", "人际"),
    }
    focus_a, focus_b = palace_focus.get(palace, ("综合", "运势"))

    star_note = {
        "good": "，星曜得地助益",
        "favourable": "，星曜小有助力",
        "bad": "，星曜落陷牵制",
        "neutral": "",
    }[star_level]

    templates = {
        "chong": {
            "career": f"{focus_a}宫位逢冲，职场易有变动，重大决策宜缓{star_note}",
            "wealth": f"财务波动，预留备用金，忌高风险投资{star_note}",
            "marriage": f"感情易有口角或距离变化，多沟通{star_note}",
            "health": f"注意突发急症与出行安全{star_note}",
        },
        "bad": {
            "career": f"流年克耗，{focus_a}方面压力增加，以稳为主{star_note}",
            "wealth": f"支出可能增加，控制预算{star_note}",
            "marriage": f"是非稍多，少争执{star_note}",
            "health": f"关注对应脏腑，规律作息{star_note}",
        },
        "good": {
            "career": f"流年得助，{focus_a}方面可主动争取{star_note}",
            "wealth": f"小有进益，量入为出{star_note}",
            "marriage": f"人际和谐，感情宜积极推进{star_note}",
            "health": f"精力充沛，保持运动习惯{star_note}",
        },
        "flat": {
            "career": f"{focus_a}方面按节奏推进{star_note}",
            "wealth": f"量入为出{star_note}",
            "marriage": f"顺其自然{star_note}",
            "health": f"规律作息{star_note}",
        },
    }
    return templates[level]
