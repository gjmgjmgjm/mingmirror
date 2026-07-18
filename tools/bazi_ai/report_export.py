#!/usr/bin/env python3
"""Product export package: markdown + print-ready HTML for 命书 / 标准交付包.

PDF is delivered via browser print (HTML) — no native PDF dependency required.
Optional pure-text .md for archive / CMS.
"""
from __future__ import annotations

import html
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from tools.bazi_ai.report_template import build_report, render_report


def _esc(s: Any) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def build_product_package(
    bazi: str,
    gender: str = "male",
    birth_info: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    *,
    include_auspicious: bool = True,
    event_type: str = "marriage",
    auspicious_days_n: int = 5,
    chart_id: str = "",
    label: str = "",
    liunian_start_year: Optional[int] = None,
    liunian_years: int = 10,
) -> Dict[str, Any]:
    """Assemble a standard product package (structure layer, zero LLM by default).

    *liunian_start_year* / *liunian_years* control the multi-system 流年 appendix
    range (defaults: this year × 10), aligned with frontend range controls.

    Returns dict with:
      meta, report (structured), markdown, html, filename_stem,
      auspicious (optional top days)
    """
    bazi = (bazi or "").strip()
    gender = gender or "male"
    birth_info = birth_info or {}
    today_y = date.today().year
    ln_start = int(liunian_start_year) if liunian_start_year else today_y
    ln_years = max(1, min(int(liunian_years or 10), 30))
    report = build_report(bazi, gender=gender, result=result, birth_info=birth_info)
    markdown = render_report(bazi, gender=gender, result=result, birth_info=birth_info)

    auspicious: Dict[str, Any] = {}
    if include_auspicious:
        try:
            from tools.bazi_ai.auspicious import auspicious_days

            d0 = date.today()
            aus = auspicious_days(
                bazi,
                gender,
                event_type,
                d0,
                d0 + timedelta(days=60),
                top_n=auspicious_days_n,
            )
            top = aus.get("top") or (aus.get("days") or [])[:auspicious_days_n]
            auspicious = {
                "event_type": aus.get("event_type"),
                "event_label": aus.get("event_label"),
                "useful_gods": aus.get("useful_gods") or [],
                "taboo_gods": aus.get("taboo_gods") or [],
                "top": top,
            }
            # Append to markdown
            if top:
                lines = [
                    "",
                    "---",
                    "",
                    f"## 附录、近 60 日择日精选（{auspicious.get('event_label') or event_type}）",
                    "",
                    f"> 用神：{'、'.join(auspicious.get('useful_gods') or []) or '—'}；"
                    f"忌神：{'、'.join(auspicious.get('taboo_gods') or []) or '—'}",
                    "",
                ]
                for i, day in enumerate(top, 1):
                    lines.append(
                        f"{i}. **{day.get('date')}** {day.get('day_pillar')} "
                        f"· {day.get('score')}分 · {day.get('reasoning', '')[:80]}"
                    )
                lines.append("")
                lines.append(
                    "_择日为命主用神+冲合趋势参考，非传统黄历；重大事项请多方参照。_"
                )
                markdown = markdown.rstrip() + "\n" + "\n".join(lines) + "\n"
        except Exception:
            auspicious = {}

    disclaimer = (
        "本报告结构层为程序确定性计算（排盘 / 用神 / 六亲等），AI 章节（若有）为趋势性参考，"
        "不构成医疗、法律或投资建议。"
    )
    html_doc = render_html_package(
        title=label or f"命书 · {bazi}",
        markdown=markdown,
        report=report,
        auspicious=auspicious,
        disclaimer=disclaimer,
        chart_id=chart_id,
        bazi=bazi,
        gender=gender,
    )

    # Multi-system structural appendix (ziwei + qizheng + 流年), zero LLM
    multi: Dict[str, Any] = {}
    multi_md_parts: List[str] = []
    birth_date = (birth_info or {}).get("birth_date") or ""
    birth_year: Optional[int] = None
    if birth_date and len(str(birth_date)) >= 4:
        try:
            birth_year = int(str(birth_date)[:4])
        except ValueError:
            birth_year = None

    try:
        from tools.ziwei.chart import chart_from_birth, yearly_bundle

        zw = chart_from_birth(bazi, gender=gender, birth_date=birth_date)
        if zw:
            cur = zw.get("current_limit") or {}
            multi["ziwei"] = {
                "ming_gong": zw.get("ming_gong"),
                "shen_gong": zw.get("shen_gong"),
                "bureau_label": zw.get("bureau_label"),
                "zhu_xing": zw.get("zhu_xing"),
                "ming_aux": zw.get("ming_aux"),
                "si_hua": zw.get("si_hua"),
                "current_limit": cur,
                "note": zw.get("note"),
            }
            multi_md_parts.append(
                f"### 紫微结构\n\n"
                f"- 命宫 {zw.get('life_palace')} · 身宫 {zw.get('body_palace')} · "
                f"{zw.get('bureau_label')}\n"
                f"- 命宫主星：{'、'.join(zw.get('zhu_xing') or [])}"
                + (
                    f"；辅星：{'、'.join(zw.get('ming_aux') or [])}"
                    if zw.get("ming_aux")
                    else ""
                )
                + "\n"
                f"- 年干四化：{'；'.join(zw.get('si_hua') or [])}\n"
                + (
                    f"- 当前大限：{cur.get('label')} · {cur.get('branch')}宫"
                    f"（{zw.get('limit_direction') or ''}）\n"
                    if cur
                    else ""
                )
            )
            # 流年附录：区间与前端/导出参数一致
            yb = yearly_bundle(
                bazi,
                gender=gender,
                birth_date=birth_date,
                start_year=ln_start,
                years=ln_years,
            )
            liunian_rows = (yb or {}).get("liunian") or []
            if liunian_rows:
                multi["ziwei"]["liunian"] = [
                    {
                        "year": r.get("year"),
                        "pillar": r.get("pillar"),
                        "palace_name": r.get("palace_name"),
                        "focus": r.get("focus"),
                        "si_hua": r.get("si_hua") or [],
                        "caution": r.get("caution"),
                        "overview": r.get("overview"),
                        "is_current": int(r.get("year") or 0) == today_y,
                    }
                    for r in liunian_rows
                ]
                multi["ziwei"]["liunian_range"] = {
                    "start": yb.get("start_year"),
                    "end": yb.get("end_year"),
                }
                lines = [
                    f"### 紫微流年（{yb.get('start_year')}–{yb.get('end_year')}）\n",
                    "",
                    "| 年 | 年柱 | 太岁入宫 | 重点 | 四化 |",
                    "|---|---|---|---|---|",
                ]
                for r in liunian_rows:
                    sihua = "、".join(r.get("si_hua") or []) or "—"
                    yr = r.get("year")
                    year_cell = f"{yr} 今年" if yr == today_y else str(yr)
                    lines.append(
                        f"| {year_cell} | {r.get('pillar')} | "
                        f"{r.get('palace_name')} | {r.get('focus') or '—'} | {sihua} |"
                    )
                lines.append("")
                lines.append(
                    f"_口径：{(yb.get('note') or '太岁入宫+流年四化+大限').strip()}；"
                    f"标「今年」行为公历 {today_y} 年。_\n"
                )
                multi_md_parts.append("\n".join(lines))
    except Exception:
        pass
    try:
        from tools.qizheng.calendar import structural_profile as qz_profile
        from tools.qizheng.engine import structural_yearly_sync

        qz = qz_profile(bazi)
        if qz:
            multi["qizheng"] = {
                "life_palace": qz.get("life_palace"),
                "body_palace": qz.get("body_palace"),
                "body_lord": qz.get("body_lord"),
                "five_element_pattern": qz.get("five_element_pattern"),
                "nayin": qz.get("nayin"),
            }
            multi_md_parts.append(
                f"### 七政结构\n\n"
                f"- 命宫 {qz.get('life_palace')} · 身宫 {qz.get('body_palace')}\n"
                f"- 身主 {qz.get('body_lord')} · 五行局 {qz.get('five_element_pattern')}\n"
                f"- 年柱纳音 {qz.get('nayin')}\n"
            )
            qy = structural_yearly_sync(
                bazi,
                gender=gender,
                birth_year=birth_year or date.today().year,
                years=ln_years,
                start_year=ln_start,
            )
            if not qy.get("error"):
                multi["qizheng"]["structural_summary"] = qy.get("structural_summary")
                multi["qizheng"]["dayun_summary"] = (qy.get("dayun_summary") or [])[:6]
                multi["qizheng"]["yearly_analysis"] = [
                    {
                        "year": y.get("year"),
                        "pillar": y.get("pillar"),
                        "active_palace": y.get("active_palace"),
                        "overview": y.get("overview"),
                        "caution": y.get("caution"),
                        "taishui_impact": y.get("taishui_impact"),
                        "star_impact": y.get("star_impact"),
                        "is_current": int(y.get("year") or 0) == today_y,
                    }
                    for y in (qy.get("yearly_analysis") or [])
                ]
                multi["qizheng"]["note"] = qy.get("note")
                yrows = multi["qizheng"]["yearly_analysis"]
                if yrows:
                    y0, y1 = yrows[0]["year"], yrows[-1]["year"]
                    lines = [
                        f"### 七政年运（{y0}–{y1}）\n",
                        "",
                        "| 年 | 年柱 | 大限宫 | 概要 | 注意 |",
                        "|---|---|---|---|---|",
                    ]
                    for y in yrows:
                        ov = (y.get("overview") or "")[:40]
                        ca = (y.get("caution") or "")[:36]
                        yr = y.get("year")
                        year_cell = f"{yr} 今年" if yr == today_y else str(yr)
                        lines.append(
                            f"| {year_cell} | {y.get('pillar')} | "
                            f"{y.get('active_palace') or '—'} | {ov} | {ca} |"
                        )
                    lines.append("")
                    lines.append(
                        f"_口径：{(qy.get('note') or '大限宫位+流年干支+宫主星').strip()}；"
                        f"标「今年」行为公历 {today_y} 年。_\n"
                    )
                    multi_md_parts.append("\n".join(lines))
    except Exception:
        pass
    if multi_md_parts:
        markdown = (
            markdown.rstrip()
            + "\n\n---\n\n## 附录、多体系结构摘要（确定性）\n\n"
            + f"> 流年区间：{ln_start}–{ln_start + ln_years - 1}"
            f"（{ln_years} 年）；含「今年」高亮行。\n\n"
            + "\n".join(multi_md_parts)
            + "\n_紫微/七政结构与流年为确定性简化口径；细批断语仍以各体系页面为准。_\n"
        )
        # rebuild html with extended markdown
        html_doc = render_html_package(
            title=label or f"命书 · {bazi}",
            markdown=markdown,
            report=report,
            auspicious=auspicious,
            disclaimer=disclaimer,
            chart_id=chart_id,
            bazi=bazi,
            gender=gender,
        )

    stem = f"mingmirror_{(chart_id or bazi).replace(' ', '_')[:40]}"
    return {
        "meta": {
            "bazi": bazi,
            "gender": gender,
            "chart_id": chart_id or None,
            "label": label or bazi,
            "package_version": "1.3",
            "trust": "certain_structure",
            "liunian_start_year": ln_start,
            "liunian_years": ln_years,
            "current_year": today_y,
        },
        "report": report,
        "auspicious": auspicious,
        "multi_system": multi,
        "markdown": markdown,
        "html": html_doc,
        "filename_stem": stem,
        "disclaimer": disclaimer,
    }


