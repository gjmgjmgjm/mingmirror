#!/usr/bin/env python3
"""
bazi_cli.py — reusable CLI backend for bazi (八字) OCR and knowledge-base generation.

This module wraps the standalone scripts in ``extract_bazi_and_tag_srt.py`` and
``build_knowledge_base_v3.py`` so they can be invoked from ``cli.main`` and tested
without hard-coded paths.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "缺少 rapidocr_onnxruntime，请先安装：pip install rapidocr-onnxruntime --no-deps"
    ) from exc

from tools.build_knowledge_base_v3 import (
    build_knowledge_base_v3,
)
from tools.build_knowledge_base_v3 import (
    load_glossary as load_glossary_v3,
)
from tools.extract_bazi_and_tag_srt import extract_bazi, tag_srt

#: Regex for a single bazi pillar (one stem + one branch).
BAZI_PILLAR_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")


def validate_bazi_format(bazi: Optional[str]) -> bool:
    """Return True if *bazi* is a non-empty string containing exactly 4 pillars."""
    if not bazi or not isinstance(bazi, str):
        return False
    pillars = BAZI_PILLAR_RE.findall(bazi)
    return len(pillars) == 4


def scan_video_dirs(user_dir: Path) -> List[Tuple[Path, Path]]:
    """Return (video_dir, mp4_path) pairs under *user_dir*'s post directory."""
    post_dir = user_dir / "post"
    if not post_dir.exists():
        return []
    results = []
    for d in sorted(post_dir.iterdir()):
        if not d.is_dir():
            continue
        mp4_files = sorted(d.glob("*.mp4"))
        if mp4_files:
            results.append((d, mp4_files[0]))
    return results


def _rel_key(mp4: Path, base_dir: Path) -> str:
    """Return a stable relative-path key for manifest entries."""
    try:
        return str(mp4.relative_to(base_dir))
    except ValueError:
        return str(mp4.resolve())


def extract_bazi_for_directory(
    user_dir: Path,
    base_dir: Path,
    *,
    duration: int = 60,
    interval: float = 2.0,
    resume: bool = True,
    ocr=None,
) -> Dict[str, Any]:
    """Run OCR-based bazi extraction for every video under *user_dir*.

    Args:
        user_dir: Author directory (e.g. ``Downloaded/杨炎``).
        base_dir: Project root used to produce relative manifest keys.
        duration: Only scan the first N seconds of each video (0 = whole video).
        interval: Seconds between sampled frames.
        resume: Skip videos already present in ``user_dir/post/bazi_manifest.json``.
        ocr: Optional pre-initialized RapidOCR instance.

    Returns:
        A summary dict with ``manifest_path``, ``total``, ``success``, ``failed``,
        ``skipped``, and the updated ``manifest`` mapping.
    """
    post_dir = user_dir / "post"
    post_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = post_dir / "bazi_manifest.json"

    manifest: Dict[str, Optional[str]] = {}
    if resume and manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

    videos = scan_video_dirs(user_dir)
    to_process = []
    skipped = 0
    for d, mp4 in videos:
        key = _rel_key(mp4, base_dir)
        if resume and key in manifest and manifest[key] is not None:
            skipped += 1
            continue
        to_process.append((d, mp4, key))

    ocr_instance = ocr if ocr is not None else RapidOCR()
    success = 0
    failed = 0

    for i, (d, mp4, key) in enumerate(to_process, 1):
        try:
            bazi = extract_bazi(mp4, ocr_instance, duration=duration or None, interval=interval)
            manifest[key] = bazi
            if bazi:
                success += 1
                srts = sorted(d.glob("*.transcript.srt"))
                if srts:
                    out = srts[0].with_suffix(".bazi.srt")
                    tag_srt(srts[0], bazi, out)
            else:
                failed += 1
        except Exception:  # pragma: no cover - OCR/ffmpeg failures are logged by caller
            manifest[key] = None
            failed += 1

        if i % 10 == 0:
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "manifest_path": manifest_path,
        "total": len(videos),
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "manifest": manifest,
    }


def build_knowledge_base_for_directory(
    user_dir: Path,
    output_path: Path,
    glossary_path: Path,
    *,
    version: str = "v3",
) -> Dict[str, any]:
    """Build a markdown knowledge base from existing bazi manifest + SRT files.

    Args:
        user_dir: Author directory.
        output_path: Where to write the ``.md`` file.
        glossary_path: Path to the JSON glossary used for transcript correction.
        version: Currently only ``"v3"`` is supported (AI-enhanced formatter).

    Returns:
        Summary dict with ``output_path``, ``processed_count``, and ``total_cases``.
    """
    if version != "v3":
        raise ValueError(f"Unsupported knowledge-base version: {version!r}")

    glossary = load_glossary_v3(glossary_path)
    build_knowledge_base_v3(user_dir / "post", output_path, glossary)

    # Count entries in the generated file to provide a summary.
    processed_count = 0
    if output_path.exists():
        content = output_path.read_text(encoding="utf-8")
        processed_count = content.count("## 八字：")

    manifest_path = user_dir / "post" / "bazi_manifest.json"
    total_cases = 0
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        total_cases = sum(1 for v in manifest.values() if v)

    return {
        "output_path": output_path,
        "processed_count": processed_count,
        "total_cases": total_cases,
    }
