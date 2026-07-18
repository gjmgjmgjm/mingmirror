"""Zi Wei Dou Shu (紫微斗数) analyzer with DeepSeek LLM and mock fallback."""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.ziwei.prompts import (
    build_system_prompt,
    build_user_prompt,
    retrieve_cases,
)
from utils.logger import setup_logger

logger = setup_logger("ZiWeiAnalyzer")

_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-chat"


class ZiWeiAnalyzer:
    """Analyzer for Zi Wei Dou Shu charts.

    If no DeepSeek API key is provided (via argument or environment), a deterministic
    mock fallback is returned so tests and offline usage do not depend on the network.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        rule_primer_path: Optional[Path] = None,
        cases_path: Optional[Path] = None,
        top_k: int = 3,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.top_k = max(0, min(top_k, 10))

        package_dir = Path(__file__).resolve().parent
        self.rule_primer_path = rule_primer_path or package_dir / "rule_primer.md"
        self.cases_path = cases_path or package_dir / "cases.jsonl"
        self.examples_path = package_dir / "examples.jsonl"

    async def analyze(
        self,
        chart_info: Dict[str, Any],
        question: str = "",
    ) -> Dict[str, Any]:
        """Analyze a Zi Wei Dou Shu chart asynchronously."""
        validation_error = self._validate_input(chart_info)
        if validation_error:
            return self._error_result(chart_info, validation_error)

        similar_cases = await retrieve_cases(
            chart_info,
            question,
            cases_path=self.cases_path,
            top_k=self.top_k,
        )
        system_prompt = await build_system_prompt(self.rule_primer_path)
        from tools.ziwei.prompts import _load_few_shot_examples

        few_shot_examples = _load_few_shot_examples(self.examples_path)
        user_prompt = build_user_prompt(
            chart_info, question, similar_cases, few_shot_examples=few_shot_examples
        )

        key = self.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            logger.info("DEEPSEEK_API_KEY not configured; returning mock Zi Wei analysis")
            return self._mock_analyze(chart_info, question, similar_cases)

        base = (
            self.base_url
            or os.environ.get("DEEPSEEK_BASE_URL")
            or _DEFAULT_BASE_URL
        ).rstrip("/")
        mdl = self.model or os.environ.get("DEEPSEEK_MODEL") or _DEFAULT_MODEL

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
                parsed = self._parse_json(content, chart_info)
                return self._validate_output(parsed, chart_info)

    def analyze_sync(
        self,
        chart_info: Dict[str, Any],
        question: str = "",
    ) -> Dict[str, Any]:
        """Synchronous wrapper around :meth:`analyze`."""
        return asyncio.run(self.analyze(chart_info, question))

    def _validate_input(self, chart_info: Dict[str, Any]) -> Optional[str]:
        """Return an error message if the input is invalid, otherwise None.

        Product path may supply only ``bazi`` + ``gender`` for structure-layer
        charting; full birth_datetime+location still preferred for LLM path.
        """
        if not isinstance(chart_info, dict):
            return "chart_info 必须是字典"
        has_bazi = bool((chart_info.get("bazi") or chart_info.get("chart") or "").strip())
        has_birth = bool(chart_info.get("birth_datetime"))
        if not has_bazi and not has_birth:
            return "缺少 bazi 或 birth_datetime"
        gender = chart_info.get("gender")
        if gender is not None and gender not in ("male", "female", "男", "女"):
            return "gender 必须是 male 或 female"
        if has_birth:
            try:
                datetime.fromisoformat(
                    str(chart_info["birth_datetime"]).replace("Z", "+00:00")
                )
            except ValueError:
                return "birth_datetime 格式不正确，应为 ISO 8601"
            location = chart_info.get("location")
            if location is not None and not isinstance(location, dict):
                return "location 必须是字典"
        return None

    def _error_result(
        self,
        chart_info: Dict[str, Any],
        error: str,
    ) -> Dict[str, Any]:
        return {
            "system": "ziwei",
            "basic_info": {},
            "domain_analysis": {},
            "confidence": "low",
            "raw": {"input": chart_info, "error": error},
        }

    def _mock_analyze(
        self,
        chart_info: Dict[str, Any],
        question: str,
        similar_cases: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Structure-layer chart + domain hints when no API key is available."""
        from tools.ziwei.chart import chart_from_birth, to_basic_info

        gender = chart_info.get("gender", "male")
        if gender in ("男",):
            gender = "male"
        if gender in ("女",):
            gender = "female"
        bazi = (chart_info.get("bazi") or chart_info.get("chart") or "").strip()
        birth_date = ""
        bdt = chart_info.get("birth_datetime") or ""
        if isinstance(bdt, str) and len(bdt) >= 10:
            birth_date = bdt[:10]
        birth_date = chart_info.get("birth_date") or birth_date

        struct = chart_from_birth(bazi, gender=str(gender), birth_date=birth_date) if bazi else None
        refs = [c.get("birth_datetime") for c in similar_cases[:2] if c.get("birth_datetime")]

        if struct:
            basic = to_basic_info(struct)
            domain_raw = struct.get("domain_analysis") or {}
            domain_analysis = {
                k: {
                    "score": 70 if k != "health" else 60,
                    "text": domain_raw.get(k, ""),
                    "keywords": [],
                }
                for k in ("career", "wealth", "marriage", "health", "general")
            }
            cur = struct.get("current_limit") or {}
            summary = [
                f"命宫{struct.get('life_palace')} · 身宫{struct.get('body_palace')} · {struct.get('bureau_label')}",
                f"命宫主星：{'、'.join(struct.get('zhu_xing') or [])}"
                + (
                    f"；辅{'、'.join(struct.get('ming_aux') or [])}"
                    if struct.get("ming_aux")
                    else ""
                ),
                f"年干四化：{'；'.join(struct.get('si_hua') or [])}",
            ]
            if cur:
                summary.append(
                    f"当前大限{cur.get('label')}走{cur.get('branch')}"
                    f"（{struct.get('limit_direction') or ''}）"
                )
            if refs:
                summary.append(f"参考相似案例：{', '.join(str(r) for r in refs)}")
            reasoning = (
                "结构层已完成安命身宫、五行局、紫微/天府系主星与年干四化（确定性简化算法）。"
                "未配置 DEEPSEEK_API_KEY，领域断语为宫位主星提示，非完整斗数精批。"
            )
            caveats = [
                "结构层 certain_simplified",
                struct.get("note") or "",
                "配置 DEEPSEEK_API_KEY 可叠加 LLM 细批",
            ]
        else:
            basic = {
                "ming_gong": "未知",
                "shen_gong": "未知",
                "zhu_xing": [],
                "si_hua": [],
            }
            domain_analysis = {
                k: {"score": 50, "text": "八字不足，无法排盘。", "keywords": []}
                for k in ("career", "wealth", "marriage", "health", "general")
            }
            summary = ["无法从输入生成紫微结构盘"]
            reasoning = "缺少有效四柱八字。"
            caveats = ["invalid_bazi"]
            struct = {}

        return {
            "system": "ziwei",
            "basic_info": basic,
            "structural": struct,
            "reasoning": reasoning,
            "domain_analysis": domain_analysis,
            "summary": summary,
            "confidence": "medium" if struct else "low",
            "caveats": [c for c in caveats if c],
            "raw": {
                "input": chart_info,
                "similar_cases": refs,
                "_mock": True,
                "_structural": True,
            },
        }

    def _validate_output(
        self,
        result: Dict[str, Any],
        chart_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Sanity-check model output and ensure required fields exist."""
        if not isinstance(result, dict):
            result = {"raw_content": str(result)}

        result.setdefault("system", "ziwei")
        result.setdefault("basic_info", {})
        result.setdefault("domain_analysis", {})
        result.setdefault("confidence", "medium")
        result.setdefault("raw", {})

        expected_domains = ("career", "wealth", "marriage", "health", "general")
        for domain in expected_domains:
            domain_data = result["domain_analysis"].get(domain)
            if not isinstance(domain_data, dict):
                result["domain_analysis"][domain] = {
                    "score": 50,
                    "text": "模型未返回该领域分析。",
                    "keywords": [],
                }
            else:
                domain_data.setdefault("score", 50)
                domain_data.setdefault("text", "")
                domain_data.setdefault("keywords", [])
                score = domain_data["score"]
                try:
                    score = max(0, min(100, int(score)))
                except (TypeError, ValueError):
                    score = 50
                domain_data["score"] = score

        caveats = list(result.get("caveats", []))
        if not result.get("basic_info"):
            caveats.append("模型未返回 basic_info")
        if result["confidence"] not in ("high", "medium", "low"):
            caveats.append(f"模型置信度 {result.get('confidence')} 不在 high/medium/low 中，已修正为 medium")
            result["confidence"] = "medium"
        if caveats:
            result["caveats"] = caveats

        result["raw"]["input"] = chart_info
        return result

    def _parse_json(
        self,
        content: str,
        chart_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Parse model output as JSON, with fallbacks."""
        content = content.strip()
        if not content:
            return {
                "system": "ziwei",
                "basic_info": {},
                "parse_error": True,
                "raw_content": "",
            }

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

        return {
            "system": "ziwei",
            "basic_info": {},
            "parse_error": True,
            "raw_content": content,
        }

    @staticmethod
    def _detect_question_domains(question: str) -> List[str]:
        """Return life domains mentioned in the question."""
        if not question:
            return []
        keywords = {
            "career": ["事业", "工作", "职业", "创业", "上班", "行业", "升迁", "贵人"],
            "wealth": ["财", "钱", "富", "收入", "资产", "赚钱", "百万", "千万", "小康"],
            "marriage": ["婚姻", "感情", "桃花", "老公", "老婆", "配偶", "恋爱", "结婚", "离婚"],
            "health": ["健康", "病", "身体", "手术", "肾", "妇科", "心脏", "血液", "子宫"],
            "general": ["运势", "命运", "命盘", "整体", "综合", "运程", "运气"],
        }
        domains = []
        for domain, kws in keywords.items():
            if any(kw in question for kw in kws):
                domains.append(domain)
        return domains
