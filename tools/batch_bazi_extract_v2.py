#!/usr/bin/env python3
"""
batch_bazi_extract_v2.py — 改进版批量八字OCR提取（支持重试失败项）

用法：
  python tools/batch_bazi_extract_v2.py --input-dir ./Downloaded/作者名/post
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.extract_bazi_and_tag_srt import RapidOCR, extract_bazi, tag_srt


def main():
    parser = argparse.ArgumentParser(
        description="改进版批量八字OCR提取（支持重试失败项）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python tools/batch_bazi_extract_v2.py --input-dir ./Downloaded/作者名/post",
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="用户 post 目录，例如 ./Downloaded/作者名/post",
    )
    parser.add_argument(
        "--base-dir",
        default=".",
        help="计算相对路径的基准目录（默认当前目录）",
    )
    parser.add_argument(
        "--manifest-name",
        default="bazi_manifest.json",
        help="清单文件名（默认 bazi_manifest.json）",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="只取前 N 秒（默认 60）",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="每隔多少秒取一帧（默认 2 秒）",
    )
    args = parser.parse_args()

    user_dir = Path(args.input_dir)
    base_dir = Path(args.base_dir)
    manifest_path = user_dir / args.manifest_name

    # 加载已有的manifest
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = {}

    # 找出所有视频目录
    video_dirs = sorted([d for d in user_dir.iterdir() if d.is_dir()])

    # 筛选出还没有处理或识别失败的视频
    unprocessed = []
    for d in video_dirs:
        mp4_files = list(d.glob("*.mp4"))
        if not mp4_files:
            continue
        mp4 = mp4_files[0]
        rel_key = str(mp4.relative_to(base_dir))
        # 重新处理之前失败的视频
        if rel_key in manifest and manifest[rel_key] is not None:
            continue
        unprocessed.append((d, mp4))

    print(f"总共 {len(video_dirs)} 个视频，待处理 {len(unprocessed)} 个")

    if not unprocessed:
        print("所有视频已处理完毕！")
        return

    # 加载OCR模型
    print("正在加载 OCR 模型...")
    ocr = RapidOCR()

    # 处理每个视频
    success = 0
    failed = 0
    for i, (d, mp4) in enumerate(unprocessed, 1):
        print(f"\n[{i}/{len(unprocessed)}] 处理: {mp4.name[:50]}")

        try:
            bazi = extract_bazi(mp4, ocr, duration=args.duration, interval=args.interval)
            if bazi:
                # 检查是否有?标记
                if '?' in bazi:
                    print(f"  ~ 八字(部分识别): {bazi}")
                else:
                    print(f"  ✓ 八字: {bazi}")
                manifest[str(mp4.relative_to(base_dir))] = bazi
                success += 1

                # 处理SRT
                srts = list(d.glob("*.transcript.srt"))
                if srts:
                    srt = srts[0]
                    out = srt.with_suffix(".bazi.srt")
                    tag_srt(srt, bazi, out)
            else:
                print("  ✗ 未能识别八字")
                manifest[str(mp4.relative_to(base_dir))] = None
                failed += 1
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            manifest[str(mp4.relative_to(base_dir))] = None
            failed += 1

        # 每10个视频保存一次manifest
        if i % 10 == 0:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            print(f"  [进度保存] 已处理 {i}/{len(unprocessed)}")

    # 最终保存
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n处理完成！成功: {success}，失败: {failed}")

    # 统计最终结果
    total_success = sum(1 for v in manifest.values() if v is not None)
    print(f"总计识别成功: {total_success}/{len(manifest)}")


if __name__ == "__main__":
    main()
