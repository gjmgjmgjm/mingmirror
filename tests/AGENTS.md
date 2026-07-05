<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-07-01 -->

# tests

## Purpose
Pytest test suite with 68 test modules covering all major components. Uses `pytest-asyncio` for async test support.

## Key Files

| File | Description |
|------|-------------|
| `test_api_client.py` | API client request building and response parsing |
| `test_bazi_ai.py` | Bazi AI analysis engine |
| `test_bazi_ai_evaluator.py` | Bazi AI evaluator |
| `test_bazi_cli.py` | Bazi CLI backend |
| `test_bazi_tools.py` | Bazi OCR parsing/assembly/correction helpers |
| `test_bazi_embeddings.py` | Bazi embedding-based RAG fallback |
| `test_bazi_ensemble.py` | Bazi multi-run consensus aggregation |
| `test_bazi_rule_checker.py` | Bazi rule-based output validation |
| `test_bazi_validator.py` | Bazi four-pillar validation |
| `test_bazi_calendar.py` | Bazi lunar-calendar / solar-term utilities |
| `test_server_bazi.py` | Bazi REST API endpoints |
| `test_server_qizheng.py` | Qi Zheng REST API endpoints |
| `test_server_enhance.py` | REST server enhancements: cancel, SSE, config overrides |
| `test_frontend_serve.py` | Bundled React frontend static file serving |
| `test_ci_sanity.py` | Repository / CI consistency sanity checks |
| `test_build_knowledge_base_v3.py` | Knowledge-base builder parameterization |
| `test_user_modes_browser_fallback.py` | Browser fallback for like/mix/music user modes |
| `test_ziwei_engine.py` | Zi Wei Dou Shu analyzer |
| `test_qizheng_engine.py` | Qi Zheng Si Yu analyzer |
| `test_destiny_contract.py` | Multi-destiny shared data contract |
| `test_destiny_aligner.py` | Domain alignment across destiny systems |
| `test_destiny_ensemble.py` | Multi-destiny ensemble aggregation |
| `test_destiny_benchmark.py` | Single-system vs ensemble benchmark |
| `test_config_loader.py` | Config loading, merging, env overrides, cookie resolution |
| `test_config_validation.py` | Config validation edge cases |
| `test_cookie_fetcher.py` | Browser-based cookie fetching tool |
| `test_cookie_manager.py` | Cookie storage and validation |
| `test_cookie_utils.py` | Cookie parsing and sanitization helpers |
| `test_database.py` | SQLite history operations |
| `test_downloader_factory.py` | Factory URL-type to downloader mapping |
| `test_file_manager.py` | File path construction and writing |
| `test_mix_downloader.py` | Mix/collection download logic |
| `test_ms_token_manager.py` | MS token generation |
| `test_music_downloader.py` | Music download logic |
| `test_progress_display.py` | Rich progress display |
| `test_rate_limiter.py` | Rate limiting behavior |
| `test_retry_handler.py` | Retry with backoff |
| `test_transcript_manager.py` | Whisper transcription management |
| `test_url_parser.py` | URL classification |
| `test_user_downloader.py` | User content download orchestration |
| `test_user_downloader_modes.py` | User downloader mode integration |
| `test_user_mode_registry.py` | Mode strategy auto-discovery |
| `test_user_mode_strategies.py` | Individual strategy behavior |
| `test_video_downloader.py` | Video and gallery downloads |
| `test_xbogus.py` | Anti-bot signature generation |

## For AI Agents

### Working In This Directory
- Run all: `python -m pytest tests/`
- Run single: `python -m pytest tests/test_<module>.py -v`
- Async mode is `auto` — no need for `@pytest.mark.asyncio` decorators
- Tests use mocking extensively (`unittest.mock`, `AsyncMock`)
- No fixtures file (`conftest.py`) — fixtures are defined per-module

### Testing Requirements
- All new code must have corresponding tests
- Mock external HTTP calls (never hit real Douyin API)
- Use `AsyncMock` for async method mocking

### Common Patterns
- `@patch` decorators for dependency injection
- `AsyncMock(return_value=...)` for async API responses
- Direct class instantiation with mocked dependencies

## Dependencies

### External
- `pytest` — test runner
- `pytest-asyncio` — async test support

<!-- MANUAL: -->
