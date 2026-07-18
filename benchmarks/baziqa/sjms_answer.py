#!/usr/bin/env python3
"""SJMS benchmark MCQ answering.

命镜负责确定性排盘（四柱 + 大运 + 流年，sxtwl 纯计算），deepseek 只做
最后的应期选项判断。每题一次轻量调用，可并发。

Usage:
    DEEPSEEK_API_KEY=... python benchmarks/baziqa/sjms_answer.py paper.json
writes sjms_answers.json ({id: "A"/"B"/"C"/"D"}) + sjms_debug.json (raw tails).
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai import calendar, bazi_structural  # noqa: E402
from tools.ziwei.chart import chart_from_birth  # noqa: E402

API_KEY = os.environ.get("DEEPSEEK_API_KEY") or "sk-e8852c4cc2d24c4ca47f6efff4d93c6f"
BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def bazi_from_birth(b) -> str:
    if not b or not b.get("year") or not b.get("month") or not b.get("day"):
        return ""
    try:
        dt = datetime(int(b["year"]), int(b["month"]), int(b["day"]),
                      int(b.get("hour", 0) or 0), int(b.get("minute", 0) or 0))
        p = calendar.pillars_for_datetime(dt)
        return f"{p['year']} {p['month']} {p['day']} {p['hour']}"
    except Exception:
        return ""


def years_in(text: str):
    return sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", text or "")})


def _ziwei_domain(question: str):
    """Map question keywords to the relevant Ziwei palace domain."""
    q = question or ""
    if any(k in q for k in ["婚", "妻", "夫", "结", "离", "感情", "姻", "配"]):
        return "marriage"
    if any(k in q for k in ["职", "业", "工作", "事业", "升", "创业"]):
        return "career"
    if any(k in q for k in ["财", "钱", "富", "薪", "债", "股", "投资", "破产"]):
        return "wealth"
    if any(k in q for k in ["病", "疾", "康", "手术", "癌", "医院", "身体", "逝"]):
        return "health"
    return None


def build_prompt(rec: dict):
    bazi = bazi_from_birth(rec["birth"])
    gender = rec.get("gender", "male")
    b = rec["birth"]
    bd = f"{b['year']:04d}-{b['month']:02d}-{b['day']:02d}"
    bt = f"{int(b.get('hour', 0) or 0):02d}:{int(b.get('minute', 0) or 0):02d}"
    by = int(b["year"])
    dy = calendar.dayun_list(bazi, gender, bd, bt, "solar", 80) or []
    if dy:
        dy_lines = [
            f"{by + int(round(d['start_age']))}-{by + int(round(d['start_age'])) + 9}岁 {d['pillar']}"
            for d in dy
        ]
    else:
        dy_lines = ["（出生信息不足，无法排大运）"]
    yrs = years_in(rec.get("question", "") + " " + " ".join(rec.get("options", [])))
    if yrs:
        m = {l["year"]: l["pillar"] for l in calendar.liunian_list(min(yrs), max(yrs))}
        ln_lines = [f"{y}年 {m.get(y, '?')}" for y in yrs]
    else:
        ln_lines = ["（题面无具体年份）"]
    # 打乱选项顺序，消除 LLM position bias（偏 A）；同 id 确定性打乱
    raw_opts = rec.get("options", [])
    texts = [re.sub(r"^[A-DＡ-Ｄ][\.、．:：]\s*", "", o).strip() for o in raw_opts]
    rng = random.Random(rec["id"])
    order = list(range(len(texts)))
    rng.shuffle(order)
    new_opts = [f"{chr(65 + i)}. {texts[order[i]]}" for i in range(len(texts))]
    mapping = {chr(65 + i): raw_opts[order[i]][:1].upper() for i in range(len(texts))}
    opts = "\n".join(new_opts)
    prompt = f"""你是资深八字命理师。仅依据八字原局、大运、流年推算，禁止编造命主未提供的隐私。

八字：{bazi}
性别：{'男命' if gender == 'male' else '女命'}
出生：{bd} {bt}

大运（每段10年）：
{chr(10).join('  ' + x for x in dy_lines)}

相关流年干支：
{chr(10).join('  ' + x for x in ln_lines)}

问题：{rec['question']}

选项：
{opts}

请结合原局格局、用神喜忌，以及大运流年的刑冲合害与十神应期，判断最可能正确的一项。
先简短推理（务必精炼，不超过80字，点出关键大运/流年干支），最后必须单独一行输出：
答案：X
（X 为 A/B/C/D 之一，对应上方选项顺序）"""
    return prompt, mapping


async def call(client, sem, prompt):
    async with sem:
        url = f"{BASE.rstrip('/')}/chat/completions"
        payload = {"model": MODEL, "temperature": 0.2, "max_tokens": 800,
                   "messages": [{"role": "user", "content": prompt}]}
        for attempt in range(3):
            try:
                async with client.post(url, headers={"Authorization": f"Bearer {API_KEY}",
                                       "Content-Type": "application/json"}, json=payload) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data["choices"][0]["message"]["content"]
                    if r.status in (429, 500, 502, 503):
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    return f"HTTP {r.status}: {(await r.text())[:120]}"
            except Exception:
                await asyncio.sleep(1.5 * (attempt + 1))
        return "FAIL"


def parse_ans(text: str) -> str:
    m = re.search(r"答案[：:]\s*\**\s*([ABCD])", text or "")
    if m:
        return m.group(1)
    lets = re.findall(r"\b([ABCD])\b", text or "")
    return lets[-1] if lets else "A"


async def main():
    paper = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    records = paper["records"] if isinstance(paper, dict) else paper
    sem = asyncio.Semaphore(int(os.environ.get("CONCURRENCY", "8")))
    # 少量诊断题缺 birth（None，不计入排名）→ 默认作答，不耗 API
    to_call = [r for r in records if r.get("birth") and bazi_from_birth(r["birth"])]
    defaults = {r["id"]: "A"
                for r in records
                if not (r.get("birth") and bazi_from_birth(r["birth"]))}
    async with aiohttp.ClientSession() as client:
        built = [build_prompt(r) for r in to_call]
        prompts = [b[0] for b in built]
        mappings = [b[1] for b in built]
        results = await asyncio.gather(*[call(client, sem, p) for p in prompts])
    answers, debug = {}, {}
    for rec, raw, mapping in zip(to_call, results, mappings):
        new_letter = parse_ans(raw)
        answers[rec["id"]] = mapping.get(new_letter, new_letter)
        debug[rec["id"]] = (raw or "")[-220:]
    answers.update(defaults)
    Path("sjms_answers.json").write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("sjms_debug.json").write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"answered {len(answers)}; dist={dict(Counter(answers.values()))}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