def render_html_package(
    title: str,
    markdown: str,
    report: Dict[str, Any],
    auspicious: Dict[str, Any],
    disclaimer: str,
    chart_id: str = "",
    bazi: str = "",
    gender: str = "",
) -> str:
    """Print-ready HTML (用户可浏览器另存为 PDF)."""
    # Lightweight markdown→HTML for headings/paragraphs/lists only
    body = _simple_md_to_html(markdown)
    gender_label = "女命" if gender in ("female", "女", "女命") else "男命"

    aus_block = ""
    top = (auspicious or {}).get("top") or []
    if top:
        rows = []
        for d in top:
            rows.append(
                "<tr>"
                f"<td>{_esc(d.get('date'))}</td>"
                f"<td>{_esc(d.get('day_pillar'))}</td>"
                f"<td>{_esc(d.get('score'))}</td>"
                f"<td>{_esc((d.get('reasoning') or '')[:100])}</td>"
                "</tr>"
            )
        aus_block = f"""
        <section class="card">
          <h2>近 60 日择日精选 · {_esc(auspicious.get('event_label'))}</h2>
          <table>
            <thead><tr><th>日期</th><th>日柱</th><th>分</th><th>理由</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </section>
        """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)}</title>
  <style>
    :root {{
      --ink: #1a1a1a; --muted: #666; --line: #e5e0d8; --gold: #b8860b;
      --paper: #faf8f5; --jade: #2d6a4f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", serif;
      color: var(--ink); background: var(--paper);
      max-width: 800px; margin: 0 auto; padding: 2rem 1.5rem 4rem;
      line-height: 1.75; font-size: 15px;
    }}
    header {{
      border-bottom: 2px solid var(--gold); padding-bottom: 1rem; margin-bottom: 1.5rem;
    }}
    header h1 {{ font-size: 1.6rem; margin: 0 0 0.35rem; letter-spacing: 0.08em; }}
    header .meta {{ color: var(--muted); font-size: 0.85rem; }}
    .badge {{
      display: inline-block; font-size: 0.7rem; padding: 0.15rem 0.5rem;
      border: 1px solid var(--gold); color: var(--gold); border-radius: 999px;
      margin-right: 0.4rem;
    }}
    .disclaimer {{
      background: #fff8e7; border-left: 3px solid var(--gold);
      padding: 0.75rem 1rem; font-size: 0.85rem; color: #555; margin: 1rem 0 1.5rem;
    }}
    h2 {{ font-size: 1.15rem; margin-top: 1.75rem; color: #333;
         border-left: 3px solid var(--jade); padding-left: 0.6rem; }}
    h3 {{ font-size: 1rem; margin-top: 1.2rem; }}
    p {{ margin: 0.5rem 0; }}
    ul, ol {{ padding-left: 1.4rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; margin: 0.75rem 0; }}
    th, td {{ border: 1px solid var(--line); padding: 0.4rem 0.55rem; text-align: left; }}
    th {{ background: #f0ebe3; }}
    tr.row-current {{ background: #fff3cd; }}
    tr.row-current td:first-child {{ font-weight: 700; color: #b8860b; }}
    .card {{ margin: 1.25rem 0; }}
    footer {{
      margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--line);
      font-size: 0.8rem; color: var(--muted); text-align: center;
    }}
    .actions {{
      position: sticky; top: 0; background: var(--paper); padding: 0.75rem 0;
      border-bottom: 1px solid var(--line); margin: -0.5rem 0 1rem; z-index: 10;
    }}
    .actions button {{
      background: var(--gold); color: #fff; border: 0; padding: 0.5rem 1rem;
      border-radius: 6px; cursor: pointer; font-size: 0.9rem;
    }}
    @media print {{
      .actions {{ display: none; }}
      body {{ background: #fff; padding: 0; max-width: none; }}
    }}
  </style>
</head>
<body>
  <div class="actions">
    <button type="button" onclick="window.print()">打印 / 另存为 PDF</button>
  </div>
  <header>
    <div>
      <span class="badge">命镜 MingMirror</span>
      <span class="badge">结构层确定性</span>
      <span class="badge">产品包 v1</span>
    </div>
    <h1>{_esc(title)}</h1>
    <div class="meta">
      {_esc(bazi)} · {_esc(gender_label)}
      {f' · ID {_esc(chart_id)}' if chart_id else ''}
    </div>
  </header>
  <div class="disclaimer">{_esc(disclaimer)}</div>
  <article class="report-body">
    {body}
  </article>
  {aus_block}
  <footer>
    命镜 · 个人命运导航 · 生成内容仅供参考 · 请勿用于医疗/法律/投资决策
  </footer>
</body>
</html>
"""


def _simple_md_to_html(md: str) -> str:
    """Very small markdown subset → HTML (headings, lists, paragraphs, hr, bold)."""
    lines = (md or "").splitlines()
    out: List[str] = []
    in_ul = False
    in_ol = False
    in_table = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def close_table() -> None:
        nonlocal in_table
        if in_table:
            out.append("</tbody></table>")
            in_table = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            close_lists()
            close_table()
            continue
        if line.strip() == "---":
            close_lists()
            close_table()
            out.append("<hr />")
            continue
        if line.startswith("|") and "|" in line[1:]:
            close_lists()
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue  # separator row
            if not in_table:
                out.append("<table><tbody>")
                in_table = True
                out.append(
                    "<tr>" + "".join(f"<th>{_esc(c)}</th>" for c in cells) + "</tr>"
                )
            else:
                # 「今年」高亮：单元格含「今年」或首列匹配公历今年
                is_current = any("今年" in c for c in cells)
                tr_cls = ' class="row-current"' if is_current else ""
                out.append(
                    f"<tr{tr_cls}>"
                    + "".join(f"<td>{_esc(c)}</td>" for c in cells)
                    + "</tr>"
                )
            continue
        close_table()
        if line.startswith("### "):
            close_lists()
            out.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            close_lists()
            out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            close_lists()
            out.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("> "):
            close_lists()
            out.append(f"<blockquote><p>{_inline(line[2:])}</p></blockquote>")
        elif line.startswith("- ") or line.startswith("* "):
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline(line[2:])}</li>")
        elif len(line) > 2 and line[0].isdigit() and line[1] in "、.":
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            # strip leading "1. " or "1、"
            content = line.split("、", 1)[-1] if "、" in line[:3] else line.split(".", 1)[-1]
            out.append(f"<li>{_inline(content.strip())}</li>")
        else:
            close_lists()
            out.append(f"<p>{_inline(line)}</p>")
    close_lists()
    close_table()
    return "\n".join(out)


def _inline(text: str) -> str:
    """Escape then apply **bold** and `code`."""
    s = _esc(text)
    # bold
    parts: List[str] = []
    while "**" in s:
        a, _, rest = s.partition("**")
        parts.append(a)
        if "**" not in rest:
            parts.append("**")
            parts.append(rest)
            s = ""
            break
        bold, _, s = rest.partition("**")
        parts.append(f"<strong>{bold}</strong>")
    parts.append(s)
    return "".join(parts)
