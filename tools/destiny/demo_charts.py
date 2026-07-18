"""Fixed demo charts for MingMirror product demos (structure-layer friendly).

These are deterministic fixtures used by:
  GET /api/v1/product/demo-charts
  scripts/demo_smoke.py
  frontend Dashboard one-click experience
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Curated samples: real-shaped bazi with birth metadata so dayun/liunian work.
DEMO_CHARTS: List[Dict[str, Any]] = [
    {
        "id": "demo-gengzi-male",
        "label": "庚子日主 · 男命",
        "blurb": "完整结构样例：八字流年 / 紫微太岁 / 七政年运 / 交付包附录。",
        "bazi": "乙卯 戊寅 庚子 丙子",
        "gender": "male",
        "birth_date": "1990-02-15",
        "birth_time": "12:00",
        "calendar_type": "solar",
        "location": {
            "name": "北京",
            "longitude": 116.4074,
            "latitude": 39.9042,
            "timezone": "Asia/Shanghai",
        },
        "tags": ["八字", "紫微", "七政", "流年", "交付包"],
        "highlights": ["命宫可排", "十年流年", "择日附录"],
    },
    {
        "id": "demo-wuchen-female",
        "label": "戊辰日主 · 女命",
        "blurb": "女命样例，适合看六亲、合婚择日与大运主题。",
        "bazi": "甲子 丙寅 戊辰 庚午",
        "gender": "female",
        "birth_date": "1984-03-08",
        "birth_time": "10:30",
        "calendar_type": "solar",
        "location": {
            "name": "上海",
            "longitude": 121.4737,
            "latitude": 31.2304,
            "timezone": "Asia/Shanghai",
        },
        "tags": ["八字", "六亲", "择日", "女命"],
        "highlights": ["大运时间轴", "合婚择日", "命书导出"],
    },
    {
        "id": "demo-bingyin-male",
        "label": "丙寅日主 · 男命",
        "blurb": "偏事业向演示：官禄/迁移流年与七政宫主星庙旺。",
        "bazi": "己未 庚午 丙寅 戊戌",
        "gender": "male",
        "birth_date": "1979-07-22",
        "birth_time": "08:15",
        "calendar_type": "solar",
        "location": {
            "name": "广州",
            "longitude": 113.2644,
            "latitude": 23.1291,
            "timezone": "Asia/Shanghai",
        },
        "tags": ["八字", "事业", "七政", "大运"],
        "highlights": ["大运主题", "七政宫主", "议会对照"],
    },
    {
        "id": "demo-renzi-young",
        "label": "壬子日主 · 青年",
        "blurb": "年轻盘：当前大运与近十年流年对比清晰。",
        "bazi": "戊辰 甲子 壬子 辛亥",
        "gender": "male",
        "birth_date": "2000-01-12",
        "birth_time": "22:40",
        "calendar_type": "solar",
        "location": {
            "name": "成都",
            "longitude": 104.0665,
            "latitude": 30.5723,
            "timezone": "Asia/Shanghai",
        },
        "tags": ["八字", "流年", "青年"],
        "highlights": ["近十年流年", "今日运势", "人生孪生"],
    },
]


def list_demo_charts() -> List[Dict[str, Any]]:
    """Return public demo catalog (no secrets)."""
    return [dict(c) for c in DEMO_CHARTS]


def get_demo_chart(demo_id: str) -> Optional[Dict[str, Any]]:
    key = (demo_id or "").strip()
    for c in DEMO_CHARTS:
        if c["id"] == key:
            return dict(c)
    return None


def demo_chart_as_birth_payload(demo: Dict[str, Any]) -> Dict[str, Any]:
    """Shape suitable for ChartCreateRequest / build_product_package."""
    return {
        "bazi": demo["bazi"],
        "gender": demo.get("gender") or "male",
        "birth_date": demo.get("birth_date") or "",
        "birth_time": demo.get("birth_time") or "",
        "calendar_type": demo.get("calendar_type") or "solar",
        "location": demo.get("location"),
        "label": demo.get("label") or demo["bazi"],
    }
