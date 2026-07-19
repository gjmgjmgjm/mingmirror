"""Tests for bazi (八字) utility tools."""

import json
from pathlib import Path

import pytest

from tools.bazi_corrector import build_replacer, correct_file, correct_text, load_glossary

# extract_bazi_and_tag_srt imports RapidOCR (onnxruntime) at module load.
_HAS_OCR = True
try:
    from tools.extract_bazi_and_tag_srt import (  # noqa: E402
        BRANCHES,
        HEADERS,
        STEMS,
        TEN_GODS,
        _assemble_bazi,
        clean_branch,
        clean_stem,
        infer_stem,
        nearest_col,
        parse_frame,
        tag_srt,
    )
except ImportError:
    _HAS_OCR = False
    BRANCHES = HEADERS = STEMS = TEN_GODS = ()  # type: ignore
    _assemble_bazi = clean_branch = clean_stem = infer_stem = None  # type: ignore
    nearest_col = parse_frame = tag_srt = None  # type: ignore

requires_ocr = pytest.mark.skipif(not _HAS_OCR, reason="onnxruntime/rapidocr not installed")


@requires_ocr
class TestBaziConstants:
    """Sanity checks for bazi lookup tables."""

    def test_stems_length(self):
        assert len(STEMS) == 10

    def test_branches_length(self):
        assert len(BRANCHES) == 12

    def test_headers(self):
        assert HEADERS == ["年柱", "月柱", "日柱", "时柱"]

    def test_ten_gods_length(self):
        assert len(TEN_GODS) == 10


@requires_ocr
class TestInferStem:
    """Tests for infer_stem based on day stem and ten-god relationship."""

    @pytest.mark.parametrize(
        "day_stem, ten_god, expected",
        [
            ("甲", "比肩", "甲"),
            ("甲", "劫财", "乙"),
            ("甲", "食神", "丙"),
            ("甲", "伤官", "丁"),
            ("甲", "偏财", "戊"),
            ("甲", "正财", "己"),
            ("甲", "七杀", "庚"),
            ("甲", "正官", "辛"),
            ("甲", "偏印", "壬"),
            ("甲", "正印", "癸"),
            ("丙", "食神", "戊"),
            ("丙", "伤官", "己"),
            ("壬", "正财", "丁"),
            ("戊", "七杀", "甲"),
        ],
    )
    def test_infer_stem_valid(self, day_stem, ten_god, expected):
        assert infer_stem(day_stem, ten_god) == expected

    def test_infer_stem_invalid_stem(self):
        assert infer_stem("X", "比肩") is None

    def test_infer_stem_invalid_god(self):
        assert infer_stem("甲", "财神") is None


@requires_ocr
class TestCleanStem:
    """Tests for clean_stem OCR post-processing."""

    @pytest.mark.parametrize("text, expected", [
        ("甲", "甲"),
        ("乙", "乙"),
        ("Z", "乙"),  # common OCR misread
        ("E", "壬"),
        ("T", "丁"),
        ("X", None),
    ])
    def test_clean_stem(self, text, expected):
        assert clean_stem(text) == expected


@requires_ocr
class TestCleanBranch:
    """Tests for clean_branch OCR post-processing."""

    @pytest.mark.parametrize("text, expected", [
        ("子", "子"),
        ("寅", "寅"),
        ("foo寅bar", "寅"),
        ("XYZ", None),
    ])
    def test_clean_branch(self, text, expected):
        assert clean_branch(text) == expected


@requires_ocr
class TestNearestCol:
    """Tests for nearest_col helper."""

    def test_nearest_col(self):
        centers = [("年柱", 50.0), ("月柱", 150.0), ("日柱", 250.0), ("时柱", 350.0)]
        assert nearest_col(60.0, centers) == "年柱"
        assert nearest_col(140.0, centers) == "月柱"
        assert nearest_col(300.0, centers) == "日柱"


def _box(x, y, w=30, h=20):
    """Build a simple rectangular OCR box."""
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


