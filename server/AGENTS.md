<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-07-01 | Updated: 2026-07-01 -->

# server

## Purpose

Optional FastAPI/uvicorn REST server for douyin-downloader. Exposes HTTP endpoints to submit download jobs, query status, cancel jobs, stream status updates via SSE, and apply runtime config overrides. Also hosts optional MingMirror destiny analysis endpoints under `/api/v1/bazi/`, `/api/v1/qizheng/`, and `/api/v1/destiny/`, and serves the bundled React web UI at `/app`.

The server module is optional — `fastapi`, `uvicorn`, and `pydantic` are listed under `[project.optional-dependencies]` in `pyproject.toml`.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Package marker |
| `app.py` | FastAPI application factory (`build_app`) and server entry (`run_server`) |
| `jobs.py` | Pure-Python job model (`DownloadJob`, `JobStatus`) and in-memory `JobManager` |

## API Endpoints

### Core Download Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Service health check |
| POST | `/api/v1/download` | Submit a URL download job |
| GET | `/api/v1/jobs/{job_id}` | Get a specific job's status/counts |
| GET | `/api/v1/jobs` | List recent jobs (TTL + capacity capped) |
| DELETE | `/api/v1/jobs/{job_id}` | Cancel a pending or running job |
| GET | `/api/v1/jobs/{job_id}/events` | SSE stream of job status changes |
| GET | `/api/v1/config` | Get current effective configuration (including runtime overrides) |
| POST | `/api/v1/config` | Apply runtime overrides (`thread`, `rate_limit`, `retry_times`, `proxy`) |

### Bazi (八字) Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/bazi/analyze` | Analyze a single bazi string with DeepSeek + RAG |
| POST | `/api/v1/bazi/timeline` | Return DaYun timeline for a bazi |
| POST | `/api/v1/bazi/yearly` | Yearly fine-grained analysis for a given year range |
| POST | `/api/v1/bazi/from_datetime` | Convert birth datetime to bazi pillars |
| GET | `/api/v1/bazi/cases` | List structured bazi cases used for retrieval |
| POST | `/api/v1/bazi/extract` | Run OCR-based bazi extraction over downloaded videos |
| POST | `/api/v1/bazi/feedback` | Record feedback for a bazi analysis |

### Qi Zheng (七政四余) Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/qizheng/analyze` | Qi Zheng natal chart analysis |
| POST | `/api/v1/qizheng/yearly` | Qi Zheng yearly analysis |

### Destiny (多命理融合) Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/destiny/analyze` | Multi-system (bazi/ziwei/qizheng) analysis |
| POST | `/api/v1/destiny/council` | Multi-Agent council debate |
| POST | `/api/v1/destiny/daily` | Daily weather / energy reading |
| GET | `/api/v1/destiny/systems` | List available destiny systems |
| POST | `/api/v1/charts/{chart_id}/events` | Record a life event for calibration |
| GET | `/api/v1/charts/{chart_id}/events` | List recorded life events |
| POST | `/api/v1/charts/{chart_id}/calibrate` | Calibrate system weights against events |

## For AI Agents

### Working In This Directory
- `server.app.build_app(config)` returns a ready-to-serve `FastAPI` instance.
- `_ServerDeps` holds shared heavyweight objects (`FileManager`, `RateLimiter`, `RetryHandler`, `QueueManager`, `CookieManager`) across requests.
- `DouyinAPIClient` is created per request to avoid aiohttp session leakage across async contexts.
- Runtime config overrides only support `thread`, `rate_limit`, `retry_times`, and `proxy`.
- `JobManager` stores jobs in memory only; process restart clears history.
- Job pruning uses TTL + capacity cap; in-flight jobs are never pruned.

### Shared Logic With Desktop
- CLI server is intentionally simpler than the desktop server.
- CLI has job cancel, SSE status stream, and runtime config overrides.
- Desktop adds license/DRM checks and UI-specific progress reporting; CLI does not.

### Testing Requirements
- Tests: `tests/test_server.py`, `tests/test_server_bazi.py`, `tests/test_server_enhance.py`, `tests/test_server_qizheng.py`, `tests/test_frontend_serve.py`, `tests/test_server_calibration.py`
- Mock FastAPI dependencies; do not hit real Douyin API or launch real browsers.

### Common Patterns
- `StreamingResponse` for SSE endpoints
- `asyncio.Semaphore` for per-manager concurrency control
- `asyncio.CancelledError` handling in `JobManager._run` for clean cancellation

## Dependencies

### Internal
- `auth/` — `CookieManager`
- `config/` — `ConfigLoader`
- `control/` — `QueueManager`, `RateLimiter`, `RetryHandler`
- `core/` — `DouyinAPIClient`, `DownloaderFactory`, `URLParser`
- `storage/` — `FileManager`
- `tools/bazi_ai/` / `tools/bazi_cli.py` — optional bazi endpoints

### External
- `fastapi` — web framework
- `uvicorn` — ASGI server
- `pydantic` — request/response models
