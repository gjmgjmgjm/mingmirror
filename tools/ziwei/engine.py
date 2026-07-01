"""Zi Wei Dou Shu (紫微斗数) analyzer with DeepSeek LLM and mock fallback."""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.ziwei.prompts import build_system_prompt, build_user_prompt, retrieve_cases
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

    async def analyze(
        self,
        chart_info: Dict[str, Any],
        question: str = "",
    ) -> Dict[str, Any]:
        """Analyze a Zi Wei Dou Shu chart asynchronously."""
        validation_error = self._validate_input(chart_info)
        if validation_error:
            return self._error_result(chart_info, validation_error)

        similar_cases = retrieve_cases(
            chart_info,
            question,
            cases_path=self.cases_path,
            top_k=self.top_k,
        )
        system_prompt = build_system_prompt(self.rule_primer_path)
        user_prompt = build_user_prompt(chart_info, question, similar_cases)

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
        """Return an error message if the input is invalid, otherwise None."""
        if not isinstance(chart_info, dict):
            return "chart_info 必须是字典"
        if "birth_datetime" not in chart_info:
            return "缺少 birth_datetime"
        if "gender" not in chart_info:
            return "缺少 gender"
        if chart_info.get("gender") not in ("male", "female"):
            return "gender 必须是 male 或 female"
        location = chart_info.get("location")
        if not isinstance(location, dict):
            return "location 必须是字典"
        for field in ("longitude", "latitude", "timezone"):
            if field not in location:
                return f"location 缺少 {field}"
        try:
            datetime.fromisoformat(str(chart_info["birth_datetime"]).replace("Z", "+00:00"))
        except ValueError:
            return "birth_datetime 格式不正确，应为 ISO 8601"
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
        """Return a deterministic placeholder analysis when no API key is available."""
        gender = chart_info.get("gender", "unknown")
        refs = [c.get("birth_datetime") for c in similar_cases[:2] if c.get("birth_datetime")]

        if str(gender).lower() == "male":
            ming_gong, zhu_xing = "巳宫", ["紫微", "天府"]
        else:
            ming_gong, zhu_xing = "亥宫", ["天同", "天梁"]

        domain_focus = self._detect_question_domains(question)
        default_score = 60
        domain_texts = {
            "career": {
                "score": 78,
                "text": "事业宫主星得力，适合管理、行政或技术岗位，中年后易得贵人提携。",
                "keywords": ["管理", "贵人", "中年后发"],
            },
            "wealth": {
                "score": 65,
                "text": "财帛宫有禄存，正财运稳，但偏财运一般，宜稳健理财。",
                "keywords": ["正财", "稳健", "忌投机"],
            },
            "marriage": {
                "score": 70,
                "text": "夫妻宫主星温和，配偶顾家，宜晚婚更稳。",
                "keywords": ["晚婚", "温和", "顾家"],
            },
            "health": {
                "score": 55,
                "text": "疾厄宫见 minor 煞星，需注意肠胃与肝胆，避免熬夜。",
                "keywords": ["肠胃", "肝胆", "作息"],
            },
            "general": {
                "score": 72,
                "text": "整体格局中上，主星得力，一生有贵人扶助，需注意情绪管理。",
                "keywords": ["贵人", "稳重", "情绪管理"],
            },
        }

        domain_analysis: Dict[str, Dict[str, Any]] = {}
        for domain in ("career", "wealth", "marriage", "health", "general"):
            if domain_focus and domain not in domain_focus:
                domain_analysis[domain] = {
                    "score": default_score,
                    "text": "该领域在 mock 模式下仅作占位，请提供具体问题或配置 API key 后重试。",
                    "keywords": ["待分析"],
                }
            else:
                domain_analysis[domain] = domain_texts[domain]

        return {
            "system": "ziwei",
            "basic_info": {
                "ming_gong": ming_gong,
                "shen_gong": "待 DeepSeek 分析",
                "zhu_xing": zhu_xing,
                "si_hua": ["禄在迁移", "权在事业", "科在财帛", "忌在疾厄"],
            },
            "reasoning": "当前未配置 DEEPSEEK_API_KEY，仅返回 mock 占位分析。请设置环境变量后重试以获取真实紫微斗数排盘与推断。",
            "domain_analysis": domain_analysis,
            "summary": (
                [f"参考相似案例：{', '.join(refs)}"] if refs else ["未找到相似案例"]
            ),
            "confidence": "low",
            "caveats": ["未调用真实模型", "请配置 DEEPSEEK_API_KEY"],
            "raw": {
                "input": chart_info,
                "similar_cases": refs,
                "_mock": True,
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
