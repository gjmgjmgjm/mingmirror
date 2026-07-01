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

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from tools.qizheng.prompts import build_system_prompt, build_user_prompt
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


def _build_mock_result(chart: str, question: str, similar_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
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

    return {
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


def _domain_keywords(domain: str) -> List[str]:
    mapping = {
        "career": ["事业", "工作", "职业", "创业", "上班", "行业", "升迁"],
        "wealth": ["财", "钱", "富", "收入", "资产", "赚钱"],
        "marriage": ["婚姻", "感情", "桃花", "老公", "老婆", "配偶", "恋爱", "结婚"],
        "health": ["健康", "病", "身体", "手术", "肾", "肝胆", "脾胃"],
    }
    return mapping.get(domain, [])


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
    ):
        self.rule_primer_path = rule_primer_path
        self.cases_path = cases_path
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.top_k = max(0, min(top_k, 10))

    async def analyze(
        self,
        chart_info: Dict[str, Any],
        question: str = "",
    ) -> Dict[str, Any]:
        """Analyze a Qi Zheng Si Yu chart.

        Args:
            chart_info: dict with at least a "bazi" / "chart" key containing
                the four pillars, e.g. "甲子 丙寅 戊辰 庚午".
            question: optional user question.

        Returns:
            Structured analysis result matching the bazi engine schema.
        """
        chart = str(chart_info.get("chart") or chart_info.get("bazi") or "").strip()
        normalized = _normalize_chart(chart)
        if normalized is None:
            return {
                "basic_info": {"chart": chart},
                "error": "无效的命盘格式，需要四柱六十甲子（如：甲子 丙寅 戊辰 庚午）",
                "reasoning": "",
                "domain_analysis": {},
                "summary": [],
                "confidence": "low",
                "caveats": ["输入命盘无法解析为四柱"],
            }

        chart = normalized
        similar_cases = await _retrieve_similar_cases(
            chart, question, self.cases_path, self.top_k
        )
        system_prompt = await build_system_prompt(self.rule_primer_path)
        user_prompt = build_user_prompt(chart, question, similar_cases)

        key = self.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            return _ensure_domain_analysis(_build_mock_result(chart, question, similar_cases))

        base = (
            self.base_url
            or os.environ.get("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com/v1"
        ).rstrip("/")
        mdl = self.model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"

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
                return _ensure_domain_analysis(parsed)
