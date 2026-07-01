#!/usr/bin/env python3
"""
case_builder.py — 把现有 bazi_knowledge/*.md 解析成结构化案例库。

输入：
    bazi_knowledge/杨炎_knowledge_final.md 等
输出：
    bazi_knowledge/cases.jsonl

每个案例包含：
    bazi, day_master, month_branch, source_video, analysis_text,
    key_terms, conclusions, 以及从文本中启发式抽取的领域信息。
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from tools.bazi_ai.bazi_validator import (
    day_master as validate_day_master,
)
from tools.bazi_ai.bazi_validator import (
    month_branch as validate_month_branch,
)
from tools.bazi_ai.bazi_validator import (
    normalize_bazi,
)


def load_glossary(glossary_path: Path) -> Dict[str, str]:
    if not glossary_path.exists():
        return {}
    with glossary_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {k.strip(): v.strip() for k, v in data.items() if k.strip()}


def correct_text(text: str, glossary: Dict[str, str]) -> str:
    # Sort by length descending to avoid partial replacements.
    for wrong in sorted(glossary, key=len, reverse=True):
        text = text.replace(wrong, glossary[wrong])
    return text


BAZI_RE = re.compile(
    r"([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]\s*){3}"
    r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]"
)


def extract_bazi(text: str) -> Optional[str]:
    match = BAZI_RE.search(text)
    if not match:
        return None
    raw = match.group(0).replace(" ", "")
    return " ".join(raw[i : i + 2] for i in range(0, 8, 2))


def extract_day_master(bazi: str) -> Optional[str]:
    return validate_day_master(bazi)


def extract_month_branch(bazi: str) -> Optional[str]:
    return validate_month_branch(bazi)


def parse_knowledge_md(md_path: Path, glossary: Dict[str, str]) -> List[Dict]:
    """Parse the v3-style knowledge base markdown into structured cases."""
    content = md_path.read_text(encoding="utf-8")
    # Split by "# " headings that contain a bazi.
    blocks = re.split(r"\n# ", content)
    cases = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # Only real cases have an advisor analysis section.
        if "### 命理师分析" not in block:
            continue
        raw_bazi = extract_bazi(block)
        bazi = normalize_bazi(raw_bazi)
        if not bazi:
            continue

        # Source video line.
        source_match = re.search(r"\*\*来源视频\*\*：(.+)", block)
        source_video = source_match.group(1).strip() if source_match else ""

        # Advisor analysis: lines after "> " under ### 命理师分析
        analysis_lines = []
        advisor_section = re.search(
            r"### 命理师分析\s*\n+((?:> .+\n|\n)+)", block
        )
        if advisor_section:
            for line in advisor_section.group(1).splitlines():
                line = line.strip()
                if line.startswith("> "):
                    analysis_lines.append(line[2:].strip())

        # Master feedback.
        feedback_lines = []
        feedback_section = re.search(
            r"### 命主反馈\s*\n+((?:- .+\n|\n)+)", block
        )
        if feedback_section:
            for line in feedback_section.group(1).splitlines():
                line = line.strip()
                if line.startswith("- "):
                    feedback_lines.append(line[2:].strip())

        # Key terms.
        key_terms = []
        terms_match = re.search(r"\*\*涉及术语\*\*：(.+)", block)
        if terms_match:
            key_terms = [t.strip() for t in re.split(r"[,，]", terms_match.group(1)) if t.strip()]

        # Conclusions.
        conclusions = []
        conclusions_match = re.search(r"\*\*主要结论\*\*：\s*\n+((?:- .+\n|\n)+)", block)
        if conclusions_match:
            for line in conclusions_match.group(1).splitlines():
                line = line.strip()
                if line.startswith("- "):
                    conclusions.append(line[2:].strip())

        raw_analysis = "\n".join(analysis_lines)
        corrected_analysis = correct_text(raw_analysis, glossary)

        cases.append({
            "bazi": bazi,
            "day_master": extract_day_master(bazi),
            "month_branch": extract_month_branch(bazi),
            "source_video": source_video,
            "analysis_raw": raw_analysis,
            "analysis_corrected": corrected_analysis,
            "master_feedback": [correct_text(f, glossary) for f in feedback_lines],
            "key_terms": key_terms,
            "conclusions": [correct_text(c, glossary) for c in conclusions],
            "domains": _extract_domains(corrected_analysis),
        })
    return cases


def _extract_domains(text: str) -> Dict[str, List[str]]:
    """Heuristically extract domain-specific sentences."""
    domains = {
        "career": [],
        "wealth": [],
        "marriage": [],
        "health": [],
        "family": [],
    }
    keywords = {
        "career": ["工作", "事业", "上班", "创业", "职务", "职位", "升迁", "贵人"],
        "wealth": ["财", "钱", "富", "收入", "千万", "百万", "赚钱", "资产"],
        "marriage": ["婚姻", "感情", "桃花", "老公", "老婆", "配偶", "恋爱", "分手", "离婚"],
        "health": ["病", "健康", "子宫", "妇科", "肾", "血液", "心脏", "手术"],
        "family": ["父母", "父亲", "母亲", "子女", "孩子", "兄弟", "姐妹"],
    }
    for sentence in re.split(r"[。！？\n]", text):
        sentence = sentence.strip()
        if len(sentence) < 5:
            continue
        for domain, kws in keywords.items():
            if any(kw in sentence for kw in kws):
                domains[domain].append(sentence)
    return {k: v for k, v in domains.items() if v}


def build_case_database(
    knowledge_dir: Path,
    output_path: Path,
    glossary_path: Optional[Path] = None,
    dedup_key: str = "bazi",
) -> Dict[str, int]:
    """Build and save the structured case database.

    Invalid bazi records are dropped, and duplicates are removed based on
    *dedup_key* (default: ``bazi``). Set *dedup_key* to ``source_video`` to
    keep multiple readings of the same chart, or ``bazi`` to collapse them.
    """
    glossary = load_glossary(glossary_path or knowledge_dir.parent / "bazi_glossary.json")
    all_cases = []
    source_counts = {}
    invalid_count = 0

    for md_path in sorted(knowledge_dir.glob("*_knowledge_final.md")):
        cases = parse_knowledge_md(md_path, glossary)
        valid_cases = []
        for case in cases:
            if normalize_bazi(case.get("bazi", "")):
                valid_cases.append(case)
            else:
                invalid_count += 1
        all_cases.extend(valid_cases)
        source_counts[md_path.name] = len(valid_cases)

    # Deduplicate while preserving source order.
    seen = set()
    deduped = []
    for case in all_cases:
        key = case.get(dedup_key, case["bazi"])
        if key not in seen:
            seen.add(key)
            deduped.append(case)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for case in deduped:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    return {
        "total_cases": len(deduped),
        "raw_cases": len(all_cases),
        "invalid_cases": invalid_count,
        "unique_bazi": len({c["bazi"] for c in deduped}),
        "sources": source_counts,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build structured bazi case database")
    parser.add_argument("-k", "--knowledge-dir", default="./bazi_knowledge", help="知识库目录")
    parser.add_argument("-o", "--output", default="./bazi_knowledge/cases.jsonl", help="输出路径")
    parser.add_argument("-g", "--glossary", default="./bazi_glossary.json", help="纠错词表")
    args = parser.parse_args()

    summary = build_case_database(
        Path(args.knowledge_dir),
        Path(args.output),
        Path(args.glossary) if args.glossary else None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
