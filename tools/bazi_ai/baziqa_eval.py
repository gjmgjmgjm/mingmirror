#!/usr/bin/env python3
"""BaziQA benchmark evaluator for MingMirror.

Loads the BaziQA dataset (https://github.com/ChenJiangxi/BaziQA), converts each
person's birth datetime into a bazi chart, asks the configured LLM each
multiple-choice question, and reports accuracy.

The evaluator supports two modes:
- ``baseline``: only the bazi string and the question are provided to the LLM.
- ``enhanced``: the prompt is enriched with structural facts, liuqin facts,
  knowledge-base snippets, and similar cases, mirroring the production engine.

Run::

    python tools/bazi_ai/baziqa_eval.py --data benchmarks/baziqa/data --limit 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

from tools.bazi_ai import bazi_structural, calendar
from tools.bazi_ai.bazi_validator import normalize_bazi
from tools.bazi_ai.engine import retrieve_similar_cases
from tools.bazi_ai.knowledge_retriever import retrieve_knowledge_snippets

_BAZIQA_DATA_URL = "https://github.com/ChenJiangxi/BaziQA/archive/refs/heads/main.zip"


def _ensure_dataset(data_dir: Path) -> None:
    """Download BaziQA dataset if the directory is missing."""
    if data_dir.exists() and any(data_dir.iterdir()):
        return

    import tempfile
    import urllib.request
    import zipfile

    data_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        urllib.request.urlretrieve(_BAZIQA_DATA_URL, tmp.name)
        with zipfile.ZipFile(tmp.name, "r") as zf:
            zf.extractall(data_dir.parent)
        extracted = data_dir.parent / "BaziQA-main"
        if extracted.exists():
            extracted.replace(data_dir)
        os.unlink(tmp.name)


def load_baziqa(data_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load Contest8 and Celebrity50 records from *data_dir*."""
    _ensure_dataset(data_dir)
    contest_records: List[Dict[str, Any]] = []
    celebrity_records: List[Dict[str, Any]] = []

    for path in sorted(data_dir.glob("contest8_*.json")):
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # First element is contest metadata; remaining are persons.
        contest_records.extend(data[1:])

    celeb_path = data_dir / "celebrity50_zh.json"
    if celeb_path.exists():
        with celeb_path.open("r", encoding="utf-8") as f:
            celebrity_records = json.load(f)

    return contest_records, celebrity_records


def person_to_bazi(person: Dict[str, Any]) -> Optional[str]:
    """Convert a BaziQA person profile into a normalized bazi string."""
    birth = person.get("profile", {}).get("birth", {})
    year = birth.get("year")
    month = birth.get("month")
    day = birth.get("day")
    hour = birth.get("hour", 0)
    minute = birth.get("minute", 0)
    if not all(isinstance(v, int) for v in (year, month, day)):
        return None
    dt = datetime(year, month, day, hour, minute)
    pillars = calendar.pillars_for_datetime(dt)
    bazi = f"{pillars['year']} {pillars['month']} {pillars['day']} {pillars['hour']}"
    normalized = normalize_bazi(bazi)
    return normalized if normalized else bazi


def _format_options(options: List[str]) -> str:
    labels = ["A", "B", "C", "D"]
    return "\n".join(f"{labels[i]}. {opt}" for i, opt in enumerate(options[:4]))


def _extract_answer(text: str) -> Optional[str]:
    """Extract the first A/B/C/D letter from *text*."""
    if not text:
        return None
    # Look for isolated letters first.
    match = re.search(r"\b([A-D])\b", text.upper())
    if match:
        return match.group(1)
    return None


