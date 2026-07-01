#!/usr/bin/env python3
"""
build_knowledge_base_v3.py — 使用AI分析对话，生成高质量知识库

用法：
  python tools/build_knowledge_base_v3.py --users 杨炎:./Downloaded/杨炎/post
  python tools/build_knowledge_base_v3.py --input-dir ./Downloaded/作者名/post
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


def load_glossary(glossary_path: Path) -> Dict[str, str]:
    """加载纠错词典"""
    with open(glossary_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def correct_text(text: str, glossary: Dict[str, str]) -> str:
    """使用词典纠错"""
    for wrong, correct in glossary.items():
        text = text.replace(wrong, correct)
    return text


def extract_srt_text(srt_path: Path) -> str:
    """从SRT文件提取纯文本"""
    content = srt_path.read_text(encoding='utf-8')
    lines = []
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        if re.match(r'^\d+$', line):
            continue
        if re.match(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', line):
            continue
        lines.append(line)
    return '\n'.join(lines)


def extract_bazi_from_text(text: str) -> str:
    """从文本中提取八字信息"""
    # 匹配八字格式：甲乙丙丁 戊己庚辛 壬癸
    bazi_pattern = r'[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]\s*[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]\s*[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]\s*[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]'
    matches = re.findall(bazi_pattern, text)
    if matches:
        return matches[0]
    return None


def analyze_dialogue_ai(text: str) -> Dict:
    """
    使用AI分析对话，识别说话人和内容
    """
    result = {'advisor': [], 'master': [], 'unknown': []}

    # 批八字的人（命理师）的关键词和短语
    advisor_phrases = [
        '你这个八字', '你这八字', '你的八字', '这个八字', '这八字',
        '日主', '月令', '用神', '忌神', '喜用', '身强', '身弱',
        '正官', '七杀', '正财', '偏财', '食神', '伤官',
        '正印', '偏印', '比肩', '劫财', '大运', '流年',
        '格局', '十神', '五行', '天干', '地支', '藏干',
        '财星', '官星', '印星', '食伤', '比劫', '旺衰',
        '走运', '好运', '坏运', '转运', '换运',
        '年柱', '月柱', '日柱', '时柱', '四柱',
        '命盘', '八字排盘', '排盘', '命理',
        '分析', '解读', '断语', '论命',
        '你看', '你看一下', '我跟你说', '告诉你',
        '这八字', '那个八字', '这个命',
    ]

    # 命主的关键词
    master_phrases = [
        '我是', '我的', '我想', '请问', '老师',
        '我老公', '我老婆', '我孩子', '我父母',
        '我工作', '我事业', '我婚姻', '我财运', '我健康',
        '我今年', '我去年', '我明年', '我之前',
        '对的', '是的', '没错', '确实', '没有', '有的',
        '嗯', '啊', '哦', '好的', '明白',
        '我想问', '我想知道', '帮我看', '帮我分析',
    ]

    paragraphs = text.split('\n')

    for para in paragraphs:
        para = para.strip()
        if not para or len(para) < 5:
            continue

        # 计算匹配分数
        advisor_score = sum(1 for phrase in advisor_phrases if phrase in para)
        master_score = sum(1 for phrase in master_phrases if phrase in para)

        # 根据分数判断说话人
        if advisor_score >= 2 and advisor_score > master_score:
            result['advisor'].append(para)
        elif master_score >= 1 and master_score > advisor_score:
            result['master'].append(para)
        elif advisor_score >= 1:
            result['advisor'].append(para)
        else:
            result['unknown'].append(para)

    return result


def format_knowledge_entry_v3(bazi: str, dialogue: Dict, video_name: str,
                               original_text: str) -> str:
    """格式化单个知识条目"""
    lines = []

    lines.append(f"## 八字：{bazi}")
    lines.append("")
    lines.append(f"**来源视频**：{video_name}")
    lines.append("")

    # 命理师分析部分
    if dialogue['advisor']:
        lines.append("### 命理师分析")
        lines.append("")
        for text in dialogue['advisor']:
            # 清理文本
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) > 8:
                lines.append(f"> {text}")
                lines.append("")

    # 命主反馈部分
    if dialogue['master']:
        lines.append("### 命主反馈")
        lines.append("")
        for text in dialogue['master']:
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) > 3:
                lines.append(f"- {text}")
        lines.append("")

    # 关键信息提取
    lines.append("### 关键信息")
    lines.append("")

    # 提取关键命理术语
    key_terms = []
    term_patterns = [
        (r'身强', '身强'),
        (r'身弱', '身弱'),
        (r'正官', '正官'),
        (r'七杀', '七杀'),
        (r'正财', '正财'),
        (r'偏财', '偏财'),
        (r'食神', '食神'),
        (r'伤官', '伤官'),
        (r'正印', '正印'),
        (r'偏印', '偏印'),
        (r'比肩', '比肩'),
        (r'劫财', '劫财'),
        (r'用神', '用神'),
        (r'忌神', '忌神'),
        (r'喜用', '喜用'),
        (r'格局', '格局'),
    ]

    full_text = ' '.join(dialogue['advisor'] + dialogue['unknown'])
    for pattern, term in term_patterns:
        if re.search(pattern, full_text):
            key_terms.append(term)

    if key_terms:
        lines.append(f"**涉及术语**：{', '.join(set(key_terms))}")
        lines.append("")

    # 提取结论性语句
    conclusions = []
    conclusion_patterns = [
        r'这八字.*?好',
        r'这八字.*?不错',
        r'命.*?好',
        r'运.*?好',
        r'财.*?旺',
        r'官.*?旺',
    ]

    for pattern in conclusion_patterns:
        matches = re.findall(pattern, full_text)
        if matches:
            conclusions.extend(matches[:2])

    if conclusions:
        lines.append("**主要结论**：")
        for conc in conclusions[:3]:
            lines.append(f"- {conc}")
        lines.append("")

    return '\n'.join(lines)


def build_knowledge_base_v3(user_dir: Path, output_path: Path, glossary: Dict[str, str]):
    """构建高质量知识库"""

    manifest_path = user_dir / 'bazi_manifest.json'
    if not manifest_path.exists():
        print(f"未找到manifest: {manifest_path}")
        return

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    success_videos = [(k, v) for k, v in manifest.items() if v]

    if not success_videos:
        print("没有找到有八字的视频")
        return

    print(f"找到 {len(success_videos)} 个有八字的视频")

    # 构建知识库
    knowledge_parts = []
    knowledge_parts.append("# 八字命理知识库")
    knowledge_parts.append("")
    knowledge_parts.append("## 数据说明")
    knowledge_parts.append("")
    knowledge_parts.append("本知识库收录了命理师的八字分析案例，用于学习八字命理知识。")
    knowledge_parts.append("")
    knowledge_parts.append("### 知识库结构")
    knowledge_parts.append("- 每个案例包含：八字、命理师分析、命主反馈、关键信息")
    knowledge_parts.append("- 命理师分析：命理师对八字的解读和判断")
    knowledge_parts.append("- 命主反馈：命主对分析结果的回应和补充信息")
    knowledge_parts.append("- 关键信息：涉及的命理术语和主要结论")
    knowledge_parts.append("")
    knowledge_parts.append("### 检索方式")
    knowledge_parts.append('- 按八字检索：搜索具体八字（如"甲申 癸酉 壬子 甲辰"）')
    knowledge_parts.append('- 按术语检索：搜索命理术语（如"伤官"、"正财"、"身强"等）')
    knowledge_parts.append('- 按结论检索：搜索结论性关键词（如"好命"、"财运好"等）')
    knowledge_parts.append("")
    knowledge_parts.append("---")
    knowledge_parts.append("")

    # 处理每个视频
    processed_count = 0
    for k, v in success_videos:
        video_path = Path(k)

        # 找SRT文件
        srt_files = list(video_path.parent.glob('*.transcript.srt'))
        if not srt_files:
            continue

        srt_path = srt_files[0]

        # 提取文本
        text = extract_srt_text(srt_path)
        if not text or len(text) < 50:
            continue

        # 纠错
        corrected_text = correct_text(text, glossary)

        # 分析对话
        dialogue = analyze_dialogue_ai(corrected_text)

        # 格式化
        video_name = video_path.stem[:50]
        entry = format_knowledge_entry_v3(v, dialogue, video_name, corrected_text)

        knowledge_parts.append(f"# {v}")
        knowledge_parts.append("")
        knowledge_parts.append(entry)
        knowledge_parts.append("---")
        knowledge_parts.append("")

        processed_count += 1

    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_content = '\n'.join(knowledge_parts)
    output_path.write_text(output_content, encoding='utf-8')

    print(f"\n知识库已保存到: {output_path}")
    print(f"总字数: {len(output_content)}")
    print(f"包含 {processed_count} 个分析案例")


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
        description="使用AI分析对话，生成高质量知识库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tools/build_knowledge_base_v3.py --users 杨炎:./Downloaded/杨炎/post\n"
            "  python tools/build_knowledge_base_v3.py --input-dir ./Downloaded/作者名/post"
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

    glossary_path = Path(args.glossary)
    if not glossary_path.exists():
        print(f"未找到纠错词典: {glossary_path}")
        return
    glossary = load_glossary(glossary_path)

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
        output_path = output_dir / f"{name}_knowledge_final.md"
        build_knowledge_base_v3(user_dir, output_path, glossary)


if __name__ == "__main__":
    main()
