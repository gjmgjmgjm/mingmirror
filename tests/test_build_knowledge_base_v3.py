"""Tests for tools/build_knowledge_base_v3.py."""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.build_knowledge_base_v3 import (
    _parse_users,
    analyze_dialogue_ai,
    build_knowledge_base_v3,
    correct_text,
    extract_bazi_from_text,
    extract_srt_text,
    load_glossary,
    main,
)


class TestParseUsers:
    def test_parse_single_user(self):
        users = _parse_users(["杨炎:./Downloaded/杨炎/post"])
        assert len(users) == 1
        assert users[0][0] == "杨炎"
        assert users[0][1] == Path("./Downloaded/杨炎/post")

    def test_parse_multiple_users(self):
        users = _parse_users([
            "杨炎:./Downloaded/杨炎/post",
            "作者B:./Downloaded/作者B/post",
        ])
        assert len(users) == 2
        assert users[0] == ("杨炎", Path("./Downloaded/杨炎/post"))
        assert users[1] == ("作者B", Path("./Downloaded/作者B/post"))

    def test_parse_invalid_format(self):
        with pytest.raises(argparse.ArgumentTypeError):
            _parse_users(["invalid_without_colon"])


class TestLoadGlossary:
    def test_load_empty_glossary(self, tmp_path: Path):
        glossary_path = tmp_path / "g.json"
        glossary_path.write_text("{}", encoding="utf-8")
        assert load_glossary(glossary_path) == {}

    def test_load_glossary_with_entries(self, tmp_path: Path):
        glossary_path = tmp_path / "g.json"
        glossary_path.write_text(
            json.dumps({"巴字": "八字"}, ensure_ascii=False),
            encoding="utf-8",
        )
        glossary = load_glossary(glossary_path)
        assert glossary["巴字"] == "八字"


class TestCorrectText:
    def test_correct_text(self):
        glossary = {"巴字": "八字", "八只": "八字"}
        assert correct_text("这巴字不错", glossary) == "这八字不错"
        assert correct_text("这八只不错", glossary) == "这八字不错"


class TestExtractSrtText:
    def test_extract_srt_text(self, tmp_path: Path):
        srt = tmp_path / "test.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n你好世界\n\n"
            "2\n00:00:03,000 --> 00:00:04,000\n第二行\n",
            encoding="utf-8",
        )
        text = extract_srt_text(srt)
        assert "你好世界" in text
        assert "第二行" in text
        assert "00:00:01,000" not in text


class TestExtractBaziFromText:
    def test_extract_valid_bazi(self):
        text = "我的八字是 甲子 丙寅 戊辰 庚午"
        assert extract_bazi_from_text(text) == "甲子 丙寅 戊辰 庚午"

    def test_extract_no_bazi(self):
        assert extract_bazi_from_text("没有八字") is None


class TestAnalyzeDialogueAi:
    def test_identify_advisor(self):
        dialogue = analyze_dialogue_ai("你这个八字身强，喜用神是金水。")
        assert len(dialogue["advisor"]) == 1

    def test_identify_master(self):
        dialogue = analyze_dialogue_ai("我想问我的事业和婚姻。")
        assert len(dialogue["master"]) == 1


