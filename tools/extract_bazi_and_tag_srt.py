#!/usr/bin/env python3
"""
extract_bazi_and_tag_srt.py — 从抖音视频画面的八字排盘里 OCR 出四柱八字，
并把八字加到 SRT 字幕每段开头。

用法：
  python tools/extract_bazi_and_tag_srt.py -d ./Downloaded
  python tools/extract_bazi_and_tag_srt.py -f video.mp4 -s video.transcript.srt
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:  # pragma: no cover
    print("缺少 rapidocr_onnxruntime，请先安装：pip install rapidocr-onnxruntime --no-deps", file=sys.stderr)
    raise

# ── 八字常量 ──
STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
HEADERS = ["年柱", "月柱", "日柱", "时柱"]
ROW_LABELS = {"天干": "stem", "地支": "branch", "主星": "god", "藏干": "hide"}
TEN_GODS = ["比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印"]

# 天干 -> (阴阳, 五行)  0=阳 1=阴
STEM_ATTR = {
    "甲": (0, "木"),
    "乙": (1, "木"),
    "丙": (0, "火"),
    "丁": (1, "火"),
    "戊": (0, "土"),
    "己": (1, "土"),
    "庚": (0, "金"),
    "辛": (1, "金"),
    "壬": (0, "水"),
    "癸": (1, "水"),
}

# 五行生克关系
PRODUCE = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
CONQUER = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def infer_stem(day_stem: str, ten_god: str) -> Optional[str]:
    """根据日主和十神反推天干。"""
    if day_stem not in STEM_ATTR or ten_god not in TEN_GODS:
        return None
    yin, elem = STEM_ATTR[day_stem]

    target_elem = None
    target_yin = None

    if ten_god == "比肩":
        target_elem, target_yin = elem, yin
    elif ten_god == "劫财":
        target_elem, target_yin = elem, 1 - yin
    elif ten_god == "食神":
        target_elem, target_yin = PRODUCE[elem], yin
    elif ten_god == "伤官":
        target_elem, target_yin = PRODUCE[elem], 1 - yin
    elif ten_god == "偏财":
        target_elem, target_yin = CONQUER[elem], yin
    elif ten_god == "正财":
        target_elem, target_yin = CONQUER[elem], 1 - yin
    elif ten_god == "七杀":
        target_elem, target_yin = next(k for k, v in CONQUER.items() if v == elem), yin
    elif ten_god == "正官":
        target_elem, target_yin = next(k for k, v in CONQUER.items() if v == elem), 1 - yin
    elif ten_god == "偏印":
        target_elem, target_yin = next(k for k, v in PRODUCE.items() if v == elem), yin
    elif ten_god == "正印":
        target_elem, target_yin = next(k for k, v in PRODUCE.items() if v == elem), 1 - yin

    if target_elem is None:
        return None
    for s, (y, e) in STEM_ATTR.items():
        if e == target_elem and y == target_yin:
            return s
    return None


def clean_branch(text: str) -> Optional[str]:
    for b in BRANCHES:
        if b in text:
            return b
    return None


def clean_stem(text: str) -> Optional[str]:
    for s in STEMS:
        if s in text:
            return s
    # 常见 OCR 误识别修正
    mapping = {"Z": "乙", "E": "壬", "T": "丁"}
    return mapping.get(text.strip())


def nearest_col(cx: float, col_centers: List[Tuple[str, float]]) -> str:
    return min(col_centers, key=lambda c: abs(c[1] - cx))[0]


def extract_frames(video_path: Path, out_dir: Path, duration: Optional[int] = None, interval: float = 2.0) -> List[Path]:
    """按 interval 秒间隔抽取整个视频（或前 duration 秒）的画面。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "frame_%03d.jpg"
    vf = f"fps=1/{interval}"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(video_path),
    ]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += [
        "-vf", vf,
        "-q:v", "2",
        str(pattern),
        "-y",
    ]
    subprocess.run(cmd, check=True)
    return sorted(out_dir.glob("frame_*.jpg"))


def parse_frame(ocr_result) -> Optional[Dict[str, Dict[str, object]]]:
    """从单帧 OCR 结果解析出每列的 天干/地支/主星。"""
    items = ocr_result[0] if isinstance(ocr_result, tuple) else ocr_result
    if not items:
        return None

    # 收集所有条目，计算中心点
    entries = []
    for box, text, score in items:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        entries.append({
            "text": text.strip(),
            "cx": sum(xs) / len(xs),
            "cy": sum(ys) / len(ys),
            "score": score,
        })

    # 找四柱表头，确定列中心
    headers = [e for e in entries if e["text"] in HEADERS]
    if len(headers) < 3:
        return None
    col_centers = sorted([(e["text"], e["cx"]) for e in headers], key=lambda x: x[1])

    # 找行标签位置
    row_y = {}
    for e in entries:
        if e["text"] in ROW_LABELS:
            row_y[ROW_LABELS[e["text"]]] = e["cy"]
    if "stem" not in row_y or "branch" not in row_y:
        return None

    result = {col: {"stem": {}, "branch": {}, "god": {}} for col, _ in col_centers}

    for e in entries:
        text = e["text"]
        if text in HEADERS or text in ROW_LABELS or text in {"日期", "藏干"}:
            continue

        # 根据 y 距离判断属于哪一行
        row_dists = {k: abs(e["cy"] - y) for k, y in row_y.items()}
        row = min(row_dists, key=row_dists.get)
        if row_dists[row] > 60:  # 太远则忽略
            continue

        col = nearest_col(e["cx"], col_centers)

        if row == "stem":
            s = clean_stem(text)
            if s:
                result[col]["stem"][s] = result[col]["stem"].get(s, 0) + 1
        elif row == "branch":
            b = clean_branch(text)
            if b:
                result[col]["branch"][b] = result[col]["branch"].get(b, 0) + 1
        elif row == "god":
            if text in TEN_GODS:
                result[col]["god"][text] = result[col]["god"].get(text, 0) + 1

    return result


