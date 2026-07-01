#!/usr/bin/env python3
"""
bazi_corrector.py — 用本地词典批量纠正八字命理 transcript 里的同音错别字

用法：
  python tools/bazi_corrector.py                          # 处理所有 .transcript.txt
  python tools/bazi_corrector.py -d ./Downloaded          # 指定目录
  python tools/bazi_corrector.py -f transcript.txt        # 单个文件
  python tools/bazi_corrector.py -t "这巴字..."           # 直接纠正一段文字
  python tools/bazi_corrector.py -g bazi_glossary.json    # 指定词表

输出：
  - 文件模式：原文件同目录下生成 *.transcript.corrected.txt
  - 文本模式：直接打印纠正后的文字
"""

import argparse
import json
import re
import sys
from pathlib import Path


def load_glossary(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("词表必须是 {错误词: 正确词} 的 JSON 对象")
    # 过滤空键
    return {k.strip(): v.strip() for k, v in data.items() if k.strip()}


def build_replacer(glossary: dict):
    """按词长降序构建正则替换器，优先匹配更长的词。"""
    sorted_items = sorted(glossary.items(), key=lambda kv: len(kv[0]), reverse=True)
    escaped = [re.escape(wrong) for wrong, _ in sorted_items]
    pattern = re.compile("|".join(escaped))
    return pattern, glossary


def correct_text(text: str, pattern, glossary: dict) -> str:
    return pattern.sub(lambda m: glossary.get(m.group(0), m.group(0)), text)


def correct_file(file_path: Path, pattern, glossary: dict, suffix: str = ".corrected"):
    text = file_path.read_text(encoding="utf-8")
    corrected = correct_text(text, pattern, glossary)
    out_path = file_path.with_suffix(suffix + file_path.suffix)
    out_path.write_text(corrected, encoding="utf-8")
    return out_path


def find_transcripts(directory: Path):
    return sorted(directory.rglob("*.transcript.txt"))


def main():
    parser = argparse.ArgumentParser(
        description="八字命理 transcript 本地词典纠错",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tools/bazi_corrector.py\n"
            "  python tools/bazi_corrector.py -d ./Downloaded\n"
            "  python tools/bazi_corrector.py -t '这巴字长得不错'"
        ),
    )
    parser.add_argument("-d", "--dir", default=".", help="扫描目录 (默认当前目录)")
    parser.add_argument("-f", "--file", help="单个 transcript 文件")
    parser.add_argument("-t", "--text", help="直接输入要纠正的文本")
    parser.add_argument("-g", "--glossary", default="bazi_glossary.json", help="词表 JSON 路径")
    parser.add_argument("--suffix", default=".corrected", help="输出文件后缀 (默认 .corrected)")
    args = parser.parse_args()

    glossary_path = Path(args.glossary)
    if not glossary_path.exists():
        print(f"词表不存在: {glossary_path}", file=sys.stderr)
        sys.exit(1)

    glossary = load_glossary(glossary_path)
    pattern, glossary = build_replacer(glossary)

    if args.text:
        print(correct_text(args.text, pattern, glossary))
        return

    if args.file:
        files = [Path(args.file)]
    else:
        files = find_transcripts(Path(args.dir))

    if not files:
        print("未找到 *.transcript.txt 文件")
        return

    total = 0
    for fp in files:
        out = correct_file(fp, pattern, glossary, args.suffix)
        total += 1
        print(f"✓ {fp} -> {out}")

    print(f"\n共处理 {total} 个文件，词表条目 {len(glossary)} 条")


if __name__ == "__main__":
    main()
