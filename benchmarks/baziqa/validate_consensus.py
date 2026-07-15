#!/usr/bin/env python3
"""Structure-layer consensus ruler: LLM 用神/旺衰/格局 vs the deterministic rule engine.

格局/用神/财富等级 have no objective gold in MingLi (its gold is the *event*). So
this ruler measures **consistency** between the LLM reader and the rule-based
deterministic engine (the standard 八字 rules anchor) — NOT accuracy. High
consistency = the LLM follows the rules; disagreements are flagged for human
review (the suspicious cases where the LLM may be deviating from standard 取用).

Usage::
    python benchmarks/baziqa/validate_consensus.py --limit 12 \
        --api-key $DEEPSEEK_API_KEY
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai import bazi_structural, calendar  # noqa: E402
from tools.bazi_ai.bazi_validator import normalize_bazi  # noqa: E402

DATA = Path("benchmarks/baziqa/data/mingli/data.json")
_ELM = set("木火土金水")
_STEM_ELM = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
             "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}


def _bazi(bi: Dict) -> str:
    try:
        dt = datetime(int(bi["year"]), int(bi["month"]), int(bi["day"]),
                      int(bi.get("hour", 0) or 0), int(bi.get("minute", 0) or 0))
    except (KeyError, ValueError, TypeError):
        return ""
    p = calendar.pillars_for_datetime(dt)
    raw = f"{p['year']} {p['month']} {p['day']} {p['hour']}"
    return normalize_bazi(raw) or raw


def _to_elm_set(s) -> set:
    out = set()
    if not s:
        return out
    if isinstance(s, (list, tuple)):
        for x in s:
            x = str(x)
            out.add(_STEM_ELM.get(x, x))
    else:
        for x in re.split(r"[,，、\s]+", str(s)):
            if x:
                out.add(_STEM_ELM.get(x, x))
    return out & _ELM or out


def _strength_bucket(s: str) -> str:
    s = (s or "").replace("偏", "").replace("太", "")
    if "强" in s or "旺" in s:
        return "强"
    if "弱" in s or "衰" in s:
        return "弱"
    return "中"


_SS_KEYS = ["食神", "伤官", "正财", "偏财", "正官", "七杀", "正印", "偏印",
            "建禄", "月劫", "羊刃"]


def _geju_root(s: str) -> str:
    """Extract the 十神 root of a 格局 name (七杀≡偏官)."""
    s = (s or "").replace("偏官", "七杀")
    for k in _SS_KEYS:
        if k in s:
            return k
    return ""


async def _call(client, key, base, model, prompt) -> dict:
    url = f"{base.rstrip('/')}/chat/completions"
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "temperature": 0.2, "max_tokens": 300,
               "response_format": {"type": "json_object"}}
    last = None
    for attempt in range(3):
        async with client.post(url, headers={"Authorization": f"Bearer {key}",
                               "Content-Type": "application/json"}, json=payload) as resp:
            text = await resp.text()
            if resp.status == 200:
                try:
                    d = json.loads(text)
                    content = d["choices"][0]["message"]["content"]
                    return json.loads(content)
                except Exception as exc:  # noqa: BLE001
                    last = f"parse: {exc} | {text[:160]}"
            else:
                last = f"HTTP {resp.status}: {text[:160]}"
        if resp.status in (429, 500, 502, 503):
            await asyncio.sleep(2 * (attempt + 1))
            continue
        break
    return {"_error": last}


def _prompt(bazi: str, bi: Dict, det_geju: str = "", det_yong: str = "", det_ji: str = "") -> str:
    gender = "男命" if bi.get("gender") in ("男", "male") else "女命"
    inject = ""
    if det_geju:
        inject += f"\n- 格局（程序按月令定格判定为【{det_geju}】，直接采用，不要自行另取）"
    if det_yong and det_yong != "需细断":
        inject += f"\n- 用神（程序按扶抑/调候/通关判定为【{det_yong}】，直接采用）"
    if det_ji and det_ji != "需细断":
        inject += f"\n- 忌神（程序判定为【{det_ji}】，直接采用）"
    return f"""只依据这个八字，快速结构判断，不要长篇。
