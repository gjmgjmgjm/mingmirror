#!/usr/bin/env python3
"""
build_knowledge_base.py — 将视频转录内容整理成结构化知识库

用法：
  python tools/build_knowledge_base.py --users 杨炎:./Downloaded/杨炎/post
  python tools/build_knowledge_base.py --input-dir ./Downloaded/作者名/post
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


def extract_srt_text(srt_path: Path) -> str:
    """从SRT文件提取纯文本"""
    content = srt_path.read_text(encoding='utf-8')
    # 移除时间轴和序号，只保留文本
    lines = []
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        # 跳过纯数字行（序号）和时间轴行
        if re.match(r'^\d+$', line):
            continue
        if re.match(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', line):
            continue
        lines.append(line)
    return '\n'.join(lines)


def analyze_dialogue(text: str) -> Dict:
    """
    分析对话内容，识别说话人和内容

    返回格式：
    {
        'master': [...],  # 命主说的话
        'advisor': [...],  # 批八字的人说的话
        'unknown': []   # 无法识别的
    }
    """
    result = {'master': [], 'advisor': [], 'unknown': []}

    # 简单的启发式规则：
    # 1. 命主通常会说：我的八字、我的命运、我是XX年生的、我的婚姻、我的事业
    # 2. 批八字的人通常会说：你这个八字、你看、你这、你的命、走运、大运、流年

    master_patterns = [
        r'我是\d{4}', r'我的八字', r'我的命', r'我的婚姻', r'我的事业',
        r'我\d{2}岁', r'我的工作', r'我的家庭', r'我老公', r'我老婆',
        r'我的财运', r'我的健康', r'我想问', r'请问', r'老师',
    ]

    advisor_patterns = [
        r'你这个八字', r'你这八字', r'你看', r'你这', r'你的命',
        r'走运', r'大运', r'流年', r'命理', r'格局', r'十神',
        r'日主', r'月令', r'用神', r'忌神', r'喜用', r'身强', r'身弱',
        r'正官', r'七杀', r'正财', r'偏财', r'食神', r'伤官',
        r'正印', r'偏印', r'比肩', r'劫财',
    ]

    # 按段落分析
    paragraphs = text.split('\n')

    for para in paragraphs:
        para = para.strip()
        if not para or len(para) < 5:
            continue

        is_master = False
        is_advisor = False

        for pattern in master_patterns:
            if re.search(pattern, para):
                is_master = True
                break

        for pattern in advisor_patterns:
            if re.search(pattern, para):
                is_advisor = True
                break

        if is_master and not is_advisor:
            result['master'].append(para)
        elif is_advisor and not is_master:
            result['advisor'].append(para)
        else:
            result['unknown'].append(para)

    return result


def format_dialogue(dialogue: Dict, bazi: str) -> str:
    """格式化对话为知识库格式"""
    lines = []
    lines.append(f"## 八字：{bazi}")
    lines.append("")

    if dialogue['advisor']:
        lines.append("### 命理师分析")
        lines.append("")
        for text in dialogue['advisor']:
            lines.append(f"> {text}")
            lines.append("")

    if dialogue['master']:
        lines.append("### 命主反馈")
        lines.append("")
        for text in dialogue['master']:
            lines.append(f"- {text}")
        lines.append("")

    if dialogue['unknown']:
        lines.append("### 其他内容")
        lines.append("")
        for text in dialogue['unknown']:
            lines.append(f"- {text}")
        lines.append("")

    return '\n'.join(lines)


def build_knowledge_base(user_dir: Path, output_path: Path):
    """构建知识库"""

    # 读取八字manifest
    manifest_path = user_dir / 'bazi_manifest.json'
    if not manifest_path.exists():
        print(f"未找到manifest: {manifest_path}")
        return

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    # 筛选有八字的视频
    success_videos = [(k, v) for k, v in manifest.items() if v]

    print(f"找到 {len(success_videos)} 个有八字的视频")

    # 构建知识库
    knowledge_parts = []
    knowledge_parts.append("# 八字命理知识库")
    knowledge_parts.append("")
    knowledge_parts.append("来源：抖音命理师视频转录")
    knowledge_parts.append("")
    knowledge_parts.append("---")
    knowledge_parts.append("")

    # 按八字分组
    bazi_groups = {}
    for k, v in success_videos:
        if v not in bazi_groups:
            bazi_groups[v] = []
        bazi_groups[v].append(k)

    print(f"共有 {len(bazi_groups)} 个不同的八字")

    # 处理每个八字
    for bazi, video_paths in bazi_groups.items():
        knowledge_parts.append(f"# {bazi}")
        knowledge_parts.append("")

        for video_path_str in video_paths:
            video_path = Path(video_path_str)

            # 找SRT文件
            srt_files = list(video_path.parent.glob('*.transcript.srt'))
            if not srt_files:
                continue

            srt_path = srt_files[0]

            # 提取文本
            text = extract_srt_text(srt_path)
            if not text or len(text) < 50:
                continue

            # 分析对话
            dialogue = analyze_dialogue(text)

            # 格式化输出
            formatted = format_dialogue(dialogue, bazi)
            knowledge_parts.append(formatted)
            knowledge_parts.append("---")
            knowledge_parts.append("")

    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_content = '\n'.join(knowledge_parts)
    output_path.write_text(output_content, encoding='utf-8')

    print(f"\n知识库已保存到: {output_path}")
    print(f"总字数: {len(output_content)}")


def _parse_users(user_args: List[str]) -> List[Tuple[str, Path]]:
    """Parse --users strings in 'name:directory' format."""
    users = []
    for arg in user_args:
        if ":" not in arg:
            raise argparse.ArgumentTypeError(
                f"--users must be in 'name:directory' format, got: {arg}"
            )
        name, directory = arg.split(":", 1)
        users.append((name.strip(), Path(directory.strip())))
    return users


def main():
    parser = argparse.ArgumentParser(
        description="将视频转录内容整理成结构化知识库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tools/build_knowledge_base.py --users 杨炎:./Downloaded/杨炎/post\n"
            "  python tools/build_knowledge_base.py --input-dir ./Downloaded/作者名/post"
        ),
    )
    parser.add_argument(
        "--glossary",
        default="./bazi_glossary.json",
        help="纠错词典路径（默认 ./bazi_glossary.json）",
    )
    parser.add_argument(
        "--output-dir",
        default="./bazi_knowledge",
        help="知识库输出目录（默认 ./bazi_knowledge）",
    )
    parser.add_argument(
        "--users",
        action="append",
        metavar="NAME:DIR",
        help="用户名称与目录（可多次传入，格式 name:directory）",
    )
    parser.add_argument(
        "--input-dir",
        help="单个用户目录（目录名作为用户名称）",
    )
    parser.add_argument(
        "--base-dir",
        default=".",
        help="计算相对路径的基准目录（默认当前目录）",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    users: List[Tuple[str, Path]] = []
    if args.users:
        users.extend(_parse_users(args.users))
    if args.input_dir:
        input_path = Path(args.input_dir)
        # 如果目录名为 post/like/mix/music，作者名取上一级目录
        if input_path.name in ("post", "like", "mix", "music"):
            user_name = input_path.parent.name or input_path.name
        else:
            user_name = input_path.name
        users.append((user_name, input_path))

    if not users:
        parser.error("请至少指定 --users 或 --input-dir")

    for name, user_dir in users:
        if not user_dir.exists():
            print(f"跳过不存在的目录: {user_dir}")
            continue
        print(f"\n处理用户: {name}")
        output_path = output_dir / f"{name}_knowledge.md"
        build_knowledge_base(user_dir, output_path)


if __name__ == "__main__":
    main()