class TestBuildKnowledgeBaseV3:
    def _make_video_dir(self, parent: Path, video_name: str, bazi: str, srt_text: str) -> Path:
        video_dir = parent / video_name
        video_dir.mkdir(parents=True, exist_ok=True)
        srt = video_dir / f"{video_name}.transcript.srt"
        srt.write_text(srt_text, encoding="utf-8")
        return video_dir

    def test_generates_knowledge_final_md(self, tmp_path: Path, capsys):
        user_dir = tmp_path / "author" / "post"
        user_dir.mkdir(parents=True, exist_ok=True)

        video_dir = user_dir / "video_001"
        video_dir.mkdir(parents=True, exist_ok=True)
        mp4_path = video_dir / "video_001.mp4"
        mp4_path.write_text("fake", encoding="utf-8")

        manifest = {str(mp4_path): "甲子 丙寅 戊辰 庚午"}
        manifest_path = user_dir / "bazi_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        self._make_video_dir(
            user_dir,
            "video_001",
            "甲子 丙寅 戊辰 庚午",
            "1\n00:00:01,000 --> 00:00:02,000\n"
            "你这八字身强，喜用神是金水，格局清正，未来事业财运都有不错发展空间，"
            "适合从事金融、科技类工作，婚姻方面也比较顺利。\n",
        )

        glossary_path = tmp_path / "glossary.json"
        glossary_path.write_text("{}", encoding="utf-8")
        glossary = load_glossary(glossary_path)

        output_path = tmp_path / "out" / "author_knowledge_final.md"
        build_knowledge_base_v3(user_dir, output_path, glossary)

        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert "甲子 丙寅 戊辰 庚午" in content
        assert "命理师分析" in content

    def test_glossary_correction_applied(self, tmp_path: Path):
        user_dir = tmp_path / "author" / "post"
        user_dir.mkdir(parents=True, exist_ok=True)

        video_dir = user_dir / "video_001"
        video_dir.mkdir(parents=True, exist_ok=True)
        mp4_path = video_dir / "video_001.mp4"
        mp4_path.write_text("fake", encoding="utf-8")

        manifest = {str(mp4_path): "甲子 丙寅 戊辰 庚午"}
        manifest_path = user_dir / "bazi_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        self._make_video_dir(
            user_dir,
            "video_001",
            "甲子 丙寅 戊辰 庚午",
            "1\n00:00:01,000 --> 00:00:02,000\n"
            "这巴字身强，喜用神是金水，格局清正，未来事业财运都有不错发展空间，"
            "适合从事金融、科技类工作，婚姻方面也比较顺利。\n",
        )
        (video_dir / "video_001.mp4").write_text("fake", encoding="utf-8")

        glossary_path = tmp_path / "glossary.json"
        glossary_path.write_text(
            json.dumps({"巴字": "八字"}, ensure_ascii=False),
            encoding="utf-8",
        )
        glossary = load_glossary(glossary_path)

        output_path = tmp_path / "out" / "author_knowledge_final.md"
        build_knowledge_base_v3(user_dir, output_path, glossary)

        content = output_path.read_text(encoding="utf-8")
        assert "八字" in content
        assert "巴字" not in content

    def test_no_manifest_returns_early(self, tmp_path: Path, capsys):
        user_dir = tmp_path / "empty" / "post"
        user_dir.mkdir(parents=True, exist_ok=True)
        output_path = tmp_path / "out" / "empty_knowledge_final.md"
        build_knowledge_base_v3(user_dir, output_path, {})
        assert not output_path.exists()


class TestMain:
    def test_main_with_input_dir(self, tmp_path: Path):
        user_dir = tmp_path / "杨炎" / "post"
        user_dir.mkdir(parents=True, exist_ok=True)

        video_dir = user_dir / "video_001"
        video_dir.mkdir(parents=True, exist_ok=True)
        mp4_path = video_dir / "video_001.mp4"
        mp4_path.write_text("fake", encoding="utf-8")

        manifest = {str(mp4_path): "甲子 丙寅 戊辰 庚午"}
        manifest_path = user_dir / "bazi_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        srt = video_dir / "video_001.transcript.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n"
            "你这八字身强，喜用神是金水，格局清正，未来事业财运都有不错发展空间，"
            "适合从事金融、科技类工作，婚姻方面也比较顺利。\n",
            encoding="utf-8",
        )

        glossary_path = tmp_path / "glossary.json"
        glossary_path.write_text("{}", encoding="utf-8")

        output_dir = tmp_path / "knowledge"

        argv = [
            "build_knowledge_base_v3.py",
            "--input-dir", str(user_dir),
            "--output-dir", str(output_dir),
            "--glossary", str(glossary_path),
        ]
        with patch.object(sys, "argv", argv):
            main()

        expected = output_dir / "杨炎_knowledge_final.md"
        assert expected.exists()
        assert "甲子 丙寅 戊辰 庚午" in expected.read_text(encoding="utf-8")

    def test_main_with_users(self, tmp_path: Path):
        user_dir = tmp_path / "作者A" / "post"
        user_dir.mkdir(parents=True, exist_ok=True)

        video_dir = user_dir / "video_001"
        video_dir.mkdir(parents=True, exist_ok=True)
        mp4_path = video_dir / "video_001.mp4"
        mp4_path.write_text("fake", encoding="utf-8")

        manifest = {str(mp4_path): "乙卯 戊寅 庚子 丙子"}
        manifest_path = user_dir / "bazi_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        srt = video_dir / "video_001.transcript.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n"
            "你这八字身弱，喜用神是木火，格局清正，未来事业财运都有不错发展空间，"
            "适合从事文化、教育类工作，健康方面需要多加注意。\n",
            encoding="utf-8",
        )

        glossary_path = tmp_path / "glossary.json"
        glossary_path.write_text("{}", encoding="utf-8")

        output_dir = tmp_path / "knowledge"

        argv = [
            "build_knowledge_base_v3.py",
            "--users", f"作者A:{user_dir}",
            "--output-dir", str(output_dir),
            "--glossary", str(glossary_path),
        ]
        with patch.object(sys, "argv", argv):
            main()

        expected = output_dir / "作者A_knowledge_final.md"
        assert expected.exists()

    def test_main_without_users_or_input_dir_exits(self, tmp_path: Path):
        glossary_path = tmp_path / "glossary.json"
        glossary_path.write_text("{}", encoding="utf-8")

        argv = [
            "build_knowledge_base_v3.py",
            "--glossary", str(glossary_path),
        ]
        with patch.object(sys, "argv", argv):
            with pytest.raises(SystemExit):
                main()