八字：{bazi}（{gender}）{inject}
请输出 JSON（用神/忌神必须是五行：木火土金水）：
{{"旺衰":"身强|身弱|偏强|偏弱|中和","格局":"如七杀格/正官格/食神格/伤官格/正财格/偏财格/正印格/偏印格/从格等","用神":["木"],"忌神":["土"],"财富等级":"贫|温饱|小康|中产|小富|中富|大富|巨富"}}"""


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--base-url", default="https://api.deepseek.com/v1")
    ap.add_argument("--model", default="deepseek-chat")
    args = ap.parse_args()

    key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("no API key", file=sys.stderr); return
    qs = json.load(DATA.open(encoding="utf-8"))["questions"]
    # one question per case (cases repeat questions); take first per case
    seen = set()
    cases = []
    for q in qs:
        cid = q["case_id"]
        if cid in seen:
            continue
        seen.add(cid)
        cases.append(q)
        if len(cases) >= args.limit:
            break

    print(f"Structure consensus on {len(cases)} 命主 (LLM {args.model} vs rule engine)\n",
          file=sys.stderr)
    timeout = aiohttp.ClientTimeout(total=90)
    conn = aiohttp.TCPConnector(limit=2)
    agree = {"旺衰": 0, "用神": 0, "忌神": 0, "格局": 0}
    n = 0
    async with aiohttp.ClientSession(timeout=timeout, connector=conn) as session:
        for i, q in enumerate(cases, 1):
            bi = q["birth_info"]
            bazi = _bazi(bi)
            prof = bazi_structural.structural_profile(bazi) or {}
            r_anchor_str = prof.get("strength", "")
            det_geju = prof.get("geju", "")
            t_anchor = _to_elm_set(prof.get("taboo_gods", ""))
            u_anchor = _to_elm_set(prof.get("useful_gods", ""))
            res = await _call(session, key, args.base_url, args.model,
                              _prompt(bazi, bi, det_geju,
                                      prof.get("useful_gods", ""), prof.get("taboo_gods", "")))
            if res.get("_error"):
                print(f"[{i}] {q['case_id']} ERROR {res['_error']}", file=sys.stderr); continue
            n += 1
            llm_str = res.get("旺衰", "")
            llm_geju = res.get("格局", "")
            u_llm = _to_elm_set(res.get("用神", []))
            t_llm = _to_elm_set(res.get("忌神", []))
            m_str = _strength_bucket(r_anchor_str) == _strength_bucket(llm_str) and bool(llm_str)
            m_u = bool(u_anchor & u_llm)
            m_t = bool(t_anchor & t_llm)
            m_ge = bool(det_geju) and _geju_root(det_geju) == _geju_root(llm_geju)
            if m_str: agree["旺衰"] += 1
            if m_u: agree["用神"] += 1
            if m_t: agree["忌神"] += 1
            if m_ge: agree["格局"] += 1
            flag = "" if (m_str and m_u) else "  ← 分歧(待复核)"
            print(f"[{i}] {q['case_id']} {bazi}  财富={res.get('财富等级','?')}")
            print(f"    格局: 规则(月令)={det_geju or '?'} vs LLM={llm_geju or '?'} {'✓' if m_ge else '✗'}")
            print(f"    旺衰: 规则={r_anchor_str}[{_strength_bucket(r_anchor_str)}] "
                  f"vs LLM={llm_str}[{_strength_bucket(llm_str)}] {'✓' if m_str else '✗'}")
            print(f"    用神: 规则={sorted(u_anchor)} vs LLM={sorted(u_llm)} {'✓' if m_u else '✗'}"
                  f"  忌神: 规则={sorted(t_anchor)} vs LLM={sorted(t_llm)} {'✓' if m_t else '✗'}{flag}")
            print()

    if n:
        print(f"{'='*50}\n结构层一致性 (LLM vs 规则引擎, n={n}):")
        for k in ("格局", "旺衰", "用神", "忌神"):
            print(f"  {k} 一致: {agree[k]}/{n} = {agree[k]/n:.0%}")
        print("\n注：一致性≠准确率。分歧case是 LLM 偏离标准取用之处，需人工复核；")
        print("旺衰/用神高度一致=LLM遵循规则；格局/财富无gold，仅看分布与合理性。")


if __name__ == "__main__":
    asyncio.run(main())
