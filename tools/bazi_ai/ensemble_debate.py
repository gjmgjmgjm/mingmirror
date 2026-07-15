#!/usr/bin/env python3
"""ensemble_debate — 多模型辩论 + critic 结构裁决 (roadmap Phase 4).

与 ``ensemble.py``(同模型多次降方差)不同,本模块跑**多个不同模型**(默认
deepseek-chat + deepseek-reasoner)独立推理,再用确定性结构事实(格局/用神,
来自 ``bazi_structural``)做 critic:

- 模型偏离确定性结构事实的字段(格局/用神)→ 被 det 裁决覆盖 + 标记分歧。
- domain(职业/财富/婚姻/健康)文本 → 多模型多数票;分歧大则降置信。
- 结构字段大多已被 engine 注入采纳,critic 主要纠正 LLM **偏离注入**的少数错误;
  debate 的核心增益来自 chat vs reasoner 在复杂命局的**互补**,以及多模型降方差。

注:deepseek-reasoner 慢(>5min/全量)且不支持 json_object —— engine 已对其
跳过 response_format(见 engine.py 657-664),故可参与辩论。

Usage::
    from tools.bazi_ai.ensemble_debate import analyze_bazi_debate
    await analyze_bazi_debate("甲子 丁卯 戈辰 壬子", gender="male",
                              models=["deepseek-chat","deepseek-reasoner"],
                              api_key=..., base_url=...)
"""
from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from tools.bazi_ai import bazi_structural  # noqa: E402
from tools.bazi_ai.engine import analyze_bazi  # noqa: E402

_DEFAULT_MODELS = ["deepseek-chat", "deepseek-reasoner"]
_ELM = set("木火土金水")


def _majority(items: List[str]) -> str:
    f = [i for i in items if i]
    return Counter(f).most_common(1)[0][0] if f else ""


def _majority_list(lists: List[List[str]]) -> List[str]:
    counts: Dict[str, int] = {}
    for lst in lists:
        for item in (lst or []):
            counts[str(item)] = counts.get(str(item), 0) + 1
    thr = len(lists) / 2
    return [k for k, c in counts.items() if c > thr]


def _elm_set(s) -> set:
    if isinstance(s, (list, tuple)):
        return {str(x) for x in s if str(x) in _ELM}
    return {x for x in str(s or "").replace("，", ",").split(",") if x in _ELM}


async def _run_model(model: str, bazi: str, kwargs: dict) -> tuple:
    try:
        r = await analyze_bazi(bazi, model=model, **kwargs)
        return model, r
    except Exception as exc:  # noqa: BLE001
        return model, {"_error": str(exc)}


async def analyze_bazi_debate(
    bazi: str,
    *,
    models: Optional[List[str]] = None,
    gender: str = "male",
    question: str = "",
    cases_path: Optional[Path] = Path("./bazi_knowledge/cases.jsonl"),
    knowledge_base_path: Path = Path("./bazi_knowledge/rule_primer.md"),
    extra_cases_paths: Optional[List[Path]] = None,
    extra_knowledge_base_paths: Optional[List[Path]] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    top_k: int = 3,
) -> Dict:
    """多模型辩论 + critic 结构裁决,返回 consensus + _debate meta."""
    models = models or _DEFAULT_MODELS
    common = dict(
        gender=gender, question=question, cases_path=cases_path,
        knowledge_base_path=knowledge_base_path,
        extra_cases_paths=extra_cases_paths,
        extra_knowledge_base_paths=extra_knowledge_base_paths,
        api_key=api_key, base_url=base_url, top_k=top_k,
    )
    pairs = await asyncio.gather(*[_run_model(m, bazi, common) for m in models])
    results = {m: r for m, r in pairs}
    errors = {m: r.get("_error") for m, r in results.items() if r.get("_error")}
    valid = {m: r for m, r in results.items() if not r.get("_error")}

    if not valid:
        return {"_error": "all models failed", "details": errors}
    if len(valid) == 1:
        m, r = next(iter(valid.items()))
        r["_debate"] = {"models_run": list(results), "single_model": m, "errors": errors}
        return r

    # ---- critic: 确定性结构事实 ----
    det = bazi_structural.structural_profile(bazi) or {}
    det_geju = det.get("geju", "")
    det_yong = _elm_set(det.get("useful_gods", []))

    rs = list(valid.values())
    basics = [r.get("basic_info", {}) for r in rs]
    model_names = list(valid)
    disagreements: List[str] = []

    # 格局: det 优先(模型偏离注入 → 裁决 + 标记)
    model_gejus = [b.get("pattern", "") for b in basics]
    final_geju = det_geju or _majority(model_gejus)
    deviants = [model_names[i] for i, g in enumerate(model_gejus)
                if g and g != final_geju]
    if deviants:
        disagreements.append(
            f"格局分歧 {model_gejus} → det裁决【{final_geju}】(偏离: {deviants})")

    # 用神: det 优先,否则多模型并集多数
    model_yongs = [_elm_set(b.get("useful_gods", [])) for b in basics]
    final_yong = det_yong or set(_majority_list([sorted(s) for s in model_yongs]))
    for i, s in enumerate(model_yongs):
        if s and not s.issubset(final_yong) and det_yong:
            disagreements.append(
                f"用神分歧 {model_names[i]}={sorted(s)} → det裁决【{sorted(final_yong)}】")

    # domain: 多模型多数票 + 分歧标记
    domains_list = [r.get("domain_analysis", {}) for r in rs]
    consensus_domains = {}
    for key in ["career", "wealth", "marriage", "health"]:
        texts = [d.get(key, "") for d in domains_list]
        consensus_domains[key] = _majority(texts)
        distinct = {t for t in texts if t}
        if len(distinct) > 1:
            disagreements.append(f"{key}文本分歧({len(distinct)}种)")

    # 置信度: 任一模型 low 或 分歧多 → 降级
    confidences = [r.get("confidence", "") for r in rs]
    if any(c == "low" for c in confidences) or len(disagreements) >= 3:
        final_conf = "low"
    elif any(c == "medium" for c in confidences) or disagreements:
        final_conf = "medium"
    else:
        final_conf = "high"

    base = rs[0]
    return {
        "basic_info": {
            **base.get("basic_info", {}),
            "pattern": final_geju,
            "useful_gods": sorted(final_yong),
        },
        "domain_analysis": consensus_domains,
        "liuqin_analysis": base.get("liuqin_analysis", ""),
        "liuqin_strength": base.get("liuqin_strength", {}),
        "wealth_level": _majority([r.get("wealth_level", "") for r in rs]),
        "summary": _majority_list([r.get("summary", []) for r in rs]),
        "confidence": final_conf,
        "_debate": {
            "models": model_names,
            "errors": errors,
            "disagreements": disagreements,
            "det_geju": det_geju,
            "det_useful_gods": sorted(det_yong),
        },
    }


def main():
    import argparse
    import json
    import os

    ap = argparse.ArgumentParser(description="八字多模型辩论分析")
    ap.add_argument("bazi")
    ap.add_argument("-q", "--question", default="")
    ap.add_argument("-m", "--models", default="deepseek-chat,deepseek-reasoner")
    ap.add_argument("--api-key", default=None)
    args = ap.parse_args()
    key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    r = asyncio.run(analyze_bazi_debate(
        args.bazi, question=args.question,
        models=[m.strip() for m in args.models.split(",") if m.strip()],
        api_key=key,
    ))
    print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
