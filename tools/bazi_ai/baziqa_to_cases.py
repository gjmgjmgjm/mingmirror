#!/usr/bin/env python3
"""Convert BaziQA questions into MingMirror cases.jsonl format.

Each BaziQA question becomes a case record with:
- bazi, day_master, month_branch extracted from the person profile
- source_video set to the BaziQA question_id
- analysis_corrected containing the question, options, correct answer, and domain
- key_terms, conclusions, and domains populated for RAG retrieval
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from tools.bazi_ai.baziqa_eval import load_baziqa, person_to_bazi

_DOMAIN_MAP = {
    "感情": "marriage",
    "财富": "wealth",
    "六亲": "kinship",
    "事业": "career",
    "健康": "health",
}


def _detect_domain(question_text: str, options: List[str]) -> str:
    """Map a BaziQA question to a MingMirror domain."""
    text = question_text + " " + " ".join(options)
    keywords = {
        "marriage": ["结婚", "离婚", "婚姻", "配偶", "妻子", "丈夫", "感情", "桃花", "恋爱"],
        "wealth": ["财", "富", "穷", "钱", "收入", "资产", "投资", "买房", "置业"],
        "career": ["职业", "工作", "事业", "升职", "创业", "公司", "职位", "跳槽"],
        "health": ["病", "疾", "健康", "手术", "医院", "身体", "受伤", "骨折"],
        "kinship": ["父", "母", "子", "女", "兄弟", "姐妹", "六亲", "家庭"],
    }
    scores = {domain: 0 for domain in keywords}
    for domain, kws in keywords.items():
        for kw in kws:
            if kw in text:
                scores[domain] += 1
    return max(scores, key=scores.get) if max(scores.values()) > 0 else "general"


def _build_analysis(
    person: Dict[str, Any],
    question: Dict[str, Any],
    domain: str,
) -> str:
    """Build a concise corrected analysis from a BaziQA Q&A."""
    qtext = question.get("question", "")
    options = question.get("options", [])
    answer = question.get("answer", "")
    answer_idx = ord(answer.upper()) - ord("A") if answer else -1
    answer_text = options[answer_idx] if 0 <= answer_idx < len(options) else ""

    birth = person.get("profile", {}).get("birth", {})
    gender = person.get("profile", {}).get("gender", "")
    gender_label = "男" if gender == "male" else "女" if gender == "female" else ""

    lines = [
        f"命主：{person.get('name', '')}，{gender_label}命",
        f"出生：{birth.get('year')}年{birth.get('month')}月{birth.get('day')}日 {birth.get('hour', 0)}:{birth.get('minute', 0):02d}",
        f"问题：{qtext}",
        "选项：",
    ]
    for i, opt in enumerate(options):
        lines.append(f"  {chr(ord('A') + i)}. {opt}")
    lines.append(f"正确答案：{answer}. {answer_text}")
    lines.append(f"领域：{domain}")
    return "\n".join(lines)


def convert(data_dir: Path) -> List[Dict[str, Any]]:
    """Convert all BaziQA questions to case records."""
    contest_records, celebrity_records = load_baziqa(data_dir)
    records = contest_records + celebrity_records

    cases: List[Dict[str, Any]] = []
    for person in records:
        bazi = person_to_bazi(person)
        if not bazi:
            continue
        day_master = bazi.split()[2][0] if len(bazi.split()) == 4 else ""
        month_branch = bazi.split()[1][1] if len(bazi.split()) == 4 else ""

        for q in person.get("questions", []):
            domain = _detect_domain(q.get("question", ""), q.get("options", []))
            analysis = _build_analysis(person, q, domain)
            options = q.get("options", [])
            answer = q.get("answer", "")
            answer_idx = ord(answer.upper()) - ord("A") if answer else -1
            answer_text = options[answer_idx] if 0 <= answer_idx < len(options) else ""

            case = {
                "bazi": bazi,
                "day_master": day_master,
                "month_branch": month_branch,
                "source_video": q.get("question_id", ""),
                "analysis_raw": analysis,
                "analysis_corrected": analysis,
                "master_feedback": [],
                "key_terms": [q.get("question", "")[:20], answer_text[:20]],
                "conclusions": [f"{q.get('question', '')} 答案：{answer}. {answer_text}"],
                "domains": {domain: [answer_text] if answer_text else []},
            }
            cases.append(case)

    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert BaziQA to MingMirror cases")
    parser.add_argument("--data", default="benchmarks/baziqa/data", help="BaziQA data directory")
    parser.add_argument("--output", default="bazi_knowledge/cases_baziqa.jsonl", help="Output cases file")
    args = parser.parse_args()

    cases = convert(Path(args.data))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    print(f"Converted {len(cases)} BaziQA questions to {output}")


if __name__ == "__main__":
    main()
