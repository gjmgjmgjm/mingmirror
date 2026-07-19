#!/usr/bin/env python3
"""Build celebrity_extra.json + yangyan_bazi_only.jsonl (S1+S2+S3).

Public figures only. Bazi via tools.bazi_ai.calendar.pillars_for_datetime.
Dedup vs MingLi / celebrity50 / yangyan (and internal).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.bazi_ai.bazi_validator import normalize_bazi  # noqa: E402
from tools.bazi_ai.calendar import pillars_for_datetime  # noqa: E402

DATA = ROOT / "benchmarks" / "baziqa" / "data"
OUT_EXTRA = DATA / "celebrity_extra.json"
OUT_YANGYAN = DATA / "yangyan_bazi_only.jsonl"
QIZHENG = ROOT / "tools" / "qizheng" / "benchmark_data" / "celebrity_charts.jsonl"
YANGYAN_CANDIDATES = [
    ROOT / "bazi_knowledge" / "cases_yangyan.jsonl",
    ROOT / "bazi_knowledge" / "杨炎八字绝技_cases.jsonl",
]

# Approximate city coords for public figures (not private homes).
LOCS = {
    "北京": (116.4074, 39.9042, "Asia/Shanghai"),
    "上海": (121.4737, 31.2304, "Asia/Shanghai"),
    "香港": (114.1694, 22.3193, "Asia/Hong_Kong"),
    "台北": (121.5654, 25.0330, "Asia/Taipei"),
    "广州": (113.2644, 23.1291, "Asia/Shanghai"),
    "杭州": (120.1551, 30.2741, "Asia/Shanghai"),
    "南京": (118.7969, 32.0603, "Asia/Shanghai"),
    "成都": (104.0665, 30.5723, "Asia/Shanghai"),
    "重庆": (106.5516, 29.5630, "Asia/Shanghai"),
    "武汉": (114.3055, 30.5928, "Asia/Shanghai"),
    "西安": (108.9402, 34.3416, "Asia/Shanghai"),
    "长沙": (112.9388, 28.2282, "Asia/Shanghai"),
    "天津": (117.2008, 39.0842, "Asia/Shanghai"),
    "沈阳": (123.4315, 41.8057, "Asia/Shanghai"),
    "大连": (121.6147, 38.9140, "Asia/Shanghai"),
    "青岛": (120.3826, 36.0671, "Asia/Shanghai"),
    "厦门": (118.0894, 24.4798, "Asia/Shanghai"),
    "福州": (119.2965, 26.0745, "Asia/Shanghai"),
    "昆明": (102.8329, 24.8801, "Asia/Shanghai"),
    "哈尔滨": (126.5349, 45.8038, "Asia/Shanghai"),
    "郑州": (113.6254, 34.7466, "Asia/Shanghai"),
    "济南": (117.1205, 36.6519, "Asia/Shanghai"),
    "合肥": (117.2272, 31.8206, "Asia/Shanghai"),
    "南昌": (115.8579, 28.6820, "Asia/Shanghai"),
    "南宁": (108.3661, 22.8170, "Asia/Shanghai"),
    "海口": (110.1999, 20.0440, "Asia/Shanghai"),
    "兰州": (103.8343, 36.0611, "Asia/Shanghai"),
    "乌鲁木齐": (87.6168, 43.8256, "Asia/Shanghai"),
    "拉萨": (91.1409, 29.6456, "Asia/Shanghai"),
    "呼和浩特": (111.7519, 40.8414, "Asia/Shanghai"),
    "银川": (106.2309, 38.4872, "Asia/Shanghai"),
    "西宁": (101.7782, 36.6171, "Asia/Shanghai"),
    "贵阳": (106.6302, 26.6477, "Asia/Shanghai"),
    "石家庄": (114.5149, 38.0428, "Asia/Shanghai"),
    "太原": (112.5489, 37.8706, "Asia/Shanghai"),
    "长春": (125.3235, 43.8171, "Asia/Shanghai"),
    "苏州": (120.5853, 31.2989, "Asia/Shanghai"),
    "无锡": (120.3119, 31.4912, "Asia/Shanghai"),
    "宁波": (121.5440, 29.8683, "Asia/Shanghai"),
    "温州": (120.6994, 27.9943, "Asia/Shanghai"),
    "绍兴": (120.5821, 30.0515, "Asia/Shanghai"),
    "嘉兴": (120.7555, 30.7461, "Asia/Shanghai"),
    "金华": (119.6474, 29.0791, "Asia/Shanghai"),
    "台州": (121.4208, 28.6561, "Asia/Shanghai"),
    "湖州": (120.0868, 30.8944, "Asia/Shanghai"),
    "常州": (119.9740, 31.8113, "Asia/Shanghai"),
    "徐州": (117.2841, 34.2058, "Asia/Shanghai"),
    "扬州": (119.4129, 32.3942, "Asia/Shanghai"),
    "镇江": (119.4528, 32.2044, "Asia/Shanghai"),
    "淮安": (119.0153, 33.6104, "Asia/Shanghai"),
    "盐城": (120.1399, 33.3776, "Asia/Shanghai"),
    "连云港": (119.2216, 34.5967, "Asia/Shanghai"),
    "南通": (120.8943, 31.9802, "Asia/Shanghai"),
    "泰州": (119.9152, 32.4849, "Asia/Shanghai"),
    "宿迁": (118.2752, 33.9630, "Asia/Shanghai"),
    "梅州": (116.1222, 24.2886, "Asia/Shanghai"),
    "潮州": (116.6226, 23.6569, "Asia/Shanghai"),
    "汕头": (116.6819, 23.3541, "Asia/Shanghai"),
    "佛山": (113.1214, 23.0215, "Asia/Shanghai"),
    "东莞": (113.7518, 23.0207, "Asia/Shanghai"),
    "中山": (113.3926, 22.5170, "Asia/Shanghai"),
    "珠海": (113.5767, 22.2707, "Asia/Shanghai"),
    "深圳": (114.0579, 22.5431, "Asia/Shanghai"),
    "保定": (115.4646, 38.8739, "Asia/Shanghai"),
    "唐山": (118.1802, 39.6309, "Asia/Shanghai"),
    "秦皇岛": (119.6005, 39.9354, "Asia/Shanghai"),
    "邯郸": (114.5391, 36.6256, "Asia/Shanghai"),
    "邢台": (114.5048, 37.0706, "Asia/Shanghai"),
    "张家口": (114.8841, 40.8119, "Asia/Shanghai"),
    "承德": (117.9624, 40.9540, "Asia/Shanghai"),
    "沧州": (116.8575, 38.3106, "Asia/Shanghai"),
    "廊坊": (116.7036, 39.5186, "Asia/Shanghai"),
    "衡水": (115.6659, 37.7351, "Asia/Shanghai"),
    "东京": (139.6917, 35.6895, "Asia/Tokyo"),
    "大阪": (135.5023, 34.6937, "Asia/Tokyo"),
    "首尔": (126.9780, 37.5665, "Asia/Seoul"),
    "新加坡": (103.8198, 1.3521, "Asia/Singapore"),
    "曼谷": (100.5018, 13.7563, "Asia/Bangkok"),
    "雅加达": (106.8456, -6.2088, "Asia/Jakarta"),
    "新德里": (77.2090, 28.6139, "Asia/Kolkata"),
    "孟买": (72.8777, 19.0760, "Asia/Kolkata"),
    "伦敦": (-0.1276, 51.5074, "Europe/London"),
    "巴黎": (2.3522, 48.8566, "Europe/Paris"),
    "柏林": (13.4050, 52.5200, "Europe/Berlin"),
    "莫斯科": (37.6173, 55.7558, "Europe/Moscow"),
    "罗马": (12.4964, 41.9028, "Europe/Rome"),
    "马德里": (-3.7038, 40.4168, "Europe/Madrid"),
    "维也纳": (16.3738, 48.2082, "Europe/Vienna"),
    "阿姆斯特丹": (4.9041, 52.3676, "Europe/Amsterdam"),
    "布鲁塞尔": (4.3517, 50.8503, "Europe/Brussels"),
    "斯德哥尔摩": (18.0686, 59.3293, "Europe/Stockholm"),
    "奥斯陆": (10.7522, 59.9139, "Europe/Oslo"),
    "哥本哈根": (12.5683, 55.6761, "Europe/Copenhagen"),
    "华沙": (21.0122, 52.2297, "Europe/Warsaw"),
    "布拉格": (14.4378, 50.0755, "Europe/Prague"),
    "雅典": (23.7275, 37.9838, "Europe/Athens"),
    "伊斯坦布尔": (28.9784, 41.0082, "Europe/Istanbul"),
    "开罗": (31.2357, 30.0444, "Africa/Cairo"),
    "约翰内斯堡": (28.0473, -26.2041, "Africa/Johannesburg"),
    "比勒陀利亚": (28.1881, -25.7479, "Africa/Johannesburg"),
    "纽约": (-74.0060, 40.7128, "America/New_York"),
    "华盛顿": (-77.0369, 38.9072, "America/New_York"),
    "波士顿": (-71.0589, 42.3601, "America/New_York"),
    "费城": (-75.1652, 39.9526, "America/New_York"),
    "芝加哥": (-87.6298, 41.8781, "America/Chicago"),
    "休斯顿": (-95.3698, 29.7604, "America/Chicago"),
    "达拉斯": (-96.7970, 32.7767, "America/Chicago"),
    "丹佛": (-104.9903, 39.7392, "America/Denver"),
    "洛杉矶": (-118.2437, 34.0522, "America/Los_Angeles"),
    "旧金山": (-122.4194, 37.7749, "America/Los_Angeles"),
    "西雅图": (-122.3321, 47.6062, "America/Los_Angeles"),
    "火奴鲁鲁": (-157.8583, 21.3069, "Pacific/Honolulu"),
    "多伦多": (-79.3832, 43.6532, "America/Toronto"),
    "温哥华": (-123.1207, 49.2827, "America/Vancouver"),
    "墨西哥城": (-99.1332, 19.4326, "America/Mexico_City"),
    "圣保罗": (-46.6333, -23.5505, "America/Sao_Paulo"),
    "布宜诺斯艾利斯": (-58.3816, -34.6037, "America/Argentina/Buenos_Aires"),
    "悉尼": (151.2093, -33.8688, "Australia/Sydney"),
    "墨尔本": (144.9631, -37.8136, "Australia/Melbourne"),
    "奥克兰": (174.7633, -36.8485, "Pacific/Auckland"),
    "未知": (116.4074, 39.9042, "Asia/Shanghai"),
}


def _loc(name: str) -> Dict[str, Any]:
    lon, lat, tz = LOCS.get(name, LOCS["未知"])
    return {"name": name, "longitude": lon, "latitude": lat, "timezone": tz}


def _bazi_str(dt: datetime) -> str:
    p = pillars_for_datetime(dt)
    raw = f"{p['year']} {p['month']} {p['day']} {p['hour']}"
    return normalize_bazi(raw) or raw


def _birth_key(y: int, m: int, d: int, h: int = 12, mi: int = 0) -> str:
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}T{int(h):02d}:{int(mi):02d}"


def _name_key(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def load_dedup() -> Tuple[Set[str], Set[str], Set[str]]:
    """Return (birth_keys, name_keys, bazi_compact_keys)."""
    births: Set[str] = set()
    names: Set[str] = set()
    bazis: Set[str] = set()

    # celebrity50
    cel = DATA / "celebrity50_zh.json"
    if cel.exists():
        for p in json.loads(cel.read_text(encoding="utf-8")):
            names.add(_name_key(p.get("name", "")))
            b = (p.get("profile") or {}).get("birth") or {}
            if b.get("year"):
                births.add(
                    _birth_key(
                        b["year"],
                        b.get("month", 1),
                        b.get("day", 1),
                        b.get("hour", 12) or 12,
                        b.get("minute", 0) or 0,
                    )
                )

    # mingli
    ml = DATA / "mingli" / "data.json"
    if ml.exists():
        seen = set()
        for q in json.loads(ml.read_text(encoding="utf-8")).get("questions", []):
            cid = q.get("case_id", "")
            if cid in seen:
                continue
            seen.add(cid)
            bi = q.get("birth_info") or {}
            if bi.get("year"):
                births.add(
                    _birth_key(
                        bi["year"],
                        bi.get("month", 1),
                        bi.get("day", 1),
                        bi.get("hour", 12) or 12,
                        bi.get("minute", 0) or 0,
                    )
                )

    # contest8 (also existing, avoid re-adding same people)
    for f in DATA.glob("contest8_*.json"):
        try:
            arr = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for p in arr:
            if not isinstance(p, dict) or "person_id" not in p:
                continue
            names.add(_name_key(p.get("name", "")))
            b = (p.get("profile") or {}).get("birth") or {}
            if b.get("year"):
                births.add(
                    _birth_key(
                        b["year"],
                        b.get("month", 1),
                        b.get("day", 1),
                        b.get("hour", 12) or 12,
                        b.get("minute", 0) or 0,
                    )
                )

    # yangyan bazi
    for path in YANGYAN_CANDIDATES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            o = json.loads(line)
            bz = normalize_bazi(o.get("bazi", "") or "") or (o.get("bazi") or "")
            if bz:
                bazis.add(bz.replace(" ", ""))
        break

    return births, names, bazis


# Curated public figures: (name, gender, YYYY-MM-DD, HH:MM, city, source_note)
# Birth facts from Wikipedia/public domain encyclopedic knowledge.
# Times: use known public times when widely published; else 12:00.
CURATED: List[Tuple[str, str, str, str, str, str]] = [
    # --- from qizheng will be loaded separately ---
    # Chinese modern public figures / historical (public bios)
    ("孙中山", "male", "1866-11-12", "12:00", "广东", "wikipedia:孙中山"),
    ("鲁迅", "male", "1881-09-25", "12:00", "绍兴", "wikipedia:鲁迅"),
    ("胡适", "male", "1891-12-17", "12:00", "上海", "wikipedia:胡适"),
    ("蔡元培", "male", "1868-01-11", "12:00", "绍兴", "wikipedia:蔡元培"),
    ("梁启超", "male", "1873-02-23", "12:00", "广东", "wikipedia:梁启超"),
    ("康有为", "male", "1858-03-19", "12:00", "广东", "wikipedia:康有为"),
    ("秋瑾", "female", "1875-11-08", "12:00", "绍兴", "wikipedia:秋瑾"),
    ("宋庆龄", "female", "1893-01-27", "12:00", "上海", "wikipedia:宋庆龄"),
    ("宋美龄", "female", "1898-03-05", "12:00", "上海", "wikipedia:宋美龄"),
    ("张学良", "male", "1901-06-03", "12:00", "沈阳", "wikipedia:张学良"),
    ("张作霖", "male", "1875-03-19", "12:00", "沈阳", "wikipedia:张作霖"),
    ("溥仪", "male", "1906-02-07", "12:00", "北京", "wikipedia:溥仪"),
    ("慈禧太后", "female", "1835-11-29", "12:00", "北京", "wikipedia:慈禧太后"),
    ("光绪帝", "male", "1871-08-14", "12:00", "北京", "wikipedia:光绪帝"),
    ("宣统帝", "male", "1906-02-07", "12:00", "北京", "wikipedia:溥仪"),
    ("康熙帝", "male", "1654-05-04", "12:00", "北京", "wikipedia:康熙帝"),
    ("乾隆帝", "male", "1711-09-25", "12:00", "北京", "wikipedia:乾隆帝"),
    ("雍正帝", "male", "1678-12-13", "12:00", "北京", "wikipedia:雍正帝"),
    ("朱元璋", "male", "1328-10-21", "12:00", "南京", "wikipedia:朱元璋"),
    ("成吉思汗", "male", "1162-05-31", "12:00", "未知", "wikipedia:成吉思汗"),
    ("李白", "male", "0701-05-19", "12:00", "未知", "wikipedia:李白"),
    ("杜甫", "male", "0712-02-12", "12:00", "未知", "wikipedia:杜甫"),
    ("苏轼", "male", "1037-01-08", "12:00", "未知", "wikipedia:苏轼"),
    ("曹雪芹", "male", "1715-07-04", "12:00", "北京", "wikipedia:曹雪芹"),
    ("孔子", "male", "-0551-09-28", "12:00", "未知", "wikipedia:孔子"),  # may fail
    ("老子", "male", "-0601-01-01", "12:00", "未知", "wikipedia:老子"),
    ("诸葛亮", "male", "0181-07-23", "12:00", "未知", "wikipedia:诸葛亮"),
    ("关羽", "male", "0160-01-01", "12:00", "未知", "wikipedia:关羽"),
    ("岳飞", "male", "1103-03-24", "12:00", "未知", "wikipedia:岳飞"),
    ("文天祥", "male", "1236-06-06", "12:00", "未知", "wikipedia:文天祥"),
    ("郑成功", "male", "1624-08-27", "12:00", "未知", "wikipedia:郑成功"),
    ("林则徐", "male", "1785-08-30", "12:00", "福州", "wikipedia:林则徐"),
    ("曾国藩", "male", "1811-11-26", "12:00", "长沙", "wikipedia:曾国藩"),
    ("李鸿章", "male", "1823-02-15", "12:00", "合肥", "wikipedia:李鸿章"),
    ("袁世凯", "male", "1859-09-16", "12:00", "郑州", "wikipedia:袁世凯"),
    ("冯玉祥", "male", "1882-11-06", "12:00", "保定", "wikipedia:冯玉祥"),
    ("阎锡山", "male", "1883-08-08", "12:00", "太原", "wikipedia:阎锡山"),
    ("白崇禧", "male", "1893-03-18", "12:00", "南宁", "wikipedia:白崇禧"),
    ("李宗仁", "male", "1891-08-13", "12:00", "南宁", "wikipedia:李宗仁"),
    ("陈毅", "male", "1901-08-26", "12:00", "四川", "wikipedia:陈毅"),
    ("贺龙", "male", "1896-03-22", "12:00", "长沙", "wikipedia:贺龙"),
    ("彭德怀", "male", "1898-10-24", "12:00", "长沙", "wikipedia:彭德怀"),
    ("刘伯承", "male", "1892-12-04", "12:00", "重庆", "wikipedia:刘伯承"),
    ("徐向前", "male", "1901-11-08", "12:00", "太原", "wikipedia:徐向前"),
    ("聂荣臻", "male", "1899-12-29", "12:00", "重庆", "wikipedia:聂荣臻"),
    ("叶剑英", "male", "1897-04-28", "12:00", "梅州", "wikipedia:叶剑英"),
    ("林彪", "male", "1907-12-05", "12:00", "武汉", "wikipedia:林彪"),
    ("华国锋", "male", "1921-02-16", "12:00", "太原", "wikipedia:华国锋"),
    ("胡耀邦", "male", "1915-11-20", "12:00", "长沙", "wikipedia:胡耀邦"),
    ("赵紫阳", "male", "1919-10-17", "12:00", "郑州", "wikipedia:赵紫阳"),
    ("江泽民", "male", "1926-08-17", "12:00", "扬州", "wikipedia:江泽民"),
    ("李鹏", "male", "1928-10-20", "12:00", "成都", "wikipedia:李鹏"),
    ("朱镕基", "male", "1928-10-23", "12:00", "长沙", "wikipedia:朱镕基"),
    ("胡锦涛", "male", "1942-12-21", "12:00", "泰州", "wikipedia:胡锦涛"),
    ("温家宝", "male", "1942-09-15", "12:00", "天津", "wikipedia:温家宝"),
    ("习近平", "male", "1953-06-15", "12:00", "北京", "wikipedia:习近平"),
    ("李克强", "male", "1955-07-01", "12:00", "合肥", "wikipedia:李克强"),
    ("李强", "male", "1959-07-23", "12:00", "温州", "wikipedia:李强"),
    # Business / tech (public bios)
    ("任正非", "male", "1944-10-25", "12:00", "贵阳", "wikipedia:任正非"),
    ("马化腾", "male", "1971-10-29", "12:00", "汕头", "wikipedia:马化腾"),
    ("李彦宏", "male", "1968-11-17", "12:00", "阳泉", "wikipedia:李彦宏"),
    ("刘强东", "male", "1974-03-10", "12:00", "宿迁", "wikipedia:刘强东"),
    ("雷军", "male", "1969-12-16", "12:00", "武汉", "wikipedia:雷军"),
    ("王健林", "male", "1954-10-24", "12:00", "四川", "wikipedia:王健林"),
    ("许家印", "male", "1958-10-09", "12:00", "河南", "wikipedia:许家印"),
    ("张一鸣", "male", "1983-01-01", "12:00", "龙岩", "wikipedia:张一鸣"),
    ("黄峥", "male", "1980-01-01", "12:00", "杭州", "wikipedia:黄峥"),
    ("丁磊", "male", "1971-10-01", "12:00", "宁波", "wikipedia:丁磊"),
    ("张朝阳", "male", "1964-10-31", "12:00", "西安", "wikipedia:张朝阳"),
    ("俞敏洪", "male", "1962-09-15", "12:00", "扬州", "wikipedia:俞敏洪"),
    ("董明珠", "female", "1954-08-01", "12:00", "南京", "wikipedia:董明珠"),
    ("宗庆后", "male", "1945-10-12", "12:00", "杭州", "wikipedia:宗庆后"),
    ("鲁冠球", "male", "1945-01-12", "12:00", "杭州", "wikipedia:鲁冠球"),
    ("柳传志", "male", "1944-04-29", "12:00", "镇江", "wikipedia:柳传志"),
    ("杨元庆", "male", "1964-11-12", "12:00", "合肥", "wikipedia:杨元庆"),
    ("曹德旺", "male", "1946-05-01", "12:00", "福州", "wikipedia:曹德旺"),
    ("何享健", "male", "1942-01-01", "12:00", "佛山", "wikipedia:何享健"),
    ("李书福", "male", "1963-06-25", "12:00", "台州", "wikipedia:李书福"),
    ("王石", "male", "1951-01-23", "12:00", "柳州", "wikipedia:王石"),
    ("潘石屹", "male", "1963-11-14", "12:00", "兰州", "wikipedia:潘石屹"),
    ("张近东", "male", "1963-01-01", "12:00", "南京", "wikipedia:张近东"),
    ("孙宏斌", "male", "1963-01-01", "12:00", "山西", "wikipedia:孙宏斌"),
    # Entertainment (public)
    ("成龙", "male", "1954-04-07", "12:00", "香港", "wikipedia:成龙"),
    ("李连杰", "male", "1963-04-26", "12:00", "北京", "wikipedia:李连杰"),
    ("周润发", "male", "1955-05-18", "12:00", "香港", "wikipedia:周润发"),
    ("周星驰", "male", "1962-06-22", "12:00", "香港", "wikipedia:周星驰"),
    ("刘德华", "male", "1961-09-27", "12:00", "香港", "wikipedia:刘德华"),
    ("张学友", "male", "1961-07-10", "12:00", "香港", "wikipedia:张学友"),
    ("郭富城", "male", "1965-10-06", "12:00", "香港", "wikipedia:郭富城"),
    ("黎明", "male", "1966-12-11", "12:00", "北京", "wikipedia:黎明"),
    ("梁朝伟", "male", "1962-06-27", "12:00", "香港", "wikipedia:梁朝伟"),
    ("刘嘉玲", "female", "1965-12-08", "12:00", "苏州", "wikipedia:刘嘉玲"),
    ("张曼玉", "female", "1964-09-20", "12:00", "香港", "wikipedia:张曼玉"),
    ("林青霞", "female", "1954-11-03", "12:00", "台北", "wikipedia:林青霞"),
    ("邓丽君", "female", "1953-01-29", "12:00", "台北", "wikipedia:邓丽君"),
    ("梅艳芳", "female", "1963-10-10", "12:00", "香港", "wikipedia:梅艳芳"),
    ("张国荣", "male", "1956-09-12", "12:00", "香港", "wikipedia:张国荣"),
    ("黄家驹", "male", "1962-06-10", "12:00", "香港", "wikipedia:黄家驹"),
    ("王菲", "female", "1969-08-08", "12:00", "北京", "wikipedia:王菲"),
    ("那英", "female", "1967-11-27", "12:00", "沈阳", "wikipedia:那英"),
    ("周杰伦", "male", "1979-01-18", "12:00", "台北", "wikipedia:周杰伦"),
    ("蔡依林", "female", "1980-09-15", "12:00", "台北", "wikipedia:蔡依林"),
    ("林俊杰", "male", "1981-03-27", "12:00", "新加坡", "wikipedia:林俊杰"),
    ("王力宏", "male", "1976-05-17", "12:00", "纽约", "wikipedia:王力宏"),
    ("李宇春", "female", "1984-03-10", "12:00", "成都", "wikipedia:李宇春"),
    ("周迅", "female", "1974-10-18", "12:00", "衢州", "wikipedia:周迅"),
    ("章子怡", "female", "1979-02-09", "12:00", "北京", "wikipedia:章子怡"),
    ("赵薇", "female", "1976-03-12", "12:00", "无锡", "wikipedia:赵薇"),
    ("周冬雨", "female", "1992-01-31", "12:00", "石家庄", "wikipedia:周冬雨"),
    ("易烊千玺", "male", "2000-11-28", "12:00", "怀化", "wikipedia:易烊千玺"),
    ("王俊凯", "male", "1999-09-21", "12:00", "重庆", "wikipedia:王俊凯"),
    ("王源", "male", "2000-11-08", "12:00", "重庆", "wikipedia:王源"),
    ("鹿晗", "male", "1990-04-20", "12:00", "北京", "wikipedia:鹿晗"),
    ("吴亦凡", "male", "1990-11-06", "12:00", "广州", "wikipedia:吴亦凡"),
    ("黄渤", "male", "1974-08-26", "12:00", "青岛", "wikipedia:黄渤"),
    ("徐峥", "male", "1972-04-18", "12:00", "上海", "wikipedia:徐峥"),
    ("沈腾", "male", "1979-10-23", "12:00", "齐齐哈尔", "wikipedia:沈腾"),
    ("贾玲", "female", "1982-04-29", "12:00", "襄阳", "wikipedia:贾玲"),
    ("杨幂", "female", "1986-09-12", "12:00", "北京", "wikipedia:杨幂"),
    ("赵丽颖", "female", "1987-10-16", "12:00", "廊坊", "wikipedia:赵丽颖"),
    ("杨紫", "female", "1992-11-06", "12:00", "北京", "wikipedia:杨紫"),
    ("迪丽热巴", "female", "1992-06-03", "12:00", "乌鲁木齐", "wikipedia:迪丽热巴"),
    ("古力娜扎", "female", "1992-05-02", "12:00", "乌鲁木齐", "wikipedia:古力娜扎"),
    ("刘亦菲", "female", "1987-08-25", "12:00", "武汉", "wikipedia:刘亦菲"),
    ("唐嫣", "female", "1983-12-06", "12:00", "上海", "wikipedia:唐嫣"),
    ("胡歌", "male", "1982-09-20", "12:00", "上海", "wikipedia:胡歌"),
    ("王凯", "male", "1982-08-18", "12:00", "武汉", "wikipedia:王凯"),
    ("靳东", "male", "1976-12-21", "12:00", "郑州", "wikipedia:靳东"),
    ("陈道明", "male", "1955-04-26", "12:00", "天津", "wikipedia:陈道明"),
    ("张国立", "male", "1955-01-17", "12:00", "天津", "wikipedia:张国立"),
    ("葛优", "male", "1957-04-19", "12:00", "北京", "wikipedia:葛优"),
    ("冯小刚", "male", "1958-03-18", "12:00", "北京", "wikipedia:冯小刚"),
    ("张艺谋", "male", "1950-11-14", "12:00", "西安", "wikipedia:张艺谋"),
    ("陈凯歌", "male", "1952-08-12", "12:00", "北京", "wikipedia:陈凯歌"),
    ("李安", "male", "1954-10-23", "12:00", "屏东", "wikipedia:李安"),
    ("王家卫", "male", "1958-07-17", "12:00", "上海", "wikipedia:王家卫"),
    ("徐克", "male", "1950-01-02", "12:00", "西贡", "wikipedia:徐克"),
    ("吴京", "male", "1974-04-03", "12:00", "北京", "wikipedia:吴京"),
    ("甄子丹", "male", "1963-07-27", "12:00", "广州", "wikipedia:甄子丹"),
    ("洪金宝", "male", "1952-01-07", "12:00", "香港", "wikipedia:洪金宝"),
    ("元彪", "male", "1957-07-26", "12:00", "香港", "wikipedia:元彪"),
    # Sports
    ("姚明", "male", "1980-09-12", "12:00", "上海", "wikipedia:姚明"),
    ("刘翔", "male", "1983-07-13", "12:00", "上海", "wikipedia:刘翔"),
    ("李娜", "female", "1982-02-26", "12:00", "武汉", "wikipedia:李娜"),
    ("丁俊晖", "male", "1987-04-01", "12:00", "宜兴", "wikipedia:丁俊晖"),
    ("林丹", "male", "1983-10-14", "12:00", "龙岩", "wikipedia:林丹"),
    ("孙杨", "male", "1991-12-01", "12:00", "杭州", "wikipedia:孙杨"),
    ("苏炳添", "male", "1989-08-29", "12:00", "中山", "wikipedia:苏炳添"),
    ("谷爱凌", "female", "2003-09-03", "12:00", "旧金山", "wikipedia:谷爱凌"),
    ("苏翊鸣", "male", "2004-02-25", "12:00", "吉林", "wikipedia:苏翊鸣"),
    ("张继科", "male", "1988-02-16", "12:00", "青岛", "wikipedia:张继科"),
    ("马龙", "male", "1988-10-20", "12:00", "鞍山", "wikipedia:马龙"),
    ("樊振东", "male", "1997-01-22", "12:00", "广州", "wikipedia:樊振东"),
    ("郭晶晶", "female", "1981-10-15", "12:00", "保定", "wikipedia:郭晶晶"),
    ("李小鹏", "male", "1981-07-27", "12:00", "长沙", "wikipedia:李小鹏"),
    # Science / letters
    ("钱学森", "male", "1911-12-11", "12:00", "上海", "wikipedia:钱学森"),
    ("钱三强", "male", "1913-10-16", "12:00", "湖州", "wikipedia:钱三强"),
    ("邓稼先", "male", "1924-06-25", "12:00", "怀宁", "wikipedia:邓稼先"),
    ("袁隆平", "male", "1930-09-07", "12:00", "北京", "wikipedia:袁隆平"),
    ("屠呦呦", "female", "1930-12-30", "12:00", "宁波", "wikipedia:屠呦呦"),
    ("杨振宁", "male", "1922-10-01", "12:00", "合肥", "wikipedia:杨振宁"),
    ("李政道", "male", "1926-11-24", "12:00", "上海", "wikipedia:李政道"),
    ("丁肇中", "male", "1936-01-27", "12:00", "美国", "wikipedia:丁肇中"),
    ("朱棣文", "male", "1948-02-28", "12:00", "圣路易斯", "wikipedia:朱棣文"),
    ("高锟", "male", "1933-11-04", "12:00", "上海", "wikipedia:高锟"),
    ("莫言", "male", "1955-02-17", "12:00", "高密", "wikipedia:莫言"),
    ("余华", "male", "1960-04-03", "12:00", "杭州", "wikipedia:余华"),
    ("贾平凹", "male", "1952-02-21", "12:00", "商洛", "wikipedia:贾平凹"),
    ("金庸", "male", "1924-03-10", "12:00", "海宁", "wikipedia:金庸"),
    ("古龙", "male", "1938-06-07", "12:00", "香港", "wikipedia:古龙"),
    ("琼瑶", "female", "1938-04-20", "12:00", "成都", "wikipedia:琼瑶"),
    ("三毛", "female", "1943-03-26", "12:00", "重庆", "wikipedia:三毛"),
    ("林语堂", "male", "1895-10-10", "12:00", "漳州", "wikipedia:林语堂"),
    ("巴金", "male", "1904-11-25", "12:00", "成都", "wikipedia:巴金"),
    ("老舍", "male", "1899-02-03", "12:00", "北京", "wikipedia:老舍"),
    ("沈从文", "male", "1902-12-28", "12:00", "凤凰", "wikipedia:沈从文"),
    ("钱钟书", "male", "1910-11-21", "12:00", "无锡", "wikipedia:钱钟书"),
    ("杨绛", "female", "1911-07-17", "12:00", "无锡", "wikipedia:杨绛"),
    # International public figures (Wikipedia)
    ("牛顿", "male", "1643-01-04", "12:00", "伦敦", "wikipedia:Isaac Newton"),
    ("爱因斯坦", "male", "1879-03-14", "11:30", "乌尔姆", "wikipedia:Albert Einstein"),
    ("达尔文", "male", "1809-02-12", "12:00", "伦敦", "wikipedia:Charles Darwin"),
    ("居里夫人", "female", "1867-11-07", "12:00", "华沙", "wikipedia:Marie Curie"),
    ("特斯拉", "male", "1856-07-10", "12:00", "未知", "wikipedia:Nikola Tesla"),
    ("爱迪生", "male", "1847-02-11", "12:00", "美国", "wikipedia:Thomas Edison"),
    ("霍金", "male", "1942-01-08", "12:00", "牛津", "wikipedia:Stephen Hawking"),
    ("图灵", "male", "1912-06-23", "12:00", "伦敦", "wikipedia:Alan Turing"),
    ("莎士比亚", "male", "1564-04-26", "12:00", "斯特拉特福", "wikipedia:William Shakespeare"),
    ("达芬奇", "male", "1452-04-15", "12:00", "佛罗伦萨", "wikipedia:Leonardo da Vinci"),
    ("米开朗基罗", "male", "1475-03-06", "12:00", "佛罗伦萨", "wikipedia:Michelangelo"),
    ("梵高", "male", "1853-03-30", "12:00", "赞德特", "wikipedia:Vincent van Gogh"),
    ("毕加索", "male", "1881-10-25", "12:00", "马拉加", "wikipedia:Pablo Picasso"),
    ("莫扎特", "male", "1756-01-27", "12:00", "萨尔茨堡", "wikipedia:Wolfgang Amadeus Mozart"),
    ("贝多芬", "male", "1770-12-17", "12:00", "波恩", "wikipedia:Ludwig van Beethoven"),
    ("巴赫", "male", "1685-03-31", "12:00", "艾森纳赫", "wikipedia:Johann Sebastian Bach"),
    ("肖邦", "male", "1810-03-01", "12:00", "华沙", "wikipedia:Frédéric Chopin"),
    ("拿破仑", "male", "1769-08-15", "12:00", "科西嘉", "wikipedia:Napoleon"),
    ("林肯", "male", "1809-02-12", "12:00", "美国", "wikipedia:Abraham Lincoln"),
    ("华盛顿", "male", "1732-02-22", "12:00", "美国", "wikipedia:George Washington"),
    ("罗斯福", "male", "1882-01-30", "12:00", "纽约", "wikipedia:Franklin D. Roosevelt"),
    ("丘吉尔", "male", "1874-11-30", "12:00", "伦敦", "wikipedia:Winston Churchill"),
    ("甘地", "male", "1869-10-02", "12:00", "博尔本德尔", "wikipedia:Mahatma Gandhi"),
    ("曼德拉", "male", "1918-07-18", "12:00", "南非", "wikipedia:Nelson Mandela"),
    ("马丁路德金", "male", "1929-01-15", "12:00", "亚特兰大", "wikipedia:Martin Luther King Jr."),
    ("肯尼迪", "male", "1917-05-29", "12:00", "波士顿", "wikipedia:John F. Kennedy"),
    ("里根", "male", "1911-02-06", "12:00", "伊利诺伊", "wikipedia:Ronald Reagan"),
    ("克林顿", "male", "1946-08-19", "12:00", "阿肯色", "wikipedia:Bill Clinton"),
    ("小布什", "male", "1946-07-06", "12:00", "康涅狄格", "wikipedia:George W. Bush"),
    ("奥巴马", "male", "1961-08-04", "19:24", "火奴鲁鲁", "wikipedia:Barack Obama"),
    ("特朗普", "male", "1946-06-14", "10:54", "纽约", "wikipedia:Donald Trump"),
    ("拜登", "male", "1942-11-20", "08:30", "斯克兰顿", "wikipedia:Joe Biden"),
    ("哈里斯", "female", "1964-10-20", "12:00", "奥克兰", "wikipedia:Kamala Harris"),
    ("普京", "male", "1952-10-07", "12:00", "圣彼得堡", "wikipedia:Vladimir Putin"),
    ("默克尔", "female", "1954-07-17", "12:00", "汉堡", "wikipedia:Angela Merkel"),
    ("马克龙", "male", "1977-12-21", "12:00", "亚眠", "wikipedia:Emmanuel Macron"),
    ("特蕾莎梅", "female", "1956-10-01", "12:00", "东伯恩茅斯", "wikipedia:Theresa May"),
    ("约翰逊", "male", "1964-06-19", "12:00", "纽约", "wikipedia:Boris Johnson"),
    ("特鲁多", "male", "1971-12-25", "12:00", "渥太华", "wikipedia:Justin Trudeau"),
    ("莫迪", "male", "1950-09-17", "12:00", "古吉拉特", "wikipedia:Narendra Modi"),
    ("安倍晋三", "male", "1954-09-21", "12:00", "东京", "wikipedia:Shinzo Abe"),
    ("岸田文雄", "male", "1957-07-29", "12:00", "东京", "wikipedia:Fumio Kishida"),
    ("金正恩", "male", "1984-01-08", "12:00", "平壤", "wikipedia:Kim Jong-un"),
    ("金日成", "male", "1912-04-15", "12:00", "平壤", "wikipedia:Kim Il-sung"),
    ("金正日", "male", "1941-02-16", "12:00", "苏联", "wikipedia:Kim Jong-il"),
    ("胡志明", "male", "1890-05-19", "12:00", "义安", "wikipedia:Ho Chi Minh"),
    ("李光耀", "male", "1923-09-16", "12:00", "新加坡", "wikipedia:Lee Kuan Yew"),
    ("李显龙", "male", "1952-02-10", "12:00", "新加坡", "wikipedia:Lee Hsien Loong"),
    ("马哈蒂尔", "male", "1925-07-10", "12:00", "吉打", "wikipedia:Mahathir Mohamad"),
    ("苏加诺", "male", "1901-06-06", "12:00", "泗水", "wikipedia:Sukarno"),
    ("阿基诺", "female", "1933-01-25", "12:00", "马尼拉", "wikipedia:Corazon Aquino"),
    ("朴槿惠", "female", "1952-02-02", "12:00", "大邱", "wikipedia:Park Geun-hye"),
    ("文在寅", "male", "1953-01-24", "12:00", "巨济", "wikipedia:Moon Jae-in"),
    ("尹锡悦", "male", "1960-12-18", "12:00", "首尔", "wikipedia:Yoon Suk-yeol"),
    ("李在明", "male", "1963-12-22", "12:00", "安东", "wikipedia:Lee Jae-myung"),
    # Tech / business international
    ("比尔盖茨", "male", "1955-10-28", "22:00", "西雅图", "wikipedia:Bill Gates"),
    ("乔布斯", "male", "1955-02-24", "19:15", "旧金山", "wikipedia:Steve Jobs"),
    ("马斯克", "male", "1971-06-28", "07:30", "比勒陀利亚", "wikipedia:Elon Musk"),
    ("扎克伯格", "male", "1984-05-14", "12:00", "纽约", "wikipedia:Mark Zuckerberg"),
    ("贝索斯", "male", "1964-01-12", "12:00", "阿尔布开克", "wikipedia:Jeff Bezos"),
    ("巴菲特", "male", "1930-08-30", "12:00", "奥马哈", "wikipedia:Warren Buffett"),
    ("索罗斯", "male", "1930-08-12", "12:00", "布达佩斯", "wikipedia:George Soros"),
    ("库克", "male", "1960-11-01", "12:00", "亚拉巴马", "wikipedia:Tim Cook"),
    ("纳德拉", "male", "1967-08-19", "12:00", "海得拉巴", "wikipedia:Satya Nadella"),
    ("皮查伊", "male", "1972-06-10", "12:00", "马杜赖", "wikipedia:Sundar Pichai"),
    ("奥特曼", "male", "1985-04-22", "12:00", "芝加哥", "wikipedia:Sam Altman"),
    ("黄仁勋", "male", "1963-02-17", "12:00", "台南", "wikipedia:Jensen Huang"),
    ("苏姿丰", "female", "1969-11-01", "12:00", "台南", "wikipedia:Lisa Su"),
    ("张忠谋", "male", "1931-07-10", "12:00", "宁波", "wikipedia:Morris Chang"),
    ("郭台铭", "male", "1950-10-08", "12:00", "台北", "wikipedia:Terry Gou"),
    ("王永庆", "male", "1917-01-18", "12:00", "台北", "wikipedia:Wang Yung-ching"),
    ("李嘉诚", "male", "1928-07-29", "06:00", "潮州", "wikipedia:Li Ka-shing"),
    ("李兆基", "male", "1928-02-20", "12:00", "顺德", "wikipedia:Lee Shau-kee"),
    ("郑裕彤", "male", "1925-08-26", "12:00", "顺德", "wikipedia:Cheng Yu-tung"),
    ("邵逸夫", "male", "1907-11-19", "12:00", "宁波", "wikipedia:Run Run Shaw"),
    # Sports international
    ("乔丹", "male", "1963-02-17", "12:00", "纽约", "wikipedia:Michael Jordan"),
    ("科比", "male", "1978-08-23", "12:00", "费城", "wikipedia:Kobe Bryant"),
    ("詹姆斯", "male", "1984-12-30", "12:00", "阿克伦", "wikipedia:LeBron James"),
    ("梅西", "male", "1987-06-24", "12:00", "罗萨里奥", "wikipedia:Lionel Messi"),
    ("C罗", "male", "1985-02-05", "12:00", "马德拉", "wikipedia:Cristiano Ronaldo"),
    ("贝克汉姆", "male", "1975-05-02", "12:00", "伦敦", "wikipedia:David Beckham"),
    ("马拉多纳", "male", "1960-10-30", "12:00", "布宜诺斯艾利斯", "wikipedia:Diego Maradona"),
    ("贝利", "male", "1940-10-23", "12:00", "特雷斯科拉索伊斯", "wikipedia:Pelé"),
    ("费德勒", "male", "1981-08-08", "12:00", "巴塞尔", "wikipedia:Roger Federer"),
    ("纳达尔", "male", "1986-06-03", "12:00", "马略卡", "wikipedia:Rafael Nadal"),
    ("德约科维奇", "male", "1987-05-22", "12:00", "贝尔格莱德", "wikipedia:Novak Djokovic"),
    ("博尔特", "male", "1986-08-21", "12:00", "牙买加", "wikipedia:Usain Bolt"),
    ("泰森", "male", "1966-06-30", "12:00", "纽约", "wikipedia:Mike Tyson"),
    ("阿里", "male", "1942-01-17", "12:00", "路易斯维尔", "wikipedia:Muhammad Ali"),
    # Entertainment international
    ("玛丽莲梦露", "female", "1926-06-01", "12:00", "洛杉矶", "wikipedia:Marilyn Monroe"),
    ("奥黛丽赫本", "female", "1929-05-04", "12:00", "布鲁塞尔", "wikipedia:Audrey Hepburn"),
    ("伊丽莎白泰勒", "female", "1932-02-27", "12:00", "伦敦", "wikipedia:Elizabeth Taylor"),
    ("汤姆汉克斯", "male", "1956-07-09", "12:00", "康科德", "wikipedia:Tom Hanks"),
    ("莱昂纳多", "male", "1974-11-11", "12:00", "洛杉矶", "wikipedia:Leonardo DiCaprio"),
    ("布拉德皮特", "male", "1963-12-18", "12:00", "肖尼", "wikipedia:Brad Pitt"),
    ("安吉丽娜朱莉", "female", "1975-06-04", "12:00", "洛杉矶", "wikipedia:Angelina Jolie"),
    ("斯嘉丽约翰逊", "female", "1984-11-22", "12:00", "纽约", "wikipedia:Scarlett Johansson"),
    ("泰勒斯威夫特", "female", "1989-12-13", "12:00", "雷丁", "wikipedia:Taylor Swift"),
    ("碧昂丝", "female", "1981-09-04", "12:00", "休斯顿", "wikipedia:Beyoncé"),
    ("迈克尔杰克逊", "male", "1958-08-29", "12:00", "加里", "wikipedia:Michael Jackson"),
    ("猫王", "male", "1935-01-08", "12:00", "图珀洛", "wikipedia:Elvis Presley"),
    ("披头士约翰", "male", "1940-10-09", "12:00", "利物浦", "wikipedia:John Lennon"),
    ("麦卡特尼", "male", "1942-06-18", "12:00", "利物浦", "wikipedia:Paul McCartney"),
    ("鲍勃迪伦", "male", "1941-05-24", "12:00", "德卢斯", "wikipedia:Bob Dylan"),
    ("麦当娜", "female", "1958-08-16", "12:00", "贝城", "wikipedia:Madonna"),
    ("LadyGaga", "female", "1986-03-28", "12:00", "纽约", "wikipedia:Lady Gaga"),
    ("Rihanna", "female", "1988-02-20", "12:00", "巴巴多斯", "wikipedia:Rihanna"),
    ("Adele", "female", "1988-05-05", "12:00", "伦敦", "wikipedia:Adele"),
    ("EdSheeran", "male", "1991-02-17", "12:00", "哈利法克斯", "wikipedia:Ed Sheeran"),
    ("BTS金南俊", "male", "1994-09-12", "12:00", "首尔", "wikipedia:RM (rapper)"),
    ("IU", "female", "1993-05-16", "12:00", "首尔", "wikipedia:IU (singer)"),
    ("权志龙", "male", "1988-08-18", "12:00", "首尔", "wikipedia:G-Dragon"),
    ("宋慧乔", "female", "1981-11-22", "12:00", "大邱", "wikipedia:Song Hye-kyo"),
    ("全智贤", "female", "1981-10-30", "12:00", "首尔", "wikipedia:Jun Ji-hyun"),
    ("李敏镐", "male", "1987-06-22", "12:00", "首尔", "wikipedia:Lee Min-ho"),
    ("金秀贤", "male", "1988-02-16", "12:00", "首尔", "wikipedia:Kim Soo-hyun"),
    # Royalty / historical (public)
    ("伊丽莎白二世", "female", "1926-04-21", "02:40", "伦敦", "wikipedia:Elizabeth II"),
    ("戴安娜王妃", "female", "1961-07-01", "19:45", "桑德灵厄姆", "wikipedia:Diana Princess of Wales"),
    ("查尔斯三世", "male", "1948-11-14", "12:00", "伦敦", "wikipedia:Charles III"),
    ("威廉王子", "male", "1982-06-21", "12:00", "伦敦", "wikipedia:William Prince of Wales"),
    ("哈利王子", "male", "1984-09-15", "12:00", "伦敦", "wikipedia:Prince Harry"),
    ("维多利亚女王", "female", "1819-05-24", "12:00", "伦敦", "wikipedia:Queen Victoria"),
    ("路易十四", "male", "1638-09-05", "12:00", "巴黎", "wikipedia:Louis XIV"),
    ("叶卡捷琳娜二世", "female", "1729-05-02", "12:00", "什切青", "wikipedia:Catherine the Great"),
    ("彼得大帝", "male", "1672-06-09", "12:00", "莫斯科", "wikipedia:Peter the Great"),
    ("亚历山大大帝", "male", "-0356-07-20", "12:00", "佩拉", "wikipedia:Alexander the Great"),
    ("凯撒", "male", "-0100-07-12", "12:00", "罗马", "wikipedia:Julius Caesar"),
    ("克利奥帕特拉", "female", "-0069-01-01", "12:00", "亚历山大", "wikipedia:Cleopatra"),
]


def make_record(
    name: str,
    gender: str,
    birth_date: str,
    birth_time: str,
    city: str,
    source: str,
    license_: str = "CC-BY-SA",
    events: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    try:
        y, m, d = map(int, birth_date.split("-"))
        # skip non-positive years (BCE) — datetime can't handle easily
        if y <= 0:
            return None
        hh, mm = 12, 0
        if birth_time:
            parts = birth_time.split(":")
            hh, mm = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        dt = datetime(y, m, d, hh, mm)
    except (ValueError, OverflowError):
        return None
    try:
        bazi = _bazi_str(dt)
    except Exception:
        return None
    return {
        "name": name,
        "gender": gender if gender in ("male", "female") else "male",
        "birth_date": f"{y:04d}-{m:02d}-{d:02d}",
        "birth_time": f"{hh:02d}:{mm:02d}",
        "location": _loc(city),
        "bazi": bazi,
        "source": source,
        "license": license_,
        "events": events or [],
    }


def load_qizheng() -> List[Dict[str, Any]]:
    if not QIZHENG.exists():
        return []
    out = []
    for line in QIZHENG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        name = o.get("name", "")
        bdt = o.get("birth_datetime", "")
        try:
            # 1893-12-26T07:30:00
            date_part, time_part = bdt.split("T")
            time_part = time_part[:5]
        except ValueError:
            continue
        notes = o.get("notes") or "未知"
        # crude city from notes
        city = "未知"
        for k in LOCS:
            if k in notes:
                city = k
                break
        # gender unknown in qizheng — default male unless known female names
        female_names = {
            "王菲", "范冰冰", "戴安娜王妃", "伊丽莎白二世", "居里夫人", "默克尔"
        }
        gender = "female" if name in female_names else "male"
        rec = make_record(
            name,
            gender,
            date_part,
            time_part,
            city,
            source=f"github:douyin-downloader/tools/qizheng/celebrity_charts ({notes})",
            license_="public",
        )
        if rec:
            # keep expected_bazi for optional consistency note
            if o.get("expected_bazi"):
                rec["expected_bazi_source"] = o["expected_bazi"]
            out.append(rec)
    return out


def build_yangyan_only() -> List[Dict[str, Any]]:
    path = next((p for p in YANGYAN_CANDIDATES if p.exists()), None)
    if not path:
        return []
    rows = []
    seen = set()
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        o = json.loads(line)
        bz = normalize_bazi(o.get("bazi", "") or "") or (o.get("bazi") or "")
        if not bz:
            continue
        key = bz.replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "id": f"yangyan_{i:04d}",
                "bazi": bz,
                "day_master": o.get("day_master", ""),
                "month_branch": o.get("month_branch", ""),
                "gender": o.get("gender") or "",
                "domains": o.get("domains") or {},
                "key_terms": o.get("key_terms") or [],
                "source": "yangyan_cases.jsonl",
                "license": "research-local",
                "note": "bazi-only; no public identity; for structure validators",
            }
        )
    return rows


def main() -> None:
    births, names, yangyan_bazis = load_dedup()
    print(f"dedup pool: births={len(births)} names={len(names)} yangyan_bazi={len(yangyan_bazis)}")

    candidates: List[Dict[str, Any]] = []
    source_counts: Dict[str, int] = {}
    license_counts: Dict[str, int] = {}
    skipped = {"birth": 0, "name": 0, "bazi_yangyan": 0, "internal": 0, "bad": 0}

    # S2: qizheng
    for rec in load_qizheng():
        candidates.append(rec)

    # S1: curated wiki public figures
    for name, gender, bdate, btime, city, source in CURATED:
        rec = make_record(name, gender, bdate, btime, city, source, "CC-BY-SA")
        if rec:
            candidates.append(rec)
        else:
            skipped["bad"] += 1

    # Dedup
    out: List[Dict[str, Any]] = []
    seen_birth: Set[str] = set(births)
    seen_name: Set[str] = set(names)
    seen_bazi: Set[str] = set(yangyan_bazis)

    for rec in candidates:
        nk = _name_key(rec["name"])
        y, m, d = map(int, rec["birth_date"].split("-"))
        hh, mm = map(int, rec["birth_time"].split(":"))
        bk = _birth_key(y, m, d, hh, mm)
        bz = (rec.get("bazi") or "").replace(" ", "")

        if nk and nk in seen_name:
            skipped["name"] += 1
            continue
        if bk in seen_birth:
            skipped["birth"] += 1
            continue
        # yangyan bazi overlap: still allow public named person, but track
        # Task: drop if bazi overlaps yangyan — follow strictly
        if bz and bz in yangyan_bazis:
            skipped["bazi_yangyan"] += 1
            continue
        if bz and bz in seen_bazi and nk in seen_name:
            skipped["internal"] += 1
            continue

        # internal dedup among new
        if bk in seen_birth or (nk and nk in seen_name):
            skipped["internal"] += 1
            continue

        seen_birth.add(bk)
        if nk:
            seen_name.add(nk)
        if bz:
            seen_bazi.add(bz)

        # strip internal helper fields
        rec.pop("expected_bazi_source", None)
        out.append(rec)
        # source family
        fam = "qizheng" if "qizheng" in rec["source"] else (
            "wikipedia" if rec["source"].startswith("wikipedia") else "other"
        )
        source_counts[fam] = source_counts.get(fam, 0) + 1
        license_counts[rec["license"]] = license_counts.get(rec["license"], 0) + 1

    OUT_EXTRA.parent.mkdir(parents=True, exist_ok=True)
    OUT_EXTRA.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT_EXTRA} n={len(out)}")
    print(f"skipped {skipped}")
    print(f"source_counts {source_counts}")
    print(f"license_counts {license_counts}")

    # S3 yangyan bazi-only
    yy = build_yangyan_only()
    with OUT_YANGYAN.open("w", encoding="utf-8") as f:
        for row in yy:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {OUT_YANGYAN} n={len(yy)}")

    # self-check sample
    print("sample records:")
    for r in out[:5]:
        print(f"  {r['name']} {r['birth_date']} {r['birth_time']} {r['bazi']}")


if __name__ == "__main__":
    main()
