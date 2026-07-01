#!/usr/bin/env python3
"""
batch_bazi_extract.py — 批量处理剩余视频的八字OCR提取
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.extract_bazi_and_tag_srt import RapidOCR, extract_bazi, tag_srt


def main():
    post_dir = Path("D:/douyin-downloader-main/Downloaded/杨炎/post")

    # 加载已有的manifest
    manifest_path = post_dir / "bazi_manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = {}

    # 找出所有视频目录
    video_dirs = sorted([d for d in post_dir.iterdir() if d.is_dir()])

    # 筛选出还没有处理的视频
    unprocessed = []
    for d in video_dirs:
        mp4_files = list(d.glob("*.mp4"))
        if not mp4_files:
            continue
        mp4 = mp4_files[0]
        # 检查是否已在manifest中且有值
        rel_key = str(mp4.relative_to(Path("D:/douyin-downloader-main")))
        if rel_key in manifest and manifest[rel_key] is not None:
            continue
        unprocessed.append((d, mp4))

    print(f"总共 {len(video_dirs)} 个视频，已处理 {len(video_dirs) - len(unprocessed)} 个，待处理 {len(unprocessed)} 个")

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
        print(f"\n[{i}/{len(unprocessed)}] 处理: {mp4.name}")

        try:
            bazi = extract_bazi(mp4, ocr, duration=60, interval=2)
            if bazi:
                print(f"  ✓ 八字: {bazi}")
                manifest[str(mp4.relative_to(Path("D:/douyin-downloader-main")))] = bazi
                success += 1

                # 处理SRT
                srts = list(d.glob("*.transcript.srt"))
                if srts:
                    srt = srts[0]
                    out = srt.with_suffix(".bazi.srt")
                    tag_srt(srt, bazi, out)
                    print(f"  ✓ 字幕已写入: {out.name}")
            else:
                print("  ✗ 未能识别八字")
                manifest[str(mp4.relative_to(Path("D:/douyin-downloader-main")))] = None
                failed += 1
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            manifest[str(mp4.relative_to(Path("D:/douyin-downloader-main")))] = None
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
    print(f"清单已保存至: {manifest_path}")


if __name__ == "__main__":
    main()