def best(d: Dict[str, int]) -> Optional[str]:
    return max(d, key=d.get) if d else None


def extract_bazi(video_path: Path, ocr, duration: Optional[int] = None, interval: float = 2.0) -> Optional[str]:
    """返回类似 '乙卯 戊寅 庚子 丙子' 的八字字符串；逐帧扫描，识别成功即返回。"""
    with tempfile.TemporaryDirectory(prefix="bazi_frames_") as tmp:
        frames = extract_frames(video_path, Path(tmp), duration=duration, interval=interval)
        aggregated = {col: {"stem": {}, "branch": {}, "god": {}} for col in HEADERS}

        for frame in frames:
            res = ocr(str(frame))
            parsed = parse_frame(res)
            if not parsed:
                continue

            # 累加当前帧结果
            for col in HEADERS:
                for k in ("stem", "branch", "god"):
                    for val, cnt in parsed[col][k].items():
                        aggregated[col][k][val] = aggregated[col][k].get(val, 0) + cnt

            # 尝试用已累加的数据拼出完整八字，一旦成功即可提前结束
            bazi = _assemble_bazi(aggregated)
            if bazi:
                return bazi

        return _assemble_bazi(aggregated)


def _assemble_bazi(aggregated: Dict[str, Dict[str, Dict[str, int]]]) -> Optional[str]:
    day_stem = best(aggregated["日柱"]["stem"])
    pillars = []
    missing_count = 0

    for col in HEADERS:
        stem = best(aggregated[col]["stem"])
        branch = best(aggregated[col]["branch"])

        # 尝试通过十神推断天干
        if not stem and day_stem and col != "日柱":
            god = best(aggregated[col]["god"])
            if god:
                stem = infer_stem(day_stem, god)

        # 日柱天干缺失时使用日主
        if not stem and day_stem and col == "日柱":
            stem = day_stem

        # 统计缺失数量
        if not stem or not branch:
            missing_count += 1

        # 允许最多1个柱缺失（但至少要有日柱）
        if missing_count > 1:
            return None

        if stem and branch:
            pillars.append(f"{stem}{branch}")
        elif stem:
            pillars.append(f"{stem}?")  # 标记缺失的地支
        elif branch:
            pillars.append(f"?{branch}")  # 标记缺失的天干
        else:
            pillars.append("??")  # 完全缺失

    # 至少要有3个完整的柱才能返回
    complete_pillars = [p for p in pillars if '?' not in p]
    if len(complete_pillars) >= 3:
        return " ".join(pillars)

    return None


def tag_srt(srt_path: Path, bazi: str, out_path: Path):
    text = srt_path.read_text(encoding="utf-8")
    tag = f"【八字：{bazi}】"

    # 简单 SRT 块解析
    blocks = re.split(r"\n\s*\n", text.strip())
    new_blocks = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            new_blocks.append(block)
            continue
        # 前两条是序号和时间轴，第三条起是字幕内容
        new_blocks.append("\n".join(lines[:2] + [tag] + lines[2:]))

    out_path.write_text("\n\n".join(new_blocks) + "\n", encoding="utf-8")


def find_videos(directory: Path) -> List[Path]:
    return sorted(directory.rglob("*.mp4"))


def main():
    parser = argparse.ArgumentParser(
        description="OCR 提取视频画面中的八字，并写入 SRT 字幕",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tools/extract_bazi_and_tag_srt.py -d ./Downloaded\n"
            "  python tools/extract_bazi_and_tag_srt.py -f ./Downloaded/xxx/xxx.mp4 -s ./xxx.srt"
        ),
    )
    parser.add_argument("-d", "--dir", default=".", help="扫描目录 (默认当前目录)")
    parser.add_argument("-f", "--file", help="单个视频文件")
    parser.add_argument("-s", "--srt", help="单个 SRT 字幕文件（配合 -f 使用）")
    parser.add_argument("--duration", type=int, default=None, help="只取前 N 秒（默认取整个视频）")
    parser.add_argument("--interval", type=float, default=2.0, help="每隔多少秒取一帧（默认 2 秒）")
    args = parser.parse_args()

    print("正在加载 OCR 模型...")
    ocr = RapidOCR()

    if args.file:
        videos = [Path(args.file)]
    else:
        videos = find_videos(Path(args.dir))

    if not videos:
        print("未找到 mp4 视频文件")
        return

    manifest = {}
    success = 0
    for video in videos:
        print(f"\n处理: {video}")
        bazi = extract_bazi(video, ocr, duration=args.duration, interval=args.interval)
        if not bazi:
            print("  ✗ 未能识别八字")
            manifest[str(video)] = None
            continue
        print(f"  ✓ 八字: {bazi}")
        manifest[str(video)] = bazi
        success += 1

        # 找同目录下的 srt
        if args.srt and len(videos) == 1:
            srt = Path(args.srt)
        else:
            srts = list(video.parent.glob("*.transcript.srt"))
            srt = srts[0] if srts else None

        if srt and srt.exists():
            out = srt.with_suffix(".bazi.srt")
            tag_srt(srt, bazi, out)
            print(f"  ✓ 字幕已写入: {out}")
        else:
            print("  ⚠ 未找到字幕文件")

    # 保存清单
    manifest_path = Path(args.dir if not args.file else Path(args.file).parent) / "bazi_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n共处理 {len(videos)} 个视频，成功 {success} 个")
    print(f"清单保存至: {manifest_path}")


if __name__ == "__main__":
    main()
