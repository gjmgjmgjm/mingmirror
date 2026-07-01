<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-06-30 -->

# tools

## Purpose
Standalone utility scripts — not part of the core download pipeline.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Package docstring |
| `cookie_fetcher.py` | Launches Playwright browser to authenticate with Douyin and extract cookies |
| `extract_bazi_and_tag_srt.py` | OCRs bazi (八字) pillars from video frames and tags SRT transcripts |
| `batch_bazi_extract.py` | Basic batch runner for `extract_bazi_and_tag_srt.py` |
| `batch_bazi_extract_v2.py` | Improved batch runner with resume support via `bazi_manifest.json` |
| `batch_bazi_extract_new_user.py` | Batch runner targeting a second user directory |
| `build_knowledge_base.py` | Heuristic dialogue analysis for bazi knowledge extraction |
| `build_knowledge_base_v2.py` | Enhanced dialogue analyzer with glossary correction |
| `build_knowledge_base_v3.py` | AI-assisted dialogue analysis for higher-quality knowledge bases |
| `bazi_corrector.py` | Corrects common OCR/transcription errors in bazi strings |
| `bazi_ai/case_builder.py` | Parses `_knowledge_final.md` into structured `cases.jsonl` |
| `bazi_ai/engine.py` | DeepSeek + RAG bazi analysis engine |
| `bazi_ai/cli.py` | Standalone CLI for `python -m tools.bazi_ai.cli` |

## For AI Agents

### Working In This Directory
- `cookie_fetcher.py` requires the `[browser]` optional dependency (`playwright`)
- Bazi scripts require additional packages **not** listed in `requirements.txt`:
  - 八字相关工具需要额外安装 `pip install -r requirements-bazi.txt`
  - `rapidocr-onnxruntime` for frame OCR
  - `opencv-python` for image handling
  - Optional LLM packages for `build_knowledge_base_v3.py` AI analysis
- Bazi utilities are **experimental** and currently standalone; they are not invoked by `cli.main`
- Hard-coded absolute paths in `batch_bazi_extract*.py` should be parameterized before reuse

### Testing Requirements
- Tests: `tests/test_cookie_fetcher.py`
- Tests mock Playwright — do not launch real browsers
- Tests: `tests/test_bazi_tools.py` covers OCR parsing/assembly/correction helpers; `tests/test_bazi_cli.py` covers the reusable backend

### Common Patterns
- Playwright async API for browser automation
- Cookie export as JSON dict for use with `ConfigLoader`
- Blocking I/O (file reads, subprocess, OCR inference) is acceptable here because these scripts run outside the async core pipeline
- `tools/bazi_cli.py` is the reusable backend used by `cli/main.py --extract-bazi` / `--build-knowledge-base`

## Dependencies

### Internal
- `utils/cookie_utils.py` — cookie sanitization

### External
- `playwright` — browser automation (optional dependency)
- `rapidocr-onnxruntime` — OCR for bazi extraction (optional, not in core requirements)
- DeepSeek API Key — for `bazi_ai/engine.py` (optional; falls back to mock mode without a key)

<!-- MANUAL: -->
