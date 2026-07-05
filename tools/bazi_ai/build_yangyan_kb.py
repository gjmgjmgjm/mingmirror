#!/usr/bin/env python3
"""
build_yangyan_kb.py — 将《杨炎八字绝技》PDF 文本整理成本地研究知识库。

注意：本脚本仅用于个人本地研究。生成的文件不会被项目默认加载；如需参考，
请在 config.yml 的 bazi_ai.extra_cases_paths / extra_knowledge_base_paths 中
显式配置，并确保你对原始资料拥有合法使用权。

输入：
    bazi_knowledge/杨炎八字绝技_raw.txt  (已由 pymupdf 提取)
输出：
    bazi_knowledge/杨炎八字绝技_rulebook.md        (完整断六亲规则手册)
    bazi_knowledge/杨炎八字绝技_rulebook_compact.md (精简版)
    bazi_knowledge/杨炎八字绝技_knowledge_final.md  (结构化案例库)
    bazi_knowledge/杨炎八字绝技_cases.jsonl         (结构化 JSONL 案例)
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from bazi_validator import normalize_bazi

RAW_PATH = Path("bazi_knowledge/杨炎八字绝技_raw.txt")
OUT_DIR = Path("bazi_knowledge")


def _is_heading(line: str) -> bool:
    patterns = [
        r"^第[一二三四五六七八九十]+章[：:]",
        r"^第[一二三四五六七八九十]+节",
        r"^\d+\.\d+",
        r"^附录[：:]",
        r"^导论[：:]",
        r"^目录$",
        r"^核心心法[：:]?",
        r"^口诀[：:]?",
        r"^案例\s*\d+",
        r"^[\(（][一二三四五六七八九十]+[\)）]",
    ]
    return any(re.match(p, line.strip()) for p in patterns)


def clean_raw_text(text: str) -> str:
    """Merge broken lines from PDF extraction while preserving headings."""
    text = re.sub(r"===== Page \d+ =====", "", text)
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
    text = re.sub(r"\.{3,}\s*\d+", "", text)

    lines = [ln.rstrip() for ln in text.splitlines()]
    fixed: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.fullmatch(r"\d+\.\d+", line) and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt and not _is_heading(nxt):
                fixed.append(f"{line} {nxt}")
                i += 2
                continue
        fixed.append(line)
        i += 1

    merged: List[str] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf:
            merged.append(buf.strip())
            buf = ""

    for line in fixed:
        line = line.strip()
        if not line:
            flush()
            continue

        if _is_heading(line):
            flush()
            merged.append(line)
            continue

        if re.match(r"^[·●•◦\-\*]\s", line):
            flush()
            merged.append(line)
            continue

        if not buf:
            buf = line
            continue

        if buf[-1] in "。！？":
            flush()
            buf = line
            continue

        if len(line) <= 3 and not re.search(r"[\u4e00-\u9fff]", line):
            flush()
            merged.append(line)
            continue

        if buf[-1].isascii() and line[0].isascii() and buf[-1] not in " (":
            buf += " " + line
        else:
            buf += line

    flush()

    text = "\n".join(merged)
    text = re.sub(
        r"([甲乙丙丁戊己庚辛壬癸])\s*([子丑寅卯辰巳午未申酉戌亥])",
        r"\1\2",
        text,
    )
    text = re.sub(
        r"([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])\s+(?=[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])",
        r"\1 ",
        text,
    )
    return text


BAZI_RE = re.compile(
    r"(?:[乾坤]造[：:]\s*)?"
    r"([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]\s*){3}"
    r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]"
)


def normalize_bazi_in_text(text: str) -> Optional[str]:
    m = BAZI_RE.search(text)
    if not m:
        return None
    raw = m.group(0).replace(" ", "").replace("：", "").replace(":", "")
    raw = re.sub(r"^[乾坤]造", "", raw)
    return normalize_bazi(raw)


def split_into_sections(text: str) -> List[str]:
    parts = re.split(r"(?=第[一二三四五六七八九十]+章[：:])", text)
    return [p.strip() for p in parts if p.strip()]


def _drop_case_details(body: str) -> str:
    """Remove detailed case blocks, keeping only leading theoretical text."""
    parts = re.split(r"(?=案例\s*\d+[\s:：])", body)
    kept = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if _is_case_block_start(part):
            prelude = re.split(r"案例\s*\d+", part, maxsplit=1)[0]
            if len(prelude.strip()) > 50:
                kept.append(prelude.strip())
            continue
        if len(part) < 25 or re.fullmatch(r"[\.\s\d]+", part):
            continue
        kept.append(part)
    return "\n\n".join(kept)


def extract_rulebook(text: str, max_chars: int = 60000) -> str:
    """Build a full rulebook from theoretical chapters and appendix."""
    sections = split_into_sections(text)
    out = ["# 杨炎八字绝技 · 断六亲规则手册\n"]
    out.append(
        "> 来源：《杨炎八字绝技》PDF\n\n"
        "> 作用：作为 AI 八字分析系统 rule_primer 的补充，专精于六亲（父母、兄弟、配偶、子女）论断。\n\n"
        "> 使用方式：在 system_prompt 中作为“基础知识参考”注入，遇到命主询问家庭、父母、婚姻、子女等问题时重点参考。\n"
    )

    intro_match = re.search(r"^(.*?)第[一二三四五六七八九十]+章[：:]", text, re.DOTALL)
    if intro_match:
        intro = intro_match.group(1).strip()
        intro = re.sub(r"^.*?导论", "导论", intro, flags=re.DOTALL)
        if len(intro) > 100:
            out.append("\n## 导论：断六亲的核心思想\n")
            out.append(intro + "\n")

    for sec in sections:
        lines = sec.splitlines()
        if not lines:
            continue
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if len(body) < 80:
            continue
        out.append(f"\n## {heading}\n")
        out.append(_drop_case_details(body) + "\n")

    result = "\n".join(out)
    if len(result) > max_chars:
        result = result[:max_chars]
        last_para = result.rfind("\n\n")
        if last_para > max_chars * 0.8:
            result = result[:last_para]
    return result


def _is_case_block_start(para: str) -> bool:
    """Return True if the paragraph starts with a bullet/heading and a detailed case block."""
    stripped = para.strip().lstrip("·●•◦-*")
    return bool(re.match(r"案例\s*\d+[:：\(]", stripped))


def _extract_appendix_mnemonics(text: str) -> str:
    """Extract the real mnemonic appendix (last occurrence) keeping only口诀lists per section."""
    matches = list(re.finditer(r"附录[：:]杨炎断六亲秘传口诀集锦", text))
    if not matches:
        return ""
    start = matches[-1].end()
    appendix = text[start:].strip()
    closing = re.search(r"最后叮嘱[：:]", appendix)
    if closing:
        appendix = appendix[: closing.start()]

    # Split into sections like 一、父母篇, 二、夫妻篇, ...
    section_heads = [
        r"一、\s*父母篇",
        r"二、\s*夫妻篇",
        r"三、\s*子女篇",
        r"四、\s*兄弟篇",
        r"五、\s*综合篇",
    ]
    section_pattern = "(?=" + "|".join(section_heads) + ")"
    sections = re.split(section_pattern, appendix)

    kept = []
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        # Keep only up to "深度解读与案例" or first "口诀N:" (detailed explanation)
        end_markers = ["深度解读与案例", "口诀1:", "口诀1："]
        cut = len(sec)
        for marker in end_markers:
            idx = sec.find(marker)
            if 0 < idx < cut:
                cut = idx
        sec = sec[:cut].strip()
        # Drop if too short or only preamble
        if len(sec) < 20 or re.fullmatch(r"[一二三四五]、\s*\w+篇", sec):
            continue
        kept.append(sec)
    return "\n\n".join(kept)


def _extract_chapter_core_rules(text: str) -> str:
    """Extract core principle/口诀 paragraphs from each chapter, drop case examples."""
    sections = split_into_sections(text)
    out = []
    for sec in sections:
        lines = sec.splitlines()
        if not lines:
            continue
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if len(body) < 80:
            continue
        out.append(f"\n## {heading}\n")
        # Split at every case marker, including "案例1(..."
        parts = re.split(r"(?=案例\s*\d+[:：\(])", body)
        for part in parts:
            part = part.strip()
            if _is_case_block_start(part):
                continue
            # Drop any part that still mentions a case in its body
            if re.search(r"案例\s*\d+", part):
                continue
            if len(part) < 30:
                continue
            if any(kw in part for kw in ["口诀", "心法", "铁律", "法则", "核心", "原则", "要点", "总结", "提升"]):
                out.append(part + "\n")
    return "\n".join(out)


def extract_compact_rulebook(text: str, max_chars: int = 9000) -> str:
    """Build a compact rulebook: principles -> mnemonics -> chapter core rules."""
    out = ["# 杨炎八字绝技 · 断六亲核心手册（精简版）\n"]
    out.append(
        "> 来源：《杨炎八字绝技》PDF\n\n"
        "> 作用：注入 AI system prompt，提供断六亲的核心法则、口诀与吉凶信号。\n\n"
        "> 提示：遇到父母、兄弟、配偶、子女、婚姻、家庭相关问题时，优先按本手册推理。\n"
    )

    # 1. Core principles (intro)
    intro_match = re.search(r"^(.*?)第[一二三四五六七八九十]+章[：:]", text, re.DOTALL)
    if intro_match:
        intro = intro_match.group(1).strip()
        intro = re.sub(r"^.*?导论", "导论", intro, flags=re.DOTALL)
        intro = re.sub(r"目录.*$", "", intro, flags=re.DOTALL)
        if len(intro) > 80:
            out.append("\n## 核心原则\n")
            out.append(intro[:1200] + "\n")

    # 2. Mnemonics appendix (high value, keep near front)
    mnemonics = _extract_appendix_mnemonics(text)
    if mnemonics:
        out.append("\n## 断六亲秘传口诀集锦\n")
        out.append(mnemonics + "\n")

    # 3. Chapter core rules (will be truncated last)
    out.append(_extract_chapter_core_rules(text))

    result = "\n".join(out)
    if len(result) > max_chars:
        result = result[:max_chars]
        last_para = result.rfind("\n\n")
        if last_para > max_chars * 0.8:
            result = result[:last_para]
    return result


def extract_case_blocks(text: str) -> List[Dict]:
    blocks = re.split(r"(?=案例\s*\d+[\s:：])", text)
    cases = []
    for block in blocks:
        block = block.strip()
        if not block.startswith("案例"):
            continue
        bazi = normalize_bazi_in_text(block)
        if not bazi:
            continue
        gender = "男" if "乾造" in block[:60] else ("女" if "坤造" in block[:60] else "")
        first_line = block.splitlines()[0] if block.splitlines() else ""

        analysis = ""
        analysis_match = re.search(
            r"[●·]?\s*分析[：:]\s*(.*?)(?=\n\s*(?:案例\s*\d+|第[一二三四五六七八九十]+章[：:]|附录[：:]|口诀\d+|核心口诀[：:]))",
            block,
            re.DOTALL,
        )
        if analysis_match:
            analysis = analysis_match.group(1).strip()
        else:
            tail = re.sub(r"^.*?\n", "", block, count=1)
            tail = re.sub(r"^.*?\n", "", tail, count=1)
            analysis = tail.strip()[:1500]

        conclusions = []
        for line in block.splitlines():
            line = line.strip()
            if any(kw in line for kw in ["应期与表现", "特殊点", "结论", "总结", "核心"]):
                conclusions.append(line)

        key_terms = []
        term_keywords = [
            "比劫", "食伤", "财官", "官杀", "印星", "正印", "偏印", "正财", "偏财",
            "正官", "七杀", "伤官", "食神", "比肩", "劫财", "穿害", "六冲", "三刑",
            "合化", "墓库", "旺衰", "用神", "忌神", "身强", "身弱", "从格", "羊刃",
        ]
        for term in term_keywords:
            if term in analysis and term not in key_terms:
                key_terms.append(term)

        cases.append({
            "bazi": bazi,
            "day_master": bazi.split()[2][0] if len(bazi.split()) == 4 else "",
            "month_branch": bazi.split()[1][1] if len(bazi.split()) == 4 else "",
            "source_video": f"杨炎八字绝技-{first_line[:60].strip()}",
            "analysis_raw": analysis,
            "analysis_corrected": analysis,
            "master_feedback": [],
            "key_terms": key_terms,
            "conclusions": conclusions,
            "domains": _extract_domains(analysis),
            "gender": gender,
        })
    return cases


def _extract_domains(text: str) -> Dict[str, List[str]]:
    domains = {
        "career": [],
        "wealth": [],
        "marriage": [],
        "health": [],
        "family": [],
    }
    keywords = {
        "career": ["工作", "事业", "上班", "创业", "职务", "职位", "升迁", "公职"],
        "wealth": ["财", "钱", "富", "收入", "千万", "百万", "赚钱", "资产", "贫困", "小康"],
        "marriage": ["婚姻", "感情", "桃花", "老公", "老婆", "配偶", "恋爱", "分手", "离婚", "夫妻", "妻", "夫"],
        "health": ["病", "健康", "子宫", "妇科", "肾", "血液", "心脏", "手术", "残疾", "夭折", "亡故"],
        "family": ["父母", "父亲", "母亲", "子女", "孩子", "兄弟", "姐妹", "六亲", "祖上", "父", "母"],
    }
    for sentence in re.split(r"[。！？\n]", text):
        sentence = sentence.strip()
        if len(sentence) < 5:
            continue
        for domain, kws in keywords.items():
            if any(kw in sentence for kw in kws):
                domains[domain].append(sentence)
    return {k: v for k, v in domains.items() if v}


def build_knowledge_final_md(cases: List[Dict]) -> str:
    out = ["# 杨炎八字绝技 · 实战案例库\n"]
    out.append(
        "> 来源：《杨炎八字绝技》PDF\n\n"
        "> 说明：每个条目包含一个八字命例与杨炎老师的断六亲分析，用于 RAG 检索。\n"
    )
    for i, case in enumerate(cases, 1):
        out.append(f"\n# 案例{i}：{case['bazi']}（{case.get('gender', '')}命）\n")
        out.append(f"**来源视频**：{case['source_video']}\n")
        if case.get("key_terms"):
            out.append(f"**涉及术语**：{', '.join(case['key_terms'])}\n")
        out.append("\n### 命理师分析\n")
        for line in case["analysis_corrected"].splitlines():
            out.append(f"> {line}\n")
        if case.get("master_feedback"):
            out.append("\n### 命主反馈\n")
            for fb in case["master_feedback"]:
                out.append(f"- {fb}\n")
        if case.get("conclusions"):
            out.append("\n**主要结论**：\n")
            for c in case["conclusions"]:
                out.append(f"- {c}\n")
    return "\n".join(out)


def main():
    raw = RAW_PATH.read_text(encoding="utf-8")
    cleaned = clean_raw_text(raw)

    (OUT_DIR / "杨炎八字绝技_cleaned.txt").write_text(cleaned, encoding="utf-8")

    rulebook = extract_rulebook(cleaned)
    (OUT_DIR / "杨炎八字绝技_rulebook.md").write_text(rulebook, encoding="utf-8")

    compact = extract_compact_rulebook(cleaned)
    (OUT_DIR / "杨炎八字绝技_rulebook_compact.md").write_text(compact, encoding="utf-8")

    mnemonics = _extract_appendix_mnemonics(cleaned)
    if mnemonics:
        mnemonics_doc = (
            "# 杨炎八字绝技 · 断六亲秘传口诀集锦\n\n"
            "> 来源：《杨炎八字绝技》PDF 附录\n\n"
            "> 作用：遇到父母、配偶、子女、兄弟、婚姻、家庭等问题时，快速查阅核心口诀。\n\n"
            + mnemonics
        )
        (OUT_DIR / "杨炎八字绝技_mnemonics.md").write_text(mnemonics_doc, encoding="utf-8")

    cases = extract_case_blocks(cleaned)
    (OUT_DIR / "杨炎八字绝技_cases.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in cases), encoding="utf-8"
    )

    kf_md = build_knowledge_final_md(cases)
    (OUT_DIR / "杨炎八字绝技_knowledge_final.md").write_text(kf_md, encoding="utf-8")

    print(json.dumps({
        "rulebook_chars": len(rulebook),
        "rulebook_compact_chars": len(compact),
        "cases_extracted": len(cases),
        "unique_bazi": len({c['bazi'] for c in cases}),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
