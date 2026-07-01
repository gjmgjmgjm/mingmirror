"""Reflection strategy: self-critique and revise a single system's output."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from tools.destiny.contract import ChartInfo

_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-chat"


_REFLECTION_SYSTEM_PROMPT = """你是一位命理分析质量检查员。任务是对给定的命理分析结果进行自我审查，指出事实、逻辑和命理一致性方面的问题，并输出修正后的结构化结果。

审查要点：
1. 八字/命盘结构是否与输入一致。
2. 日主旺衰、用神忌神的判断是否自相矛盾。
3. 各领域结论是否有具体依据，避免空泛。
4. 置信度是否与论证强度匹配，证据不足时应降级。

输出必须是合法 JSON，包含：
- reflection_notes: 审查发现的问题列表
- revised_result: 修正后的完整分析结果（保持原结构）
- confidence_adjusted: 调整后的一级置信度（high/medium/low）
"""


def _build_reflection_prompt(system: str, result: Dict[str, Any], chart_info: ChartInfo) -> str:
    return f"""请审查以下 {system} 系统的命理分析结果。

输入八字：{chart_info.bazi}
提问：{chart_info.question or "全面分析"}

原始分析结果：
{json.dumps(result, ensure_ascii=False, indent=2)}

请按系统提示要求输出 JSON。"""


class ReflectionStrategy:
    """Apply a reflection step to a single system's raw result.

    Without an API key the strategy returns a deterministic mock reflection
    that adds review notes and may downgrade obviously weak confidence.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def reflect(
        self,
        system: str,
        result: Dict[str, Any],
        chart_info: ChartInfo,
    ) -> Dict[str, Any]:
        """Return the result after self-reflection / revision."""
        key = self.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            return self._mock_reflect(system, result, chart_info)

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
                {"role": "system", "content": _REFLECTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_reflection_prompt(system, result, chart_info),
                },
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
                parsed = self._parse_json(content)
                revised = parsed.get("revised_result", result)
                confidence = parsed.get("confidence_adjusted", result.get("confidence", "medium"))
                revised["reflection_notes"] = parsed.get("reflection_notes", [])
                revised["confidence"] = confidence
                revised["_reflection_applied"] = True
                return revised

    def _mock_reflect(
        self,
        system: str,
        result: Dict[str, Any],
        chart_info: ChartInfo,
    ) -> Dict[str, Any]:
        """Deterministic reflection when no API key is available."""
        revised = dict(result)
        notes: list[str] = []

        basic = revised.get("basic_info", {})
        if not basic:
            notes.append("缺少 basic_info，无法验证命盘结构")

        domain_analysis = revised.get("domain_analysis") or {}
        empty_domains = [d for d, v in domain_analysis.items() if not v]
        if empty_domains:
            notes.append(f"以下领域缺少分析：{', '.join(empty_domains)}")

        reasoning = revised.get("reasoning", "")
        if not reasoning or len(reasoning) < 30:
            notes.append("推理过程过短，结论依据不足")

        confidence = revised.get("confidence", "medium")
        if notes and confidence == "high":
            confidence = "medium"
        if len(notes) >= 3 and confidence in ("high", "medium"):
            confidence = "low"

        notes.append("当前为 mock reflection，未调用真实模型")

        revised["reflection_notes"] = notes
        revised["confidence"] = confidence
        revised["_reflection_applied"] = True
        return revised

    def _parse_json(self, content: str) -> Dict[str, Any]:
        content = content.strip()
        if not content:
            return {}
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        import re

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
        return {}
