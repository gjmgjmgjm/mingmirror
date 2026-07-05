<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-07-01 -->

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
| `bazi_ai/bazi_validator.py` | Validates and normalizes four-pillar bazi strings against the 60 JiaZi cycle |
| `bazi_ai/bazi_structural.py` | Structural profile extraction (day master, pattern, useful/taboo gods, pillar relations) |
| `bazi_ai/case_builder.py` | Parses `_knowledge_final.md` into structured `cases.jsonl`; validates and deduplicates cases |
| `bazi_ai/build_yangyan_kb.py` | Builds the Yangyan 八字绝技 structured case database from raw research materials |
| `bazi_ai/calendar.py` | Lunar calendar / solar-term utilities for datetime-to-bazi conversion |
| `bazi_ai/annotator.py` | Auto-labels cases with pattern, day-master strength, useful/taboo gods via LLM |
| `bazi_ai/embeddings.py` | Optional sentence-transformer embedding cache for semantic RAG retrieval |
| `bazi_ai/rule_checker.py` | Lightweight rule-based sanity checks for day-master strength and useful/taboo gods |
| `bazi_ai/engine.py` | DeepSeek + RAG bazi analysis engine with domain-aware retrieval and output validation |
| `bazi_ai/ensemble.py` | Multi-run consensus aggregation to reduce single-sample LLM variance |
| `bazi_ai/evaluator.py` | Consistency, format, case overlap, and leave-one-out benchmark evaluator |
| `bazi_ai/benchmark.py` | CLI wrapper for `evaluate_leave_one_out()` |
| `bazi_ai/cli.py` | Standalone CLI for `python -m tools.bazi_ai.cli` |
| `qizheng/engine.py` | Qi Zheng Si Yu analyzer with natal / yearly interpretation |
| `qizheng/calendar.py` | Astronomical calendar utilities for Qi Zheng calculations |
| `qizheng/prompts.py` | System and user prompts for Qi Zheng LLM analysis |
| `ziwei/engine.py` | Zi Wei Dou Shu analyzer |
| `ziwei/prompts.py` | System and user prompts for Zi Wei LLM analysis |
| `destiny/ensemble.py` | Multi-destiny analyzer with pluggable agent strategies |
| `destiny/calibrator.py` | Event calibration engine: match life events to predictions and adjust system weights |
| `destiny/benchmark_v2.py` | Quantitative benchmark against human-annotated cases |
| `destiny/strategies/reflection.py` | Self-critique and revision strategy |
| `destiny/strategies/debate.py` | Multi-system debate and consensus strategy |
| `destiny/strategies/tool_caller.py` | Rule-validation feedback strategy |
| `destiny/strategies/retriever.py` | Cross-system case retrieval (keyword + optional embeddings) |
| `frontend-handoff.md` | Handoff doc for the independent modern frontend developer |

## For AI Agents

### Working In This Directory
- `cookie_fetcher.py` requires the `[browser]` optional dependency (`playwright`)
- Bazi scripts require additional packages **not** listed in `requirements.txt`:
  - 八字相关工具需要额外安装 `pip install -r requirements-bazi.txt`
  - `rapidocr-onnxruntime` for frame OCR
  - `opencv-python` for image handling
  - Optional LLM packages for `build_knowledge_base_v3.py` AI analysis
- Bazi utilities are standalone; `tools/bazi_ai/` is now stable (validator, structural parser, calendar, RAG, embeddings, annotator, rule_checker, ensemble, REST API)
- `tools/bazi_ai/build_yangyan_kb.py` produces `bazi_knowledge/cases_yangyan.jsonl`; raw research materials are gitignored
- Destiny analyzers (`tools/ziwei/`, `tools/qizheng/`, `tools/destiny/`) are optional and currently rely on core dependencies only; `requirements-destiny.txt` is a placeholder
- `tools/destiny/strategies/` provides agent strategies: `reflection.py`, `debate.py`, `tool_caller.py`, `retriever.py`
- `tools/destiny/benchmark_v2.py` runs quantitative evaluation against `tools/destiny/benchmark_data/annotated_cases.jsonl` and writes `benchmark_report.json`
- `tools/destiny/ensemble.py` supports `strategy="single"|"reflection"|"debate"|"tool_augmented"`; default remains `"single"`
- `build_knowledge_base*.py` have been parameterized; use `--glossary`, `--users`, `--output-dir`, `--base-dir` instead of hard-coded paths
- Hard-coded absolute paths in `batch_bazi_extract*.py` should be parameterized before reuse

### Testing Requirements
- Tests: `tests/test_cookie_fetcher.py`
- Tests mock Playwright — do not launch real browsers
- Tests: `tests/test_bazi_tools.py` covers OCR parsing/assembly/correction helpers
- Tests: `tests/test_bazi_cli.py` covers the reusable backend
- Tests: `tests/test_bazi_validator.py`, `tests/test_bazi_ai.py`, `tests/test_bazi_ai_evaluator.py` cover validation, RAG, and evaluation
- Tests: `tests/test_bazi_calendar.py` covers lunar-calendar / solar-term utilities
- Tests: `tests/test_ziwei_engine.py`, `tests/test_qizheng_engine.py`, `tests/test_qizheng_calendar.py`, `tests/test_destiny_*.py` cover the multi-destiny subsystem
- Tests: `tests/test_destiny_reflection.py`, `tests/test_destiny_debate.py`, `tests/test_destiny_benchmark_v2.py` cover the new agent strategies and benchmark
- Tests: `tests/test_destiny_calibrator.py` covers event scoring, storage, and calibration aggregation

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
