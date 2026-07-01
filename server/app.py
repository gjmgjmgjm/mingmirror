"""FastAPI REST 服务入口。

HTTP 层薄封装：
- 接收 URL，创建 job，返回 job_id
- 实际下载委托给 cli.main.download_url 的简化复用
- 新增八字分析相关端点（可选功能，需 DeepSeek API Key / rapidocr）

fastapi/uvicorn 是**可选**依赖。若未安装，导入本模块会 ImportError。
"""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import CookieManager
from config import ConfigLoader
from control import QueueManager, RateLimiter, RetryHandler
from core import DouyinAPIClient, DownloaderFactory, URLParser
from server.jobs import JobManager, JobStatus
from storage import FileManager
from utils.logger import setup_logger
from utils.validators import is_short_url, normalize_short_url

# Whitelisted proxy schemes for the REST proxy test endpoint.
_PROXY_ALLOWED_SCHEMES = {"http", "https", "socks5", "socks5h"}
_PROXY_RE = re.compile(r"^(https?|socks5h?)://(.+)$")


def _is_valid_proxy(proxy: str) -> bool:
    """Validate a proxy string for the test-proxy endpoint.

    Empty string means "no proxy" and is accepted. Non-empty strings must use
    a whitelisted scheme and provide a non-blank host portion.
    """
    if proxy == "":
        return True
    match = _PROXY_RE.match(proxy)
    if not match:
        return False
    host = match.group(2).strip()
    return host != ""

logger = setup_logger("REST")


class DownloadRequest(BaseModel):
    url: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    url: str


class BaziAnalyzeRequest(BaseModel):
    bazi: str
    question: str = ""
    top_k: int = 3


class BaziAnalyzeResponse(BaseModel):
    bazi: str
    result: Dict[str, Any]


class BaziExtractRequest(BaseModel):
    user_dir: str
    duration: int = 60
    interval: float = 2.0


class BaziExtractResponse(BaseModel):
    user_dir: str
    total: int
    success: int
    failed: int
    skipped: int
    manifest_path: str


class BaziFeedbackRequest(BaseModel):
    bazi: str
    correct: bool
    note: str = ""


class ConfigOverrideRequest(BaseModel):
    thread: Optional[int] = None
    rate_limit: Optional[float] = None
    retry_times: Optional[int] = None
    proxy: Optional[str] = None


