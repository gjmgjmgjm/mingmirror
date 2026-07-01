"""Tests for tools/bazi_cli.py CLI backend."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.bazi_cli import (
    build_knowledge_base_for_directory,
    extract_bazi_for_directory,
    scan_video_dirs,
    validate_bazi_format,
)


class TestValidateBaziFormat:
    @pytest.mark.parametrize("value, expected", [
        ("甲子 丙寅 戊辰 庚午", True),
        ("甲子丙寅戊辰庚午", True),
        ("甲子 丙寅 戊辰", False),
        ("", False),
        (None, False),
        ("invalid", False),
    ])
    def test_validate_bazi_format(self, value, expected):
        assert validate_bazi_format(value) is expected


class TestScanVideoDirs:
    def test_scan_video_dirs(self, tmp_path: Path):
        post_dir = tmp_path / "post"
        video_dir = post_dir / "2025-01-01_test_123"
        video_dir.mkdir(parents=True)
        (video_dir / "video.mp4").write_text("fake mp4")
        results = scan_video_dirs(tmp_path)
        assert len(results) == 1
        assert results[0][0] == video_dir
        assert results[0][1].name == "video.mp4"

    def test_scan_video_dirs_no_post(self, tmp_path: Path):
        assert scan_video_dirs(tmp_path) == []


class TestExtractBaziForDirectory:
    def test_resume_and_skip_already_processed(self, tmp_path: Path):
        post_dir = tmp_path / "post"
        video_dir = post_dir / "2025-01-01_test_123"
        video_dir.mkdir(parents=True)
        mp4 = video_dir / "video.mp4"
        mp4.write_text("fake")

        manifest_path = post_dir / "bazi_manifest.json"
        manifest_path.write_text(
            json.dumps({str(mp4.relative_to(tmp_path.parent)): "甲子 丙寅 戊辰 庚午"}, ensure_ascii=False),
            encoding="utf-8",
        )

        summary = extract_bazi_for_directory(tmp_path, tmp_path.parent, resume=True)
        assert summary["total"] == 1
        assert summary["skipped"] == 1
        assert summary["success"] == 0
        assert summary["failed"] == 0

    @patch("tools.bazi_cli.extract_bazi")
    @patch("tools.bazi_cli.tag_srt")
    def test_extract_and_tag_srt(self, mock_tag_srt, mock_extract_bazi, tmp_path: Path):
        mock_extract_bazi.return_value = "甲子 丙寅 戊辰 庚午"
        mock_ocr = MagicMock()

        post_dir = tmp_path / "post"
        video_dir = post_dir / "2025-01-01_test_123"
        video_dir.mkdir(parents=True)
        mp4 = video_dir / "video.mp4"
        mp4.write_text("fake")
        srt = video_dir / "video.transcript.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")

        summary = extract_bazi_for_directory(
            tmp_path,
            tmp_path.parent,
            duration=10,
            interval=1.0,
            resume=False,
            ocr=mock_ocr,
        )
        assert summary["total"] == 1
        assert summary["success"] == 1
        assert summary["failed"] == 0
        mock_tag_srt.assert_called_once()

    @patch("tools.bazi_cli.extract_bazi")
    def test_extract_failure_recorded(self, mock_extract_bazi, tmp_path: Path):
        mock_extract_bazi.return_value = None
        mock_ocr = MagicMock()

        post_dir = tmp_path / "post"
        video_dir = post_dir / "2025-01-01_test_123"
        video_dir.mkdir(parents=True)
        mp4 = video_dir / "video.mp4"
        mp4.write_text("fake")

        summary = extract_bazi_for_directory(
            tmp_path,
            tmp_path.parent,
            duration=10,
            interval=1.0,
            resume=False,
            ocr=mock_ocr,
        )
        assert summary["total"] == 1
        assert summary["success"] == 0
        assert summary["failed"] == 1


class TestBuildKnowledgeBaseForDirectory:
    def test_build_knowledge_base(self, tmp_path: Path):
        post_dir = tmp_path / "post"
        video_dir = post_dir / "2025-01-01_test_123"
        video_dir.mkdir(parents=True)

        manifest_path = post_dir / "bazi_manifest.json"
        manifest_path.write_text(
            json.dumps({str(video_dir / "video.mp4"): "甲子 丙寅 戊辰 庚午"}, ensure_ascii=False),
            encoding="utf-8",
        )
        srt = video_dir / "video.transcript.srt"
        srt.write_text(
            "1\n00:00:00,000 --> 00:00:05,000\n"
            "老师，您好，我想让您帮我看一下我的八字。我的八字是甲子丙寅戊辰庚午。\n"
            "您这个八字日主甲木生于寅月，身强，喜用神是金水，整体格局不错。\n",
            encoding="utf-8",
        )
        glossary_path = tmp_path / "glossary.json"
        glossary_path.write_text("{}", encoding="utf-8")

        output_path = tmp_path / "out.md"
        summary = build_knowledge_base_for_directory(
            tmp_path, output_path, glossary_path, version="v3"
        )
        assert output_path.exists()
        assert summary["output_path"] == output_path
        content = output_path.read_text(encoding="utf-8")
        assert "甲子 丙寅 戊辰 庚午" in content

    def test_unsupported_version(self, tmp_path: Path):
        with pytest.raises(ValueError):
            build_knowledge_base_for_directory(
                tmp_path, tmp_path / "out.md", tmp_path / "g.json", version="v99"
            )