async def _call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 500,
    timeout_seconds: float = 30.0,
) -> str:
    """Lightweight LLM call returning raw text."""
    key = api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DOUYIN_BAZI_AI_API_KEY")
    if not key:
        raise RuntimeError("No API key configured for BaziQA evaluation")
    if aiohttp is None:  # pragma: no cover
        raise ImportError("aiohttp is required for LLM calls")

    base = (
        base_url
        or os.environ.get("DEEPSEEK_BASE_URL")
        or os.environ.get("DOUYIN_BAZI_AI_BASE_URL")
        or "https://api.deepseek.com/v1"
    ).rstrip("/")
    mdl = model or os.environ.get("DEEPSEEK_MODEL") or os.environ.get("DOUYIN_BAZI_AI_MODEL") or "deepseek-chat"

    payload = {
        "model": mdl,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
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
            return data["choices"][0]["message"]["content"]


def _build_baseline_prompt(question: str, options: List[str]) -> str:
    return f"""请根据八字命理知识回答以下选择题。

问题：{question}

{_format_options(options)}

请只回答选项字母（A/B/C/D），不要输出任何解释。"""


async def _build_enhanced_context(
    bazi: str,
    question: str,
    *,
    gender: str,
    birth_date: str,
    birth_time: str,
    cases_path: Optional[Path] = None,
    knowledge_base_path: Optional[Path] = None,
    embedding_cache_path: Optional[Path] = None,
    knowledge_embedding_cache_path: Optional[Path] = None,
    top_k: int = 3,
) -> str:
    """Build the same enrichment used by the production engine."""
    similar_cases = await retrieve_similar_cases(
        bazi,
        question,
        cases_path or Path("./bazi_knowledge/cases.jsonl"),
        top_k=top_k,
        embedding_cache_path=embedding_cache_path,
    )

    knowledge_paths = [Path("./bazi_knowledge/rule_primer.md")]
    if knowledge_base_path is not None and knowledge_base_path.exists():
        knowledge_paths.append(knowledge_base_path)

    knowledge_context = await retrieve_knowledge_snippets(
        query=f"{bazi}\n{question}".strip(),
        knowledge_paths=knowledge_paths,
        cache_path=knowledge_embedding_cache_path,
        top_k=6,
        max_chars=8000,
    )

    structural_facts = bazi_structural.structural_profile(bazi) or {}
    liuqin_facts = bazi_structural.liuqin_profile(bazi, gender=gender) or {}

    cases_text = "\n\n".join(
        f"案例 {i+1}：\n八字：{c.get('bazi')}\n分析：{c.get('analysis_corrected', '')[:500]}"
        for i, c in enumerate(similar_cases)
    )

    return f"""【命局结构事实】
- 日主：{structural_facts.get('day_master', '')}
- 月令：{structural_facts.get('month_branch', '')}
- 天干十神：{structural_facts.get('stem_shishen', {})}
- 地支十神（本气）：{structural_facts.get('branch_shishen', {})}
- 参考旺衰：{structural_facts.get('strength', '')}
- 参考用神：{structural_facts.get('useful_gods', '')}
- 参考忌神：{structural_facts.get('taboo_gods', '')}
- 地支综合关系：{structural_facts.get('di_zhi_comprehensive_text', '无')}

【六亲星宫事实】
{json.dumps(liuqin_facts, ensure_ascii=False, indent=2)}

【相关知识片段】
{knowledge_context}

【参考案例】
{cases_text}
"""


async def _build_enhanced_prompt(
    bazi: str,
    question: str,
    options: List[str],
    context: str,
) -> str:
    return f"""你是一位资深命理师。请根据以下命局信息回答选择题。

八字：{bazi}

{context}

问题：{question}

{_format_options(options)}

请只回答选项字母（A/B/C/D），不要输出任何解释。"""


async def evaluate_question(
    bazi: str,
    question: Dict[str, Any],
    *,
    mode: str = "enhanced",
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    cases_path: Optional[Path] = None,
    knowledge_base_path: Optional[Path] = None,
    embedding_cache_path: Optional[Path] = None,
    knowledge_embedding_cache_path: Optional[Path] = None,
    mock_answer: Optional[str] = None,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """Evaluate a single BaziQA question and return prediction + metadata."""
    qid = question.get("question_id", "")
    qtext = question.get("question", "")
    options = question.get("options", [])
    answer = question.get("answer", "")

    raw = ""
    error = None
    try:
        if mock_answer is not None:
            raw = mock_answer
        elif mode == "baseline":
            system_prompt = "你是一位精通中国传统八字命理的命理师。"
            user_prompt = _build_baseline_prompt(qtext, options)
            raw = await _call_llm(
                system_prompt,
                user_prompt,
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
            )
        else:
            context = await _build_enhanced_context(
                bazi,
                qtext,
                gender=gender,
                birth_date=birth_date,
                birth_time=birth_time,
                cases_path=cases_path,
                knowledge_base_path=knowledge_base_path,
                embedding_cache_path=embedding_cache_path,
                knowledge_embedding_cache_path=knowledge_embedding_cache_path,
            )
            system_prompt = "你是一位精通中国传统八字命理的命理师。"
            user_prompt = await _build_enhanced_prompt(bazi, qtext, options, context)
            raw = await _call_llm(
                system_prompt,
                user_prompt,
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
            )
    except Exception as exc:  # pragma: no cover - safety net for live API
        error = f"{type(exc).__name__}: {exc}"

    predicted = _extract_answer(raw) or ""
    result: Dict[str, Any] = {
        "question_id": qid,
        "question": qtext,
        "bazi": bazi,
        "answer": answer,
        "predicted": predicted,
        "correct": predicted == answer,
        "raw": raw,
        "mode": mode,
    }
    if error:
        result["error"] = error
    return result


def _birth_date_time(person: Dict[str, Any]) -> Tuple[str, str]:
    birth = person.get("profile", {}).get("birth", {})
    date_parts = [
        str(birth.get("year", "")),
        str(birth.get("month", "")).zfill(2),
        str(birth.get("day", "")).zfill(2),
    ]
    birth_date = "-".join(date_parts) if all(p for p in date_parts) else ""
    hour = str(birth.get("hour", 0)).zfill(2)
    minute = str(birth.get("minute", 0)).zfill(2)
    birth_time = f"{hour}:{minute}"
    return birth_date, birth_time


async def run_evaluation(
    data_dir: Path,
    *,
    mode: str = "enhanced",
    limit: Optional[int] = None,
    offset: int = 0,
    datasets: Optional[List[str]] = None,
    output: Optional[Path] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    cases_path: Optional[Path] = None,
    knowledge_base_path: Optional[Path] = None,
    embedding_cache_path: Optional[Path] = None,
    knowledge_embedding_cache_path: Optional[Path] = None,
    mock_answer: Optional[str] = None,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """Run BaziQA evaluation across selected datasets.

    Args:
        data_dir: directory containing contest8_*.json and celebrity50_zh.json.
        mode: "baseline" or "enhanced".
        limit: optional max number of questions to evaluate.
        offset: number of questions to skip from the start.
        datasets: list of dataset names to include (e.g. ["contest8", "celebrity50"]).
        output: optional path to write JSONL predictions.
        mock_answer: if set, bypass LLM and use this letter for every question.
        timeout_seconds: per-question LLM timeout.
    """
    contest_records, celebrity_records = load_baziqa(data_dir)
    datasets = datasets or ["contest8", "celebrity50"]

    records: List[Dict[str, Any]] = []
    if "contest8" in datasets:
        records.extend(contest_records)
    if "celebrity50" in datasets:
        records.extend(celebrity_records)

    questions: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for person in records:
        for q in person.get("questions", []):
            questions.append((person, q))

    if offset > 0:
        questions = questions[offset:]
    if limit is not None and limit > 0:
        questions = questions[:limit]

    results: List[Dict[str, Any]] = []
    correct = 0
    for person, q in questions:
        bazi = person_to_bazi(person)
        if not bazi:
            results.append(
                {
                    "question_id": q.get("question_id"),
                    "error": "无法从 profile 生成八字",
                    "correct": False,
                }
            )
            continue

        birth_date, birth_time = _birth_date_time(person)
        gender = person.get("profile", {}).get("gender", "male")
        result = await evaluate_question(
            bazi,
            q,
            mode=mode,
            gender=gender,
            birth_date=birth_date,
            birth_time=birth_time,
            api_key=api_key,
            base_url=base_url,
            model=model,
            cases_path=cases_path,
            knowledge_base_path=knowledge_base_path,
            embedding_cache_path=embedding_cache_path,
            knowledge_embedding_cache_path=knowledge_embedding_cache_path,
            mock_answer=mock_answer,
            timeout_seconds=timeout_seconds,
        )
        results.append(result)
        if result.get("correct"):
            correct += 1

    accuracy = correct / len(results) if results else 0.0
    summary = {
        "mode": mode,
        "datasets": datasets,
        "total": len(results),
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "results": results,
    }

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        summary["output_path"] = str(output)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate MingMirror bazi AI on BaziQA")
    parser.add_argument("--data", default="benchmarks/baziqa/data", help="BaziQA data directory")
    parser.add_argument("--mode", choices=["baseline", "enhanced"], default="enhanced")
    parser.add_argument("--datasets", nargs="+", choices=["contest8", "celebrity50"], default=None)
    parser.add_argument("--limit", type=int, default=None, help="Max questions to evaluate")
    parser.add_argument("--offset", type=int, default=0, help="Questions to skip")
    parser.add_argument("--output", default=None, help="Output JSONL path for predictions")
    parser.add_argument("--api-key", default=None, help="LLM API key")
    parser.add_argument("--base-url", default=None, help="LLM API base URL")
    parser.add_argument("--model", default=None, help="LLM model name")
    parser.add_argument("--mock-answer", default=None, help="Use fixed letter for every question (for testing)")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-question LLM timeout in seconds")
    args = parser.parse_args()

    summary = asyncio.run(
        run_evaluation(
            Path(args.data),
            mode=args.mode,
            limit=args.limit,
            offset=args.offset,
            datasets=args.datasets,
            output=Path(args.output) if args.output else None,
            api_key=args.api_key,
            base_url=args.base_url,
            model=args.model,
            mock_answer=args.mock_answer,
            timeout_seconds=args.timeout,
        )
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