@requires_ocr
class TestParseFrame:
    """Tests for parse_frame with mocked OCR output."""

    def _make_ocr_result(self, items):
        """items: list of (text, cx, cy) tuples."""
        return [[_box(cx, cy), text, 0.95] for text, cx, cy in items]

    def test_parse_frame_complete_table(self):
        ocr_result = self._make_ocr_result([
            ("年柱", 50, 30), ("月柱", 150, 30), ("日柱", 250, 30), ("时柱", 350, 30),
            ("天干", 10, 80), ("地支", 10, 120), ("主星", 10, 160),
            ("甲", 50, 80), ("丙", 150, 80), ("戊", 250, 80), ("庚", 350, 80),
            ("子", 50, 120), ("寅", 150, 120), ("辰", 250, 120), ("午", 350, 120),
            ("比肩", 50, 160), ("食神", 150, 160), ("偏财", 250, 160), ("正官", 350, 160),
        ])
        parsed = parse_frame(ocr_result)
        assert parsed is not None
        assert parsed["年柱"]["stem"]["甲"] == 1
        assert parsed["月柱"]["branch"]["寅"] == 1
        assert parsed["日柱"]["god"]["偏财"] == 1
        assert parsed["时柱"]["stem"]["庚"] == 1

    def test_parse_frame_missing_headers(self):
        ocr_result = self._make_ocr_result([
            ("天干", 10, 80), ("地支", 10, 120),
            ("甲", 50, 80), ("子", 50, 120),
        ])
        assert parse_frame(ocr_result) is None

    def test_parse_frame_missing_row_labels(self):
        ocr_result = self._make_ocr_result([
            ("年柱", 50, 30), ("月柱", 150, 30), ("日柱", 250, 30), ("时柱", 350, 30),
            ("甲", 50, 80), ("子", 50, 120),
        ])
        assert parse_frame(ocr_result) is None

    def test_parse_tuple_wrapping(self):
        """RapidOCR sometimes returns (results, elapse)."""
        items = self._make_ocr_result([
            ("年柱", 50, 30), ("月柱", 150, 30), ("日柱", 250, 30), ("时柱", 350, 30),
            ("天干", 10, 80), ("地支", 10, 120),
            ("甲", 50, 80), ("丙", 150, 80), ("戊", 250, 80), ("庚", 350, 80),
            ("子", 50, 120), ("寅", 150, 120), ("辰", 250, 120), ("午", 350, 120),
        ])
        parsed = parse_frame((items, 0.5))
        assert parsed is not None
        assert parsed["年柱"]["stem"]["甲"] == 1


@requires_ocr
class TestAssembleBazi:
    """Tests for _assemble_bazi."""

    def _agg(self, data):
        """Build aggregated structure from dict of pillar -> (stem, branch, god)."""
        aggregated = {col: {"stem": {}, "branch": {}, "god": {}} for col in HEADERS}
        for col, (stem, branch, god) in data.items():
            if stem:
                aggregated[col]["stem"][stem] = 1
            if branch:
                aggregated[col]["branch"][branch] = 1
            if god:
                aggregated[col]["god"][god] = 1
        return aggregated

    def test_complete_bazi(self):
        aggregated = self._agg({
            "年柱": ("甲", "子", "比肩"),
            "月柱": ("丙", "寅", "食神"),
            "日柱": ("戊", "辰", None),
            "时柱": ("庚", "午", "正官"),
        })
        assert _assemble_bazi(aggregated) == "甲子 丙寅 戊辰 庚午"

    def test_partial_bazi_with_god_inference(self):
        aggregated = self._agg({
            "年柱": (None, "子", "比肩"),
            "月柱": ("丙", "寅", "食神"),
            "日柱": ("戊", "辰", None),
            "时柱": ("庚", "午", "正官"),
        })
        # 年柱天干 should be inferred as 比肩 of 戊 -> 戊
        assert _assemble_bazi(aggregated) == "戊子 丙寅 戊辰 庚午"

    def test_missing_one_pillar(self):
        aggregated = self._agg({
            "年柱": ("甲", "子", "比肩"),
            "月柱": ("丙", "寅", "食神"),
            "日柱": ("戊", "辰", None),
            "时柱": (None, None, None),
        })
        result = _assemble_bazi(aggregated)
        assert result is not None
        assert result.count("??") == 1

    def test_missing_two_pillars(self):
        aggregated = self._agg({
            "年柱": (None, None, None),
            "月柱": ("丙", "寅", "食神"),
            "日柱": ("戊", "辰", None),
            "时柱": (None, None, None),
        })
        assert _assemble_bazi(aggregated) is None


