#!/usr/bin/env python3
"""
build_knowledge_base_v2.py — 将视频转录内容整理成结构化知识库（改进版）
"""

import json
import re
from pathlib import Path
from typing import Dict


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


def analyze_dialogue_v2(text: str) -> Dict:
    """
    改进的对话分析，使用更精确的规则
    """
    result = {'advisor': [], 'master': [], 'unknown': []}

    # 批八字的人（命理师）的关键词
    advisor_keywords = [
        '八字', '命理', '格局', '十神', '日主', '月令', '用神', '忌神',
        '身强', '身弱', '正官', '七杀', '正财', '偏财', '食神', '伤官',
        '正印', '偏印', '比肩', '劫财', '大运', '流年', '走运', '喜用',
        '五行', '天干', '地支', '藏干', '冲', '合', '刑', '害',
        '你这个', '你这', '你的', '你看', '分析', '格局', '命盘',
        '财星', '官星', '印星', '食伤', '比劫', '旺衰', '调候',
        '通关', '从格', '化格', '神煞', '桃花', '马星', '贵人',
        '年柱', '月柱', '日柱', '时柱', '四柱', '命宫', '身宫',
    ]

    # 命主的关键词
    master_keywords = [
        '我是', '我的', '我想', '请问', '老师', '咨询',
        '我老公', '我老婆', '我孩子', '我父母',
        '我工作', '我事业', '我婚姻', '我财运', '我健康',
        '我今年', '我去年', '我明年',
        '对的', '是的', '没错', '确实', '没有', '有的',
        '嗯', '啊', '哦', '好的',
    ]

    paragraphs = text.split('\n')

    for para in paragraphs:
        para = para.strip()
        if not para or len(para) < 3:
            continue

        # 计算匹配分数
        advisor_score = sum(1 for kw in advisor_keywords if kw in para)
        master_score = sum(1 for kw in master_keywords if kw in para)

        if advisor_score > master_score and advisor_score >= 2:
            result['advisor'].append(para)
        elif master_score > advisor_score and master_score >= 1:
            result['master'].append(para)
        elif advisor_score >= 1:
            result['advisor'].append(para)
        else:
            result['unknown'].append(para)

    return result


def format_knowledge_entry(bazi: str, dialogue: Dict, video_name: str) -> str:
    """格式化单个知识条目"""
    lines = []

    lines.append(f"### 八字：{bazi}")
    lines.append(f"**来源视频**：{video_name}")
    lines.append("")

    # 命理师分析部分
    if dialogue['advisor']:
        lines.append("**命理师分析**：")
        lines.append("")
        for text in dialogue['advisor']:
            # 清理文本，移除多余标点
            text = re.sub(r'[，。！？、]+', '', text)
            if len(text) > 5:
                lines.append(f"> {text}")
                lines.append("")

    # 命主反馈部分
    if dialogue['master']:
        lines.append("**命主反馈**：")
        lines.append("")
        for text in dialogue['master']:
            text = re.sub(r'[，。！？、]+', '', text)
            if len(text) > 3:
                lines.append(f"- {text}")
        lines.append("")

    # 其他内容
    if dialogue['unknown']:
        lines.append("**其他内容**：")
        lines.append("")
        for text in dialogue['unknown']:
            text = re.sub(r'[，。！？、]+', '', text)
            if len(text) > 5:
                lines.append(f"- {text}")
        lines.append("")

    return '\n'.join(lines)


def build_knowledge_base_v2(user_dir: Path, output_path: Path, glossary: Dict[str, str]):
    """构建改进版知识库"""

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

    # 按八字分组
    bazi_groups = {}
    for k, v in success_videos:
        if v not in bazi_groups:
            bazi_groups[v] = []
        bazi_groups[v].append(k)

    print(f"共有 {len(bazi_groups)} 个不同的八字")

    # 构建知识库
    knowledge_parts = []
    knowledge_parts.append("# 八字命理知识库")
    knowledge_parts.append("")
    knowledge_parts.append("## 使用说明")
    knowledge_parts.append("")
    knowledge_parts.append("本知识库收录了命理师的八字分析案例，用于学习八字命理知识。")
    knowledge_parts.append("")
    knowledge_parts.append("### 检索方式")
    knowledge_parts.append('- 按八字检索：直接搜索八字（如"甲申 癸酉 壬子 甲辰"）')
    knowledge_parts.append('- 按关键词检索：搜索命理术语（如"伤官"、"正财"、"身强"等）')
    knowledge_parts.append("- 按案例检索：浏览完整分析案例")
    knowledge_parts.append("")
    knowledge_parts.append("---")
    knowledge_parts.append("")

    # 处理每个八字
    all_entries = []
    for bazi, video_paths in bazi_groups.items():
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

            # 纠错
            corrected_text = correct_text(text, glossary)

            # 分析对话
            dialogue = analyze_dialogue_v2(corrected_text)

            # 格式化
            video_name = video_path.stem[:60]
            entry = format_knowledge_entry(bazi, dialogue, video_name)
            all_entries.append((bazi, entry))

    # 按八字排序
    all_entries.sort(key=lambda x: x[0])

    # 添加所有条目
    for bazi, entry in all_entries:
        knowledge_parts.append(f"# {bazi}")
        knowledge_parts.append("")
        knowledge_parts.append(entry)
        knowledge_parts.append("---")
        knowledge_parts.append("")

    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_content = '\n'.join(knowledge_parts)
    output_path.write_text(output_content, encoding='utf-8')

    print(f"\n知识库已保存到: {output_path}")
    print(f"总字数: {len(output_content)}")
    print(f"包含 {len(all_entries)} 个分析案例")


def main():
    # 加载纠错词典
    glossary_path = Path("D:/douyin-downloader-main/bazi_glossary.json")
    glossary = load_glossary(glossary_path)

    users = [
        ("杨炎", Path("D:/douyin-downloader-main/Downloaded/杨炎/post")),
    ]

    output_dir = Path("D:/douyin-downloader-main/bazi_knowledge")

    for name, user_dir in users:
        if user_dir.exists():
            print(f"\n处理用户: {name}")
            output_path = output_dir / f"{name}_knowledge_v2.md"
            build_knowledge_base_v2(user_dir, output_path, glossary)


if __name__ == "__main__":
    main()