class _ServerDeps:
    """跨请求复用的重量级依赖。

    REST 服务在进程生命周期内只需要一份 FileManager / RateLimiter / RetryHandler /
    QueueManager / CookieManager；每个请求重新构造既浪费又会触发文件系统 mkdir。
    DouyinAPIClient 由于持有 aiohttp.ClientSession，依旧按请求创建，避免跨请求泄漏
    连接状态或触发 "Session is closed" 错误。
    """

    def __init__(self, config: ConfigLoader):
        self.config = config
        # Resolve the cookie file path relative to the config file's directory
        # so the sidecar can find it regardless of its working directory (which
        # on macOS is often '/' when launched by Electron).
        if config.config_path:
            from pathlib import Path

            cookie_file = str(Path(config.config_path).resolve().parent / ".cookies.json")
        else:
            cookie_file = ".cookies.json"
        self.cookie_manager = CookieManager(cookie_file=cookie_file)
        # Load cookies from the config (env var / YAML cookie key) first, then
        # fall back to whatever is already on disk in the cookie file. This
        # ensures that cookies saved by a previous session are picked up on
        # restart even when the config doesn't embed them inline.
        initial_cookies = config.get_cookies()
        if initial_cookies:
            self.cookie_manager.set_cookies(initial_cookies)
        else:
            # Trigger a load from disk so get_cookies() returns the persisted
            # session without requiring a fresh login on every app restart.
            self.cookie_manager.get_cookies()
        self.file_manager = FileManager(config.get("path"))
        self.rate_limiter = RateLimiter(max_per_second=float(config.get("rate_limit", 2) or 2))
        self.retry_handler = RetryHandler(max_retries=int(config.get("retry_times", 3) or 3))
        self.queue_manager = QueueManager(max_workers=int(config.get("thread", 5) or 5))
        self._overrides: Dict[str, Any] = {}

    def apply_overrides(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Apply runtime config overrides and return the effective values.

        Only a small set of keys can be overridden at runtime because the
        heavyweight control objects need to be rebuilt.
        """
        allowed = {"thread", "rate_limit", "retry_times", "proxy"}
        changed = {k: v for k, v in overrides.items() if k in allowed and v is not None}
        self._overrides.update(changed)

        if "rate_limit" in changed:
            self.rate_limiter = RateLimiter(
                max_per_second=float(self._overrides.get("rate_limit", 2) or 2)
            )
        if "retry_times" in changed:
            self.retry_handler = RetryHandler(
                max_retries=int(self._overrides.get("retry_times", 3) or 3)
            )
        if "thread" in changed:
            self.queue_manager = QueueManager(
                max_workers=int(self._overrides.get("thread", 5) or 5)
            )
        # Proxy is stored on the config dict and used by api_client creation.
        if "proxy" in changed:
            self.config.config["proxy"] = changed["proxy"]

        return self.get_effective_config()

    def get_effective_config(self) -> Dict[str, Any]:
        """Return config merged with runtime overrides."""
        effective = dict(self.config.config)
        effective.update(self._overrides)
        return effective


async def _execute_download(url: str, deps: "_ServerDeps") -> Dict[str, int]:
    """简化版 download_url：只负责执行并返回成功/失败计数。

    有意不复用 cli.main.download_url —— 后者绑定了 progress_display 的 rich 状态。
    API client 仍按请求创建（aiohttp session 不跨请求复用）；其余重量级依赖从
    _ServerDeps 共享。
    """
    async with DouyinAPIClient(deps.cookie_manager.get_cookies()) as api_client:
        if is_short_url(url):
            resolved = await api_client.resolve_short_url(normalize_short_url(url))
            if not resolved:
                raise RuntimeError(f"Failed to resolve short URL: {url}")
            url = resolved

        parsed = URLParser.parse(url)
        if not parsed:
            raise RuntimeError(f"Unsupported URL: {url}")

        downloader = DownloaderFactory.create(
            parsed["type"],
            deps.config,
            api_client,
            deps.file_manager,
            deps.cookie_manager,
            None,  # database 不在 server 场景里启用，避免单例冲突
            deps.rate_limiter,
            deps.retry_handler,
            deps.queue_manager,
            progress_reporter=None,
        )
        if downloader is None:
            raise RuntimeError(f"No downloader for url_type={parsed['type']}")

        result = await downloader.download(parsed)
        return {
            "total": result.total,
            "success": result.success,
            "failed": result.failed,
            "skipped": result.skipped,
        }


def build_app(config: ConfigLoader) -> FastAPI:
    deps = _ServerDeps(config)

    async def executor(url: str) -> Dict[str, int]:
        return await _execute_download(url, deps)

    server_cfg = config.get("server") or {}
    if not isinstance(server_cfg, dict):
        server_cfg = {}
    manager = JobManager(
        executor=executor,
        max_concurrency=int(config.get("thread", 2) or 2),
        max_jobs=int(server_cfg.get("max_jobs") or JobManager.DEFAULT_MAX_JOBS),
        job_ttl_seconds=float(
            server_cfg.get("job_ttl_seconds") or JobManager.DEFAULT_JOB_TTL_SECONDS
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await manager.shutdown()

    app = FastAPI(
        title="Douyin Downloader API",
        version="1.0",
        description="REST API for dispatching Douyin download jobs.",
        lifespan=lifespan,
    )
    app.state.job_manager = manager
    app.state.deps = deps

    @app.get("/api/v1/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/download", response_model=JobResponse)
    async def create_job(req: DownloadRequest) -> JobResponse:
        if not req.url:
            raise HTTPException(status_code=400, detail="url is required")
        job = await manager.submit(req.url)
        return JobResponse(job_id=job.job_id, status=job.status, url=job.url)

    @app.get("/api/v1/jobs/{job_id}")
    async def get_job(job_id: str) -> Dict[str, Any]:
        job = await manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job.to_dict()

    @app.get("/api/v1/jobs")
    async def list_jobs() -> Dict[str, List[Dict[str, Any]]]:
        jobs = await manager.list_jobs()
        return {"jobs": [j.to_dict() for j in jobs]}

    @app.delete("/api/v1/jobs/{job_id}")
    async def cancel_job(job_id: str) -> Dict[str, Any]:
        """Cancel a pending or running job."""
        job = await manager.cancel(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job.to_dict()

    @app.get("/api/v1/jobs/{job_id}/events")
    async def job_events(job_id: str, request: Request):
        """SSE stream of job status changes."""

        async def event_stream():
            last_status = None
            while True:
                if await request.is_disconnected():
                    break
                job = await manager.get(job_id)
                if job is None:
                    yield f"event: error\ndata: {json.dumps({'detail': 'job not found'}, ensure_ascii=False)}\n\n"
                    break
                current = job.to_dict()
                if current["status"] != last_status:
                    last_status = current["status"]
                    yield f"event: status\ndata: {json.dumps(current, ensure_ascii=False)}\n\n"
                if current["status"] in JobStatus.TERMINAL:
                    break
                await asyncio.sleep(0.5)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @app.get("/api/v1/config")
    async def get_config() -> Dict[str, Any]:
        """Get the current effective configuration (including runtime overrides)."""
        return deps.get_effective_config()

    @app.post("/api/v1/config")
    async def update_config(req: ConfigOverrideRequest) -> Dict[str, Any]:
        """Apply runtime config overrides."""
        overrides = req.model_dump(exclude_unset=True)
        return deps.apply_overrides(overrides)

    # ── 八字相关端点 ──

    @app.post("/api/v1/bazi/analyze", response_model=BaziAnalyzeResponse)
    async def analyze_bazi_endpoint(req: BaziAnalyzeRequest) -> BaziAnalyzeResponse:
        """Analyze a single bazi string with DeepSeek + RAG."""
        from tools.bazi_ai.engine import analyze_bazi

        ai_cfg = config.get("bazi_ai") or {}
        cases_path = Path(ai_cfg.get("cases", "./bazi_knowledge/cases.jsonl"))
        knowledge_path = Path(ai_cfg.get("knowledge_base", "./bazi_knowledge/rule_primer.md"))
        embedding_cache = ai_cfg.get("embedding_cache")
        embedding_cache_path = Path(embedding_cache) if embedding_cache else None

        result = await analyze_bazi(
            req.bazi.strip(),
            question=req.question,
            cases_path=cases_path,
            knowledge_base_path=knowledge_path,
            embedding_cache_path=embedding_cache_path,
            top_k=min(max(req.top_k, 1), 10),
        )
        return BaziAnalyzeResponse(bazi=req.bazi, result=result)

    @app.get("/api/v1/bazi/cases")
    async def list_bazi_cases() -> Dict[str, List[Dict[str, Any]]]:
        """List structured bazi cases used for RAG retrieval."""
        ai_cfg = config.get("bazi_ai") or {}
        cases_path = Path(ai_cfg.get("cases", "./bazi_knowledge/cases.jsonl"))
        cases = []
        if cases_path.exists():
            async with aiofiles.open(cases_path, "r", encoding="utf-8") as f:
                async for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cases.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return {"cases": cases}

    @app.post("/api/v1/bazi/extract", response_model=BaziExtractResponse)
    async def extract_bazi_endpoint(req: BaziExtractRequest) -> BaziExtractResponse:
        """Run OCR-based bazi extraction over downloaded videos in a user dir."""
        from fastapi.concurrency import run_in_threadpool

        from tools.bazi_cli import extract_bazi_for_directory

        user_dir = Path(req.user_dir)
        if not user_dir.exists():
            raise HTTPException(status_code=404, detail=f"user_dir not found: {req.user_dir}")

        summary = await run_in_threadpool(
            extract_bazi_for_directory,
            user_dir,
            user_dir,  # base_dir for relative manifest keys
            duration=req.duration,
            interval=req.interval,
            resume=True,
        )
        return BaziExtractResponse(
            user_dir=str(user_dir),
            total=summary["total"],
            success=summary["success"],
            failed=summary["failed"],
            skipped=summary["skipped"],
            manifest_path=str(summary["manifest_path"]),
        )

    @app.post("/api/v1/bazi/feedback")
    async def bazi_feedback(req: BaziFeedbackRequest) -> Dict[str, str]:
        """Record simple feedback for a bazi analysis (placeholder persistence)."""
        ai_cfg = config.get("bazi_ai") or {}
        feedback_path = Path(ai_cfg.get("feedback_path", "./bazi_knowledge/feedback.jsonl"))
        feedback_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(feedback_path, "a", encoding="utf-8") as f:
            await f.write(
                json.dumps(
                    {
                        "bazi": req.bazi,
                        "correct": req.correct,
                        "note": req.note,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return {"status": "ok"}

    return app


async def run_server(config: ConfigLoader, *, host: str, port: int) -> None:
    import uvicorn

    app = build_app(config)
    uv_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(uv_config)
    await server.serve()