@requires_ocr
class TestTagSrt:
    """Tests for tag_srt."""

    def test_tag_srt_basic(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\nHello world\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nSecond line\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.srt"
        tag_srt(srt, "甲子 丙寅 戊辰 庚午", out)
        content = out.read_text(encoding="utf-8")
        assert "【八字：甲子 丙寅 戊辰 庚午】" in content
        assert "Hello world" in content
        assert "Second line" in content


class TestBaziCorrector:
    """Tests for bazi_corrector."""

    def test_load_glossary(self, tmp_path: Path):
        path = tmp_path / "glossary.json"
        path.write_text(json.dumps({"巴字": "八字", "日竹": "日主"}, ensure_ascii=False), encoding="utf-8")
        glossary = load_glossary(path)
        assert glossary["巴字"] == "八字"
        assert glossary["日竹"] == "日主"

    def test_load_glossary_invalid_type(self, tmp_path: Path):
        path = tmp_path / "glossary.json"
        path.write_text(json.dumps(["a", "b"]), encoding="utf-8")
        with pytest.raises(ValueError):
            load_glossary(path)

    def test_correct_text(self):
        glossary = {"巴字": "八字", "日竹": "日主"}
        pattern, _ = build_replacer(glossary)
        assert correct_text("这巴字不错", pattern, glossary) == "这八字不错"
        assert correct_text("我的日竹是甲", pattern, glossary) == "我的日主是甲"

    def test_correct_file(self, tmp_path: Path):
        glossary = {"巴字": "八字"}
        pattern, glos = build_replacer(glossary)
        src = tmp_path / "test.transcript.txt"
        src.write_text("这巴字很长", encoding="utf-8")
        out = correct_file(src, pattern, glos)
        assert out.exists()
        assert out.read_text(encoding="utf-8") == "这八字很长"


class TestKnowledgeBaseV3Helpers:
    """Tests for helper functions in build_knowledge_base_v3."""

    def test_extract_srt_text(self, tmp_path: Path):
        from tools.build_knowledge_base_v3 import extract_srt_text

        srt = tmp_path / "test.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\nFirst line.\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nSecond line.\n",
            encoding="utf-8",
        )
        text = extract_srt_text(srt)
        assert "First line." in text
        assert "Second line." in text
        assert "00:00" not in text

    def test_extract_bazi_from_text(self, tmp_path: Path):
        from tools.build_knowledge_base_v3 import extract_bazi_from_text

        text = "我的八字是 甲子 丙寅 戊辰 庚午，请老师看看。"
        assert extract_bazi_from_text(text) == "甲子 丙寅 戊辰 庚午"

    def test_analyze_dialogue_ai(self):
        from tools.build_knowledge_base_v3 import analyze_dialogue_ai

        text = "\n".join([
            "老师，我的八字怎么样？",
            "你这个八字身强，喜用神是金水。",
            "那我的财运呢？",
            "财星很旺，明年流年不错。",
        ])
        result = analyze_dialogue_ai(text)
        assert any("你这个八字" in s for s in result["advisor"])
        assert any("我的八字" in s for s in result["master"])


class TestKnowledgeBaseV2Helpers:
    """Tests for helper functions in build_knowledge_base_v2."""

    def test_analyze_dialogue_v2(self):
        from tools.build_knowledge_base_v2 import analyze_dialogue_v2

        text = "\n".join([
            "我是1990年出生的。",
            "你的八字日主很强，格局不错。",
            "请问我的婚姻怎么样？",
            "正官星透干，婚姻稳定。",
        ])
        result = analyze_dialogue_v2(text)
        assert any("八字" in s for s in result["advisor"])
        assert any("我是" in s for s in result["master"])
