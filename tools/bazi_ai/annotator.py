#!/usr/bin/env python3
"""
annotator.py — automatically annotate bazi cases with structured fields.

For each case missing `pattern`, `day_master_strength`, `useful_gods`, or
`taboo_gods`, we ask the LLM to extract them from the corrected analysis text.
This turns raw transcript cases into labeled retrieval examples, which improves
RAG quality and makes few-shot prompting easier.

Usage:
    python -m tools.bazi_ai.annotator \
        -i bazi_knowledge/cases.jsonl \
        -o bazi_knowledge/cases_annotated.jsonl
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from tools.bazi_ai.bazi_validator import normalize_bazi


def _build_annotation_prompt(bazi: str, analysis: str) -> str:
    return f"""你是一位八字命理标注员。请根据以下命理师分析，提取结构化标签。

八字：{bazi}
命理师分析：{analysis}

请严格按以下 JSON 输出，不要解释：
{{
  "pattern": "格局名称，如 七杀格/伤官格/正官格/财格/印格/身旺无依/从格 等",
  "day_master_strength": "身强|身弱|中和|从旺|从弱",
  "useful_gods": ["用神1", "用神2"],
  "taboo_gods": ["忌神1", "忌神2"]
}}
"""


async def _annotate_case(
    case: Dict,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict:
    """Annotate a single case. Returns a new dict with added fields."""
    result = dict(case)
    bazi = case.get("bazi", "")
    analysis = case.get("analysis_corrected", "") or case.get("analysis_raw", "")
    if not analysis or normalize_bazi(bazi) is None:
        return result

    # Skip if already fully annotated.
    if (
        result.get("pattern")
        and result.get("day_master_strength")
        and result.get("useful_gods")
        and result.get("taboo_gods")
    ):
        return result

    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return result

    base = (base_url or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/")
    mdl = model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"

    try:
        import aiohttp
    except ImportError as exc:  # pragma: no cover
        raise ImportError("需要 aiohttp 来调用 DeepSeek API") from exc

    payload = {
        "model": mdl,
        "messages": [
            {"role": "user", "content": _build_annotation_prompt(bazi, analysis)},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
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
            try:
                annotation = json.loads(content)
            except json.JSONDecodeError:
                return result

            for field in ("pattern", "day_master_strength", "useful_gods", "taboo_gods"):
                if field in annotation and not result.get(field):
                    result[field] = annotation[field]
            return result


async def annotate_cases(
    input_path: Path,
    output_path: Path,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, int]:
    """Annotate all cases in *input_path* and write to *output_path*."""
    cases: List[Dict] = []
    if input_path.exists():
        with input_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        cases.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    annotated = []
    changed = 0
    skipped = 0
    for case in cases:
        if not os.environ.get("DEEPSEEK_API_KEY") and not api_key:
            annotated.append(case)
            skipped += 1
            continue
        new_case = await _annotate_case(
            case,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        annotated.append(new_case)
        if new_case != case:
            changed += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for case in annotated:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    return {
        "total": len(cases),
        "changed": changed,
        "skipped": skipped,
        "output_path": str(output_path),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="自动标注 bazi 案例结构化字段")
    parser.add_argument("-i", "--input", default="./bazi_knowledge/cases.jsonl")
    parser.add_argument("-o", "--output", default="./bazi_knowledge/cases_annotated.jsonl")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    import asyncio

    result = asyncio.run(
        annotate_cases(
            Path(args.input),
            Path(args.output),
            api_key=args.api_key,
            model=args.model,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
