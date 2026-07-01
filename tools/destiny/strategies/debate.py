"""Debate strategy: multiple subsystems challenge each other and reach consensus."""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any, Dict, List, Optional

from tools.destiny.contract import ChartInfo, DomainConclusion

_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-chat"


_DEBATE_SYSTEM_PROMPT = """你是一位命理仲裁者。多个命理子系统对同一命盘的不同领域给出了分析，请识别共识与分歧，并输出最终的综合结论。

要求：
1. 对每个领域，选择最合理或支持者最多的结论作为 consensus。
2. 如果所有系统一致，置信度为 high；多数一致但有分歧为 medium；分歧严重为 low。
3. 输出必须是合法 JSON，格式：
{
  "consensus_by_domain": {
    "career": {"text": "...", "confidence": "high|medium|low", "supporting_systems": ["bazi", "ziwei"]},
    ...
  },
  "dissent_summary": "分歧说明"
}
"""


def _build_debate_prompt(
    chart_info: ChartInfo,
    system_conclusions: Dict[str, List[DomainConclusion]],
) -> str:
    payload = {
        "bazi": chart_info.bazi,
        "question": chart_info.question or "全面分析",
        "system_conclusions": {
            system: [c.to_dict() for c in conclusions]
            for system, conclusions in system_conclusions.items()
        },
    }
    return f"""请对以下多系统命理分析进行仲裁。

{json.dumps(payload, ensure_ascii=False, indent=2)}

请按系统提示要求输出 JSON。"""


class DebateStrategy:
    """Run a debate across subsystems and produce a consensus result.

    Without an API key the strategy falls back to a deterministic majority-vote
    consensus with simple textual grouping.
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

    async def debate(
        self,
        chart_info: ChartInfo,
        system_conclusions: Dict[str, List[DomainConclusion]],
    ) -> Dict[str, Any]:
        """Return a dict of consensus conclusions by domain."""
        key = self.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            return self._mock_debate(chart_info, system_conclusions)

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
                {"role": "system", "content": _DEBATE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_debate_prompt(chart_info, system_conclusions),
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
                return parsed.get("consensus_by_domain", {})

    def _mock_debate(
        self,
        chart_info: ChartInfo,
        system_conclusions: Dict[str, List[DomainConclusion]],
    ) -> Dict[str, Any]:
        """Deterministic majority-vote consensus without API calls."""
        by_domain: Dict[str, List[DomainConclusion]] = {}
        for system, conclusions in system_conclusions.items():
            for conclusion in conclusions:
                by_domain.setdefault(conclusion.domain, []).append(conclusion)

        consensus: Dict[str, Any] = {}
        for domain, conclusions in by_domain.items():
            if not conclusions:
                continue
            texts = [c.text for c in conclusions]
            counter = Counter(texts)
            top_text, top_count = counter.most_common(1)[0]
            flat = [
                (system, conclusion)
                for system, conclusion_list in system_conclusions.items()
                for conclusion in conclusion_list
                if conclusion.domain == domain
            ]
            supporting_systems = [
                system for system, conclusion in flat if conclusion.text == top_text
            ]
            total = len(conclusions)
            if top_count == total:
                confidence = "high"
            elif top_count > total / 2:
                confidence = "medium"
            else:
                confidence = "low"
            consensus[domain] = {
                "text": top_text,
                "confidence": confidence,
                "supporting_systems": list(dict.fromkeys(supporting_systems)),
            }

        return consensus

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
