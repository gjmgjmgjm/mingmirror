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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from auth import CookieManager
from config import ConfigLoader
from control import QueueManager, RateLimiter, RetryHandler
from core import DouyinAPIClient, DownloaderFactory, URLParser
from server.jobs import JobManager, JobStatus
from storage import FileManager
from tools.qizheng.star_tables import resolve_dignity_table
from utils.logger import setup_logger
from utils.validators import is_short_url, normalize_short_url


class _SPAStaticFiles(StaticFiles):
    """StaticFiles subclass that falls back to index.html for SPA routing."""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise
        if response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


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
    gender: str = "male"
    birth_date: str = ""
    birth_time: str = "00:00"
    calendar_type: str = "solar"
    top_k: int = 3


class BaziAnalyzeResponse(BaseModel):
    bazi: str
    result: Dict[str, Any]


class BaziTimelineRequest(BaseModel):
    bazi: str
    gender: str = ""
    birth_date: str = ""
    birth_time: str = "00:00"
    calendar_type: str = "solar"
    until_age: int = 80


class BaziTimelineResponse(BaseModel):
    bazi: str
    dayun: List[Dict[str, Any]]
    liunian: List[Dict[str, Any]]


class BaziYearlyRequest(BaseModel):
    bazi: str
    gender: str = ""
    birth_date: str = ""
    birth_time: str = "00:00"
    calendar_type: str = "solar"
    mode: str = "10y"
    start_year: Optional[int] = None
    years: Optional[int] = None


class BaziYearlyResponse(BaseModel):
    bazi: str
    mode: str
    result: Dict[str, Any]


class BaziFromDatetimeRequest(BaseModel):
    birth_datetime: str
    calendar_type: str = "solar"


class BaziFromDatetimeResponse(BaseModel):
    bazi: str
    pillars: Dict[str, str]
    calendar_type: str


class BaziReportRequest(BaseModel):
    bazi: str
    gender: str = "male"
    birth_date: str = ""
    birth_time: str = "00:00"
    calendar_type: str = "solar"
    top_k: int = 3


class BaziReportResponse(BaseModel):
    bazi: str
    report: Dict[str, Any]


class BaziAuspiciousRequest(BaseModel):
    bazi: str
    gender: str = "male"
    event_type: str = "marriage"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    top_n: int = 10
    hour_top_k: int = 3
    # 为 True 时在响应中附带 ics 文本(推荐日批量日历)
    include_ics: bool = False


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


class QizhengAnalyzeRequest(BaseModel):
    bazi: Optional[str] = None
    question: str = ""
    birth_datetime: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone_offset: Optional[float] = None
    precession_mode: str = "tropical"
    dignity_table: str = "default"


class QizhengAnalyzeResponse(BaseModel):
    bazi: str
    result: Dict[str, Any]


class ZiweiAnalyzeRequest(BaseModel):
    bazi: Optional[str] = None
    question: str = ""
    gender: str = "male"
    birth_datetime: Optional[str] = None
    birth_date: Optional[str] = None
    location: Optional[Dict[str, Any]] = None


class ZiweiAnalyzeResponse(BaseModel):
    bazi: str
    result: Dict[str, Any]


class ZiweiYearlyRequest(BaseModel):
    bazi: str
    gender: str = "male"
    birth_date: str = ""
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    years: int = 10


class ZiweiYearlyResponse(BaseModel):
    bazi: str
    result: Dict[str, Any]


class QizhengYearlyRequest(BaseModel):
    bazi: Optional[str] = None
    gender: str = ""
    birth_year: int = 0
    mode: str = "10y"
    birth_datetime: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone_offset: Optional[float] = None
    precession_mode: str = "tropical"
    dignity_table: str = "default"


class QizhengYearlyResponse(BaseModel):
    bazi: str
    mode: str
    result: Dict[str, Any]


def _resolve_qizheng_input(
    bazi: Optional[str],
    birth_datetime: Optional[str],
    latitude: Optional[float],
    longitude: Optional[float],
    timezone_offset: Optional[float],
    precession_mode: str,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Resolve the chart input for qizheng endpoints.

    Returns a tuple of (chart_info dict for the analyzer, bazi string).
    If neither bazi nor datetime+location are provided, returns (None, "").
    """
    from datetime import datetime as _dt

    from tools.qizheng.calendar import astro_structural_profile

    # Prefer birth_datetime + location when available.
    if birth_datetime and latitude is not None and longitude is not None:
        raw = birth_datetime.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = _dt.fromisoformat(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid datetime: {exc}") from exc
        profile = astro_structural_profile(
            birth_datetime=dt,
            latitude=latitude,
            longitude=longitude,
            timezone_offset_hours=timezone_offset,
            precession_mode=precession_mode,
        )
        if profile is None:
            raise HTTPException(status_code=500, detail="Failed to compute qizheng profile")
        return (
            {
                "birth_datetime": dt.isoformat(),
                "latitude": latitude,
                "longitude": longitude,
                "timezone_offset": timezone_offset,
                "precession_mode": precession_mode,
                "chart": profile.get("chart", ""),
                "bazi": profile.get("chart", ""),
            },
            profile.get("chart", ""),
        )

    if bazi:
        chart = bazi.strip()
        return ({"bazi": chart, "chart": chart, "precession_mode": precession_mode}, chart)

    return None, ""


class DestinyAnalyzeRequest(BaseModel):
    bazi: str
    question: str = ""
    systems: List[str] = ["bazi"]
    strategy: str = "single"
    gender: Optional[str] = None
    birth_datetime: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    # If true (default), load latest calibration adjusted_weights for this chart.
    use_calibration_weights: bool = True
    # Explicit override; wins over stored calibration when provided.
    system_weights: Optional[Dict[str, float]] = None


class DestinyAnalyzeResponse(BaseModel):
    bazi: str
    question: str
    per_system: List[Dict[str, Any]]
    aligned: Dict[str, Any]
    final_summary: str
    overall_confidence: str
    strategy: Optional[str] = None
    system_weights: Optional[Dict[str, float]] = None
    weights_source: Optional[str] = None


class DestinyCouncilRequest(BaseModel):
    bazi: str
    question: str = ""
    systems: List[str] = ["bazi", "qizheng"]
    strategy: str = "debate"
    gender: Optional[str] = None
    birth_datetime: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    use_calibration_weights: bool = True
    system_weights: Optional[Dict[str, float]] = None


class DestinyDailyRequest(BaseModel):
    bazi: str
    date: Optional[str] = None  # ISO format; defaults to today


class DestinyScriptRequest(BaseModel):
    bazi: str
    gender: Optional[str] = None
    birth_datetime: Optional[str] = None
    birth_year: int = 1990


class DestinyScriptResponse(BaseModel):
    character_card: Dict[str, Any]
    chapters: List[Dict[str, Any]]
    opening: str
    closing: str


class EventCreateRequest(BaseModel):
    event_type: str
    happened_at: str  # ISO date or datetime
    description: str = ""


class EventResponse(BaseModel):
    id: str
    chart_id: str
    event_type: str
    happened_at: str
    description: str = ""


class CalibrationResponse(BaseModel):
    chart_id: str
    event_count: int
    average_score: float
    system_scores: Dict[str, float]
    adjusted_weights: Dict[str, float]
    suggested_hour_offset: Optional[int] = None
    events: List[Dict[str, Any]]
    calibration_id: Optional[str] = None
    created_at: Optional[int] = None


class CompatibilityRequest(BaseModel):
    bazi_a: str
    gender_a: str = "male"
    bazi_b: str
    gender_b: str = "female"
    # Off by default so simple score calls stay cheap; frontend opts in.
    include_joint_days: bool = False
    include_ics: bool = False
    event_type: str = "marriage"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    top_n: int = 8


class ChartCreateRequest(BaseModel):
    bazi: str
    gender: str = "male"
    birth_date: str = ""
    birth_time: str = ""
    calendar_type: str = "solar"
    location: Optional[Dict[str, Any]] = None
    label: str = ""
    # If true, reuse most recent chart with same bazi when present.
    reuse_existing: bool = True


class PackageExportOptions(BaseModel):
    """流年附录区间（与紫微/七政前端控件一致）。"""

    liunian_start_year: Optional[int] = None
    liunian_years: int = 10


class BaziPackageExportRequest(ChartCreateRequest):
    liunian_start_year: Optional[int] = None
    liunian_years: int = 10


class ChartResponse(BaseModel):
    id: str
    bazi: str
    gender: str
    birth_date: str = ""
    birth_time: str = ""
    calendar_type: str = "solar"
    location: Optional[Dict[str, Any]] = None
    label: str = ""
    created_at: int = 0
    updated_at: int = 0


class TrackEventRequest(BaseModel):
    event: str
    device_id: str = ""
    chart_id: str = ""
    props: Optional[Dict[str, Any]] = None


class EntitlementActivateRequest(BaseModel):
    device_id: str
    action: str = "pro"  # pro | credit
    code: str = ""  # demo activation code
    days: int = 30
    credits: int = 1


class EntitlementConsumeRequest(BaseModel):
    device_id: str


class PaymentWebhookRequest(BaseModel):
    """Generic payment provider payload (Stripe/Lemon/wechat-style).

    Map provider fields into these canonical keys in the adapter layer.
    """

    provider: str = "demo"
    external_id: str  # provider payment / order id (idempotent)
    device_id: str
    product: str = "package"  # pro | package | ...
    amount_cents: int = 0
    currency: str = "CNY"
    status: str = "succeeded"
    days: int = 30
    credits: int = 1
    raw: Optional[Dict[str, Any]] = None


class CheckoutRequest(BaseModel):
    """Demo / adapter checkout: creates ledger + grants entitlement.

    Real PSP: use webhook fulfillment; this endpoint is the closed-loop
    path for demo provider and local smoke tests.
    """

    device_id: str
    product: str = "pro"  # pro | package
    provider: str = "demo"
    days: int = 30
    credits: int = 1
    amount_cents: int = 0
    currency: str = "CNY"
    external_id: str = ""


class AdminGrantRequest(BaseModel):
    device_id: str
    action: str = "pro"  # pro | credit
    days: int = 30
    credits: int = 1


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
        knowledge_embedding_cache = ai_cfg.get("knowledge_embedding_cache")
        knowledge_embedding_cache_path = Path(knowledge_embedding_cache) if knowledge_embedding_cache else None

        def _to_paths(key: str) -> List[Path]:
            values = ai_cfg.get(key) or []
            if isinstance(values, str):
                values = [values]
            return [Path(v) for v in values if v]

        result = await analyze_bazi(
            req.bazi.strip(),
            question=req.question,
            gender=req.gender,
            birth_date=req.birth_date,
            birth_time=req.birth_time,
            calendar_type=req.calendar_type,
            cases_path=cases_path,
            knowledge_base_path=knowledge_path,
            extra_cases_paths=_to_paths("extra_cases_paths"),
            extra_knowledge_base_paths=_to_paths("extra_knowledge_base_paths"),
            embedding_cache_path=embedding_cache_path,
            knowledge_embedding_cache_path=knowledge_embedding_cache_path,
            top_k=min(max(req.top_k, 1), 10),
            api_key=ai_cfg.get("api_key") or None,
            base_url=ai_cfg.get("base_url") or None,
            model=ai_cfg.get("model") or None,
        )
        return BaziAnalyzeResponse(bazi=req.bazi, result=result)

    @app.post("/api/v1/bazi/report", response_model=BaziReportResponse)
    async def bazi_report(req: BaziReportRequest) -> BaziReportResponse:
        """生成结构化可解释报告(确定性结构层 + LLM 增强),一次返回 sections。"""
        from tools.bazi_ai.engine import analyze_bazi
        from tools.bazi_ai.report_template import build_report

        ai_cfg = config.get("bazi_ai") or {}
        cases_path = Path(ai_cfg.get("cases", "./bazi_knowledge/cases.jsonl"))
        knowledge_path = Path(ai_cfg.get("knowledge_base", "./bazi_knowledge/rule_primer.md"))
        embedding_cache = ai_cfg.get("embedding_cache")
        embedding_cache_path = Path(embedding_cache) if embedding_cache else None
        knowledge_embedding_cache = ai_cfg.get("knowledge_embedding_cache")
        knowledge_embedding_cache_path = Path(knowledge_embedding_cache) if knowledge_embedding_cache else None

        def _report_paths(key: str) -> List[Path]:
            values = ai_cfg.get(key) or []
            if isinstance(values, str):
                values = [values]
            return [Path(v) for v in values if v]

        result = await analyze_bazi(
            req.bazi.strip(),
            question="",
            gender=req.gender,
            birth_date=req.birth_date,
            birth_time=req.birth_time,
            calendar_type=req.calendar_type,
            cases_path=cases_path,
            knowledge_base_path=knowledge_path,
            extra_cases_paths=_report_paths("extra_cases_paths"),
            extra_knowledge_base_paths=_report_paths("extra_knowledge_base_paths"),
            embedding_cache_path=embedding_cache_path,
            knowledge_embedding_cache_path=knowledge_embedding_cache_path,
            top_k=min(max(req.top_k, 1), 10),
            api_key=ai_cfg.get("api_key") or None,
            base_url=ai_cfg.get("base_url") or None,
            model=ai_cfg.get("model") or None,
        )
        birth_info = {
            "birth_date": req.birth_date,
            "birth_time": req.birth_time,
            "calendar_type": req.calendar_type,
        }
        report = build_report(
            req.bazi.strip(), gender=req.gender, result=result, birth_info=birth_info
        )
        return BaziReportResponse(bazi=req.bazi, report=report)

    def _birth_year(birth_date: str) -> Optional[int]:
        try:
            return int(birth_date.split("-")[0])
        except (ValueError, AttributeError):
            return None

    @app.post("/api/v1/bazi/timeline", response_model=BaziTimelineResponse)
    async def bazi_timeline(req: BaziTimelineRequest) -> BaziTimelineResponse:
        """Return DaYun and Liunian pillars for a chart."""
        from tools.bazi_ai.calendar import dayun_list, liunian_list

        dayun = dayun_list(
            req.bazi.strip(),
            req.gender,
            req.birth_date,
            req.birth_time,
            req.calendar_type,
            until_age=req.until_age,
        )
        birth_year = _birth_year(req.birth_date)
        if birth_year:
            for d in dayun:
                start = birth_year + int(d["start_age"])
                end = birth_year + int(d["end_age"])
                d["start_year"] = start
                d["end_year"] = end

        current_year = datetime.now().year
        start_year = birth_year or current_year
        end_year = start_year + req.until_age - 1
        liunian = liunian_list(start_year, end_year)
        return BaziTimelineResponse(bazi=req.bazi, dayun=dayun, liunian=liunian)

    @app.post("/api/v1/bazi/yearly", response_model=BaziYearlyResponse)
    async def bazi_yearly(req: BaziYearlyRequest) -> BaziYearlyResponse:
        """Generate a detailed yearly luck analysis."""
        from tools.bazi_ai.engine import analyze_yearly

        ai_cfg = config.get("bazi_ai") or {}
        knowledge_path = Path(ai_cfg.get("knowledge_base", "./bazi_knowledge/rule_primer.md"))

        def _to_paths(key: str) -> List[Path]:
            values = ai_cfg.get(key) or []
            if isinstance(values, str):
                values = [values]
            return [Path(v) for v in values if v]

        embedding_cache = ai_cfg.get("embedding_cache")
        knowledge_embedding_cache = ai_cfg.get("knowledge_embedding_cache")
        result = await analyze_yearly(
            req.bazi.strip(),
            gender=req.gender,
            birth_date=req.birth_date,
            birth_time=req.birth_time,
            calendar_type=req.calendar_type,
            mode=req.mode,
            start_year=req.start_year,
            years=req.years,
            api_key=ai_cfg.get("api_key") or None,
            base_url=ai_cfg.get("base_url") or None,
            model=ai_cfg.get("model") or None,
            knowledge_base_path=knowledge_path,
            extra_knowledge_base_paths=_to_paths("extra_knowledge_base_paths"),
            cases_path=Path(ai_cfg.get("cases", "./bazi_knowledge/cases.jsonl")),
            extra_cases_paths=_to_paths("extra_cases_paths"),
            embedding_cache_path=Path(embedding_cache) if embedding_cache else None,
            knowledge_embedding_cache_path=Path(knowledge_embedding_cache) if knowledge_embedding_cache else None,
            top_k=int(ai_cfg.get("top_k", 3)),
        )
        return BaziYearlyResponse(bazi=req.bazi, mode=req.mode, result=result)

    @app.post("/api/v1/bazi/from_datetime", response_model=BaziFromDatetimeResponse)
    async def bazi_from_datetime(req: BaziFromDatetimeRequest) -> BaziFromDatetimeResponse:
        """Derive bazi from a solar or lunar birth datetime."""
        from datetime import datetime as _dt

        from tools.bazi_ai.calendar import (
            pillars_for_datetime,
            pillars_for_lunar_datetime,
        )

        raw = req.birth_datetime.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = _dt.fromisoformat(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid datetime: {exc}")

        calendar_type = req.calendar_type.strip().lower()
        if calendar_type not in ("solar", "lunar"):
            raise HTTPException(status_code=400, detail="calendar_type must be solar or lunar")

        try:
            if calendar_type == "lunar":
                pillars = pillars_for_lunar_datetime(
                    dt.year, dt.month, dt.day, dt.hour, dt.minute
                )
            else:
                pillars = pillars_for_datetime(dt)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Bazi calculation failed: {exc}")

        bazi = " ".join([pillars["year"], pillars["month"], pillars["day"], pillars["hour"]])
        return BaziFromDatetimeResponse(
            bazi=bazi, pillars=pillars, calendar_type=calendar_type
        )

    @app.post("/api/v1/qizheng/analyze", response_model=QizhengAnalyzeResponse)
    async def analyze_qizheng(req: QizhengAnalyzeRequest) -> QizhengAnalyzeResponse:
        """Analyze a Qi Zheng Si Yu chart.

        Accepts either a four-pillar ``bazi`` string or a real birth datetime
        plus geographic coordinates.  When datetime+location are supplied, the
        astronomical profile is computed from Swiss Ephemeris.
        """
        from tools.qizheng.engine import QiZhengAnalyzer

        chart_info, bazi = _resolve_qizheng_input(
            bazi=req.bazi,
            birth_datetime=req.birth_datetime,
            latitude=req.latitude,
            longitude=req.longitude,
            timezone_offset=req.timezone_offset,
            precession_mode=req.precession_mode,
        )
        if chart_info is None:
            raise HTTPException(
                status_code=400,
                detail="Must provide either bazi or birth_datetime + latitude + longitude",
            )

        ai_cfg = config.get("bazi_ai") or {}
        try:
            dignity_table = resolve_dignity_table(req.dignity_table)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        analyzer = QiZhengAnalyzer(
            api_key=ai_cfg.get("api_key") or None,
            base_url=ai_cfg.get("base_url") or None,
            model=ai_cfg.get("model") or None,
            rule_primer_path=Path("./tools/qizheng/rule_primer.md"),
            cases_path=Path("./tools/qizheng/cases.jsonl"),
            dignity_table=dignity_table,
        )
        result = await analyzer.analyze(chart_info, question=req.question)
        return QizhengAnalyzeResponse(bazi=bazi, result=result)

    @app.post("/api/v1/ziwei/analyze", response_model=ZiweiAnalyzeResponse)
    async def analyze_ziwei(req: ZiweiAnalyzeRequest) -> ZiweiAnalyzeResponse:
        """Analyze Zi Wei Dou Shu with structural chart (works offline)."""
        from tools.ziwei.engine import ZiWeiAnalyzer

        bazi = (req.bazi or "").strip()
        gender = req.gender if req.gender in ("male", "female") else "male"
        if gender in ("男",):
            gender = "male"
        if gender in ("女",):
            gender = "female"

        chart_info: Dict[str, Any] = {
            "bazi": bazi,
            "gender": gender,
        }
        if req.birth_datetime:
            chart_info["birth_datetime"] = req.birth_datetime
        if req.birth_date:
            chart_info["birth_date"] = req.birth_date
        if req.location:
            chart_info["location"] = req.location
        elif req.birth_datetime:
            # minimal location so strict LLM path still works if key set
            chart_info["location"] = {
                "longitude": 116.4074,
                "latitude": 39.9042,
                "timezone": "Asia/Shanghai",
            }

        if not bazi and not req.birth_datetime:
            raise HTTPException(status_code=400, detail="bazi or birth_datetime required")

        # If only datetime, still allow engine to run; bazi may be empty in response
        ai_cfg = config.get("bazi_ai") or {}
        analyzer = ZiWeiAnalyzer(
            api_key=ai_cfg.get("api_key") or None,
            base_url=ai_cfg.get("base_url") or None,
            model=ai_cfg.get("model") or None,
        )
        result = await analyzer.analyze(chart_info, question=req.question)
        out_bazi = bazi or str((result.get("basic_info") or {}).get("chart") or "")
        return ZiweiAnalyzeResponse(bazi=out_bazi, result=result)

    @app.post("/api/v1/ziwei/yearly", response_model=ZiweiYearlyResponse)
    async def ziwei_yearly(req: ZiweiYearlyRequest) -> ZiweiYearlyResponse:
        """紫微流年：太岁入宫 + 流年四化 + 所在大限（确定性结构层）。"""
        from tools.ziwei.chart import yearly_bundle

        gender = req.gender if req.gender in ("male", "female") else "male"
        if req.gender in ("女", "女命"):
            gender = "female"
        result = yearly_bundle(
            req.bazi.strip(),
            gender=gender,
            birth_date=req.birth_date or "",
            start_year=req.start_year,
            end_year=req.end_year,
            years=req.years,
        )
        if result.get("error") and not result.get("chart"):
            raise HTTPException(status_code=400, detail=result["error"])
        return ZiweiYearlyResponse(bazi=req.bazi.strip(), result=result)

    @app.post("/api/v1/qizheng/yearly", response_model=QizhengYearlyResponse)
    async def qizheng_yearly(req: QizhengYearlyRequest) -> QizhengYearlyResponse:
        """Generate a detailed yearly luck analysis with Qi Zheng Si Yu."""
        from datetime import datetime as _dt

        from tools.qizheng.engine import analyze_yearly

        chart_info, bazi = _resolve_qizheng_input(
            bazi=req.bazi,
            birth_datetime=req.birth_datetime,
            latitude=req.latitude,
            longitude=req.longitude,
            timezone_offset=req.timezone_offset,
            precession_mode=req.precession_mode,
        )
        if chart_info is None:
            raise HTTPException(
                status_code=400,
                detail="Must provide either bazi or birth_datetime + latitude + longitude",
            )

        ai_cfg = config.get("bazi_ai") or {}
        birth_year = req.birth_year or None
        if birth_year == 0:
            birth_year = None
        # If a datetime was supplied but no explicit birth_year, derive it.
        if birth_year is None and req.birth_datetime:
            try:
                raw = req.birth_datetime.strip()
                if raw.endswith("Z"):
                    raw = raw[:-1] + "+00:00"
                birth_year = _dt.fromisoformat(raw).year
            except ValueError:
                pass
        try:
            dignity_table = resolve_dignity_table(req.dignity_table)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await analyze_yearly(
            bazi,
            gender=req.gender,
            birth_year=birth_year,
            mode=req.mode,
            api_key=ai_cfg.get("api_key") or None,
            base_url=ai_cfg.get("base_url") or None,
            model=ai_cfg.get("model") or None,
            rule_primer_path=Path("./tools/qizheng/rule_primer.md"),
            dignity_table=dignity_table,
        )
        return QizhengYearlyResponse(bazi=bazi, mode=req.mode, result=result)

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

    # ── 多学派命理端点 ──

    def _build_bazi_caller() -> Optional[Any]:
        """Build a bazi caller that respects the configured bazi_ai paths."""
        try:
            from tools.bazi_ai.engine import analyze_bazi
        except Exception:  # pragma: no cover - optional subsystem
            return None

        ai_cfg = config.get("bazi_ai") or {}
        cases_path = Path(ai_cfg.get("cases", "./bazi_knowledge/cases.jsonl"))
        knowledge_path = Path(ai_cfg.get("knowledge_base", "./bazi_knowledge/rule_primer.md"))
        embedding_cache = ai_cfg.get("embedding_cache")
        embedding_cache_path = Path(embedding_cache) if embedding_cache else None

        def _to_paths(key: str) -> List[Path]:
            values = ai_cfg.get(key) or []
            if isinstance(values, str):
                values = [values]
            return [Path(v) for v in values if v]

        async def _caller(chart_info: Any, question: str) -> Dict[str, Any]:
            return await analyze_bazi(
                chart_info.bazi,
                question=question,
                gender=chart_info.gender or "male",
                birth_date=getattr(chart_info, "birth_datetime", "") or "",
                cases_path=cases_path,
                knowledge_base_path=knowledge_path,
                extra_cases_paths=_to_paths("extra_cases_paths"),
                extra_knowledge_base_paths=_to_paths("extra_knowledge_base_paths"),
                embedding_cache_path=embedding_cache_path,
                top_k=ai_cfg.get("top_k", 3),
            )

        return _caller

    def _build_qizheng_caller() -> Optional[Any]:
        """Build a Qi Zheng Si Yu caller using the configured AI backend."""
        try:
            from tools.qizheng.engine import QiZhengAnalyzer
        except Exception:  # pragma: no cover - optional subsystem
            return None

        ai_cfg = config.get("bazi_ai") or {}
        package_dir = Path(__file__).resolve().parent.parent / "tools" / "qizheng"
        analyzer = QiZhengAnalyzer(
            api_key=ai_cfg.get("api_key") or None,
            base_url=ai_cfg.get("base_url") or None,
            model=ai_cfg.get("model") or None,
            rule_primer_path=package_dir / "rule_primer.md",
            cases_path=package_dir / "cases.jsonl",
        )

        async def _caller(chart_info: Any, question: str) -> Dict[str, Any]:
            return await analyzer.analyze({"bazi": chart_info.bazi}, question=question)

        return _caller

    def _resolve_system_weights(req: Any, chart_bazi: str) -> Dict[str, float]:
        """Prefer explicit request weights, else latest calibration for chart."""
        explicit = getattr(req, "system_weights", None) or None
        if isinstance(explicit, dict) and explicit:
            return {str(k): float(v) for k, v in explicit.items()}
        if not getattr(req, "use_calibration_weights", True):
            return {}
        store = getattr(app.state, "event_store", None)
        latest_fn = getattr(store, "latest_calibration", None) if store else None
        if not callable(latest_fn):
            return {}
        try:
            latest = latest_fn(chart_bazi.strip())
        except Exception:  # pragma: no cover
            return {}
        if not latest:
            return {}
        weights = latest.get("adjusted_weights") or {}
        if not isinstance(weights, dict):
            return {}
        return {str(k): float(v) for k, v in weights.items() if v is not None}

    def _destiny_analyze(req: Any, default_strategy: str):
        """Run multi-destiny analysis and return (analyzer, chart)."""
        try:
            from tools.destiny.contract import ChartInfo
            from tools.destiny.ensemble import MultiDestinyAnalyzer
        except Exception as exc:  # pragma: no cover - optional subsystem
            raise HTTPException(
                status_code=503,
                detail=f"destiny subsystem not available: {exc}",
            ) from exc

        strategy = req.strategy if req.strategy in (
            "single", "reflection", "debate", "tool_augmented"
        ) else default_strategy

        callables: Dict[str, Any] = {}
        bazi_caller = _build_bazi_caller()
        if bazi_caller is not None:
            callables["bazi"] = bazi_caller
        qizheng_caller = _build_qizheng_caller()
        if qizheng_caller is not None:
            callables["qizheng"] = qizheng_caller

        weights = _resolve_system_weights(req, req.bazi)
        analyzer = MultiDestinyAnalyzer(
            systems=req.systems,
            callables=callables,
            config=config.get("bazi_ai") or {},
            strategy=strategy,
            system_weights=weights or None,
        )
        return analyzer, ChartInfo(
            bazi=req.bazi.strip(),
            question=req.question,
            gender=req.gender,
            birth_datetime=req.birth_datetime,
            location=req.location,
        )

    def _build_calibration_analyzer() -> Any:
        """Build an analyzer callable for the event calibrator."""
        try:
            from tools.destiny.contract import ChartInfo
            from tools.destiny.ensemble import MultiDestinyAnalyzer
        except Exception as exc:  # pragma: no cover - optional subsystem
            raise HTTPException(
                status_code=503,
                detail=f"destiny subsystem not available: {exc}",
            ) from exc

        callables: Dict[str, Any] = {}
        bazi_caller = _build_bazi_caller()
        if bazi_caller is not None:
            callables["bazi"] = bazi_caller
        qizheng_caller = _build_qizheng_caller()
        if qizheng_caller is not None:
            callables["qizheng"] = qizheng_caller

        async def _analyzer(chart_info: Any, question: str) -> Dict[str, Any]:
            analyzer = MultiDestinyAnalyzer(
                systems=["bazi", "qizheng"],
                callables=callables,
                config=config.get("bazi_ai") or {},
                strategy="single",
            )
            if isinstance(chart_info, dict):
                chart_info = ChartInfo(**chart_info)
            return await analyzer.analyze(chart_info, question=question)

        return _analyzer

    # Event calibration + chart identity + product plane: same SQLite file.
    _chart_store = None
    _product_store = None
    try:
        from tools.destiny.calibrator import DestinyCalibrator, SqliteEventStore
        from tools.destiny.chart_store import ChartStore
        from tools.destiny.product_store import ProductStore

        _download_path = Path(config.get("path", "./Downloaded"))
        _download_path.mkdir(parents=True, exist_ok=True)
        _event_db = Path(
            config.get("event_store_db", _download_path / "mingmirror_events.db")
        )
        _event_jsonl = Path(
            config.get("event_store_path", _download_path / "events.jsonl")
        )
        _event_store = SqliteEventStore(
            _event_db,
            migrate_from_jsonl=_event_jsonl if _event_jsonl.exists() else None,
        )
        _chart_store = ChartStore(_event_db)
        _product_store = ProductStore(_event_db)
        _calibrator = DestinyCalibrator(
            analyzer=_build_calibration_analyzer(),
            event_store=_event_store,
        )
        app.state.calibrator = _calibrator
        app.state.event_store = _event_store
        app.state.chart_store = _chart_store
        app.state.product_store = _product_store
    except Exception as exc:  # pragma: no cover - optional subsystem
        _event_store = None
        _calibrator = None
        _chart_store = None
        _product_store = None
        app.state.calibrator = None
        app.state.event_store = None
        app.state.chart_store = None
        app.state.product_store = None
        logger.debug("Event calibration / chart store not available: %s", exc)

    import os as _os

    _demo_code = str(
        config.get("mingmirror_demo_code")
        or _os.environ.get("MINGMIRROR_DEMO_CODE", "demo-pro")
    )
    _admin_token = str(
        config.get("mingmirror_admin_token")
        or _os.environ.get("MINGMIRROR_ADMIN_TOKEN", "")
    ).strip()
    _webhook_secret = str(
        config.get("mingmirror_webhook_secret")
        or _os.environ.get("MINGMIRROR_WEBHOOK_SECRET", "")
    ).strip()

    def _require_admin(request: Request) -> None:
        """Protect admin read APIs. If token unset, allow in dev (open)."""
        if not _admin_token:
            return
        header = (request.headers.get("X-Admin-Token") or "").strip()
        query_token = (request.query_params.get("admin_token") or "").strip()
        if header != _admin_token and query_token != _admin_token:
            raise HTTPException(status_code=401, detail="admin token required")

    def _require_webhook(request: Request) -> None:
        """Protect payment webhook. If secret unset, allow demo mode."""
        if not _webhook_secret:
            return
        header = (
            request.headers.get("X-Webhook-Secret")
            or request.headers.get("X-Mingmirror-Secret")
            or ""
        ).strip()
        if header != _webhook_secret:
            raise HTTPException(status_code=401, detail="invalid webhook secret")

    def _resolve_chart_scope(chart_id: str) -> tuple:
        """Return (event_store_key, bazi_for_analysis) for UUID or legacy bazi."""
        key = (chart_id or "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="chart_id is required")
        if _chart_store is not None:
            from tools.destiny.chart_store import is_chart_uuid

            if is_chart_uuid(key):
                rec = _chart_store.get(key)
                if rec is None:
                    raise HTTPException(status_code=404, detail="chart not found")
                return key, rec.bazi
        return key, key

    @app.post("/api/v1/destiny/analyze", response_model=DestinyAnalyzeResponse)
    async def destiny_analyze(req: DestinyAnalyzeRequest) -> DestinyAnalyzeResponse:
        """Analyze a chart using one or more destiny systems."""
        analyzer, chart = _destiny_analyze(req, default_strategy="single")
        result = await analyzer.analyze(chart)
        return DestinyAnalyzeResponse(
            bazi=result.get("bazi", chart.bazi),
            question=result.get("question", chart.question),
            per_system=result.get("per_system", []),
            aligned=result.get("aligned", {}),
            final_summary=result.get("final_summary", ""),
            overall_confidence=result.get("overall_confidence", "low"),
            strategy=result.get("strategy"),
            system_weights=result.get("system_weights"),
            weights_source=result.get("weights_source"),
        )

    @app.post("/api/v1/destiny/council", response_model=DestinyAnalyzeResponse)
    async def destiny_council(req: DestinyCouncilRequest) -> DestinyAnalyzeResponse:
        """Run a multi-agent destiny council (debate/reflection) for a chart."""
        analyzer, chart = _destiny_analyze(req, default_strategy="debate")
        result = await analyzer.analyze(chart)
        return DestinyAnalyzeResponse(
            bazi=result.get("bazi", chart.bazi),
            question=result.get("question", chart.question),
            per_system=result.get("per_system", []),
            aligned=result.get("aligned", {}),
            final_summary=result.get("final_summary", ""),
            overall_confidence=result.get("overall_confidence", "low"),
            strategy=result.get("strategy"),
            system_weights=result.get("system_weights"),
            weights_source=result.get("weights_source"),
        )

    @app.post("/api/v1/destiny/daily")
    async def destiny_daily(req: DestinyDailyRequest) -> Dict[str, Any]:
        """Return a simplified daily fortune reading for a bazi chart."""
        try:
            from tools.bazi_ai.calendar import daily_fortune
        except Exception as exc:  # pragma: no cover - optional subsystem
            raise HTTPException(
                status_code=503,
                detail=f"calendar subsystem not available: {exc}",
            ) from exc

        target_date = None
        if req.date:
            from datetime import date as _date

            try:
                target_date = _date.fromisoformat(req.date)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"invalid date format: {exc}",
                ) from exc

        return daily_fortune(req.bazi.strip(), target_date)

    @app.get("/api/v1/bazi/auspicious/event-types")
    async def bazi_auspicious_event_types() -> Dict[str, Any]:
        """列出择日引擎支持的事项类型。"""
        try:
            from tools.bazi_ai.auspicious import event_types
        except Exception as exc:  # pragma: no cover - optional subsystem
            raise HTTPException(
                status_code=503,
                detail=f"auspicious subsystem not available: {exc}",
            ) from exc
        return {"event_types": event_types()}

    @app.post("/api/v1/bazi/auspicious")
    async def bazi_auspicious(req: BaziAuspiciousRequest) -> Dict[str, Any]:
        """目标导向个性化吉日推荐(命主用神忌神 + 冲合 + 目标权重 + 吉时)。"""
        try:
            from tools.bazi_ai.auspicious import auspicious_days, to_ics
        except Exception as exc:  # pragma: no cover - optional subsystem
            raise HTTPException(
                status_code=503,
                detail=f"auspicious subsystem not available: {exc}",
            ) from exc

        from datetime import date as _date

        date_from = None
        date_to = None
        try:
            if req.date_from:
                date_from = _date.fromisoformat(req.date_from)
            if req.date_to:
                date_to = _date.fromisoformat(req.date_to)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid date format: {exc}",
            ) from exc

        result = auspicious_days(
            req.bazi.strip(),
            req.gender,
            req.event_type,
            date_from,
            date_to,
            req.top_n,
            hour_top_k=req.hour_top_k,
        )
        if req.include_ics and not result.get("error"):
            result = dict(result)
            result["ics"] = to_ics(result, top_n=req.top_n)
        return result

    @app.post("/api/v1/destiny/script", response_model=DestinyScriptResponse)
    async def destiny_script(req: DestinyScriptRequest) -> DestinyScriptResponse:
        """Generate a Destiny Script (RPG character card + life chapters)."""
        try:
            from tools.destiny.contract import ChartInfo
            from tools.destiny.script_writer import ScriptWriter
        except Exception as exc:  # pragma: no cover - optional subsystem
            raise HTTPException(
                status_code=503,
                detail=f"destiny script subsystem not available: {exc}",
            ) from exc

        ai_cfg = config.get("bazi_ai") or {}
        writer = ScriptWriter(
            api_key=ai_cfg.get("api_key") or None,
            base_url=ai_cfg.get("base_url") or None,
            model=ai_cfg.get("model") or None,
        )
        chart = ChartInfo(
            bazi=req.bazi.strip(),
            gender=req.gender,
            birth_datetime=req.birth_datetime,
        )
        result = await writer.write(chart, birth_year=req.birth_year)
        return DestinyScriptResponse(
            character_card=result.get("character_card", {}),
            chapters=result.get("chapters", []),
            opening=result.get("opening", ""),
            closing=result.get("closing", ""),
        )

    @app.get("/api/v1/destiny/systems")
    async def list_destiny_systems() -> Dict[str, List[str]]:
        """List destiny systems that are currently available."""
        available = []
        if _build_bazi_caller() is not None:
            available.append("bazi")
        for module in ("tools.qizheng.engine", "tools.ziwei.engine"):
            try:
                __import__(module)
                available.append(module.split(".")[1])
            except Exception:  # pragma: no cover - optional subsystem
                pass
        return {
            "available": available,
            "all": ["bazi", "ziwei", "qizheng"],
        }

    # ------------------------------------------------------------------
    # Chart identity (product layer)
    # ------------------------------------------------------------------
    @app.post("/api/v1/charts", response_model=ChartResponse)
    async def create_chart(req: ChartCreateRequest) -> ChartResponse:
        """Create (or reuse) a persistent chart with UUID."""
        if _chart_store is None:
            raise HTTPException(status_code=503, detail="chart store not available")
        from tools.destiny.chart_store import ChartRecord

        bazi = req.bazi.strip()
        if not bazi:
            raise HTTPException(status_code=400, detail="bazi is required")
        if req.reuse_existing:
            existing = _chart_store.get_by_bazi(bazi)
            if existing is not None:
                # Refresh birth metadata if provided
                if req.birth_date or req.birth_time or req.location or req.label:
                    existing.gender = req.gender or existing.gender
                    existing.birth_date = req.birth_date or existing.birth_date
                    existing.birth_time = req.birth_time or existing.birth_time
                    existing.calendar_type = req.calendar_type or existing.calendar_type
                    if req.location is not None:
                        existing.location = req.location
                    if req.label:
                        existing.label = req.label
                    existing = _chart_store.save(existing)
                return ChartResponse(**existing.to_dict())
        try:
            rec = ChartRecord.create(
                bazi=bazi,
                gender=req.gender,
                birth_date=req.birth_date,
                birth_time=req.birth_time,
                calendar_type=req.calendar_type,
                location=req.location,
                label=req.label,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        rec = _chart_store.save(rec)
        return ChartResponse(**rec.to_dict())

    @app.get("/api/v1/charts", response_model=List[ChartResponse])
    async def list_charts(limit: int = 50) -> List[ChartResponse]:
        if _chart_store is None:
            raise HTTPException(status_code=503, detail="chart store not available")
        return [ChartResponse(**c.to_dict()) for c in _chart_store.list(limit=limit)]

    @app.get("/api/v1/charts/{chart_id}", response_model=ChartResponse)
    async def get_chart(chart_id: str) -> ChartResponse:
        if _chart_store is None:
            raise HTTPException(status_code=503, detail="chart store not available")
        rec = _chart_store.get(chart_id.strip())
        if rec is None:
            raise HTTPException(status_code=404, detail="chart not found")
        return ChartResponse(**rec.to_dict())

    @app.delete("/api/v1/charts/{chart_id}")
    async def delete_chart(chart_id: str) -> Dict[str, Any]:
        if _chart_store is None:
            raise HTTPException(status_code=503, detail="chart store not available")
        ok = _chart_store.delete(chart_id.strip())
        if not ok:
            raise HTTPException(status_code=404, detail="chart not found")
        return {"deleted": True, "id": chart_id}

    @app.post("/api/v1/charts/{chart_id}/export/package")
    async def export_chart_package(
        chart_id: str,
        req: PackageExportOptions = PackageExportOptions(),
    ) -> Dict[str, Any]:
        """Standard product package: 命书 markdown + HTML (print to PDF) + 择日."""
        opts = req
        if _chart_store is None:
            # Allow legacy bazi-as-id without store for export
            bazi = chart_id.strip()
            gender = "male"
            birth_info: Dict[str, Any] = {}
            label = bazi
            cid = ""
        else:
            from tools.destiny.chart_store import is_chart_uuid

            key = chart_id.strip()
            if is_chart_uuid(key):
                rec = _chart_store.get(key)
                if rec is None:
                    raise HTTPException(status_code=404, detail="chart not found")
                bazi, gender = rec.bazi, rec.gender
                birth_info = {
                    "birth_date": rec.birth_date,
                    "birth_time": rec.birth_time,
                    "calendar_type": rec.calendar_type,
                }
                label, cid = rec.label, rec.id
            else:
                bazi, gender, birth_info, label, cid = key, "male", {}, key, ""

        from tools.bazi_ai.report_export import build_product_package

        return build_product_package(
            bazi,
            gender=gender,
            birth_info=birth_info,
            chart_id=cid,
            label=label,
            include_auspicious=True,
            liunian_start_year=opts.liunian_start_year,
            liunian_years=opts.liunian_years,
        )

    @app.post("/api/v1/bazi/export/package")
    async def export_bazi_package(req: BaziPackageExportRequest) -> Dict[str, Any]:
        """Export product package from raw birth/bazi payload (no UUID required)."""
        from tools.bazi_ai.report_export import build_product_package

        return build_product_package(
            req.bazi.strip(),
            gender=req.gender,
            birth_info={
                "birth_date": req.birth_date,
                "birth_time": req.birth_time,
                "calendar_type": req.calendar_type,
            },
            label=req.label or req.bazi.strip(),
            include_auspicious=True,
            liunian_start_year=req.liunian_start_year,
            liunian_years=req.liunian_years,
        )

    # ------------------------------------------------------------------
    # Product: analytics funnel + entitlements + demo charts
    # ------------------------------------------------------------------
    @app.get("/api/v1/product/demo-charts")
    async def product_demo_charts() -> Dict[str, Any]:
        """Curated sample charts for one-click product demos (no auth)."""
        from tools.destiny.demo_charts import list_demo_charts

        items = list_demo_charts()
        return {
            "count": len(items),
            "items": items,
            "note": "结构层演示样例；可直接用于流年/紫微/七政/交付包导出。",
            "pricing_demo_code": "demo-pro",
        }

    @app.get("/api/v1/product/demo-charts/{demo_id}")
    async def product_demo_chart_detail(demo_id: str) -> Dict[str, Any]:
        from tools.destiny.demo_charts import get_demo_chart

        demo = get_demo_chart(demo_id)
        if demo is None:
            raise HTTPException(status_code=404, detail="demo chart not found")
        return demo

    @app.post("/api/v1/product/demo-charts/{demo_id}/package")
    async def product_demo_chart_package(
        demo_id: str,
        req: PackageExportOptions = PackageExportOptions(),
    ) -> Dict[str, Any]:
        """Build a product package for a fixed demo chart (structure layer)."""
        from tools.bazi_ai.report_export import build_product_package
        from tools.destiny.demo_charts import demo_chart_as_birth_payload, get_demo_chart

        demo = get_demo_chart(demo_id)
        if demo is None:
            raise HTTPException(status_code=404, detail="demo chart not found")
        payload = demo_chart_as_birth_payload(demo)
        return build_product_package(
            payload["bazi"],
            gender=payload["gender"],
            birth_info={
                "birth_date": payload["birth_date"],
                "birth_time": payload["birth_time"],
                "calendar_type": payload["calendar_type"],
            },
            label=payload["label"],
            include_auspicious=True,
            liunian_start_year=req.liunian_start_year,
            liunian_years=req.liunian_years,
            chart_id=f"demo:{demo_id}",
        )

    @app.post("/api/v1/product/track")
    async def product_track(req: TrackEventRequest) -> Dict[str, Any]:
        if _product_store is None:
            raise HTTPException(status_code=503, detail="product store not available")
        eid = _product_store.track(
            req.event,
            device_id=req.device_id,
            chart_id=req.chart_id,
            props=req.props,
        )
        return {"id": eid, "ok": True}

    @app.get("/api/v1/product/funnel")
    async def product_funnel(request: Request, days: int = 7) -> Dict[str, Any]:
        if _product_store is None:
            raise HTTPException(status_code=503, detail="product store not available")
        # Public read for demo; when admin token set, require it for privacy.
        if _admin_token:
            _require_admin(request)
        import time as _time

        days = max(1, min(int(days or 7), 90))
        since = int(_time.time()) - days * 86400
        summary = _product_store.funnel_summary(since_unix=since)
        summary["days"] = days
        return summary

    @app.get("/api/v1/admin/overview")
    async def admin_overview(request: Request, days: int = 7) -> Dict[str, Any]:
        """Admin dashboard payload: funnel + payments + entitlements + charts."""
        _require_admin(request)
        if _product_store is None:
            raise HTTPException(status_code=503, detail="product store not available")
        import time as _time

        days = max(1, min(int(days or 7), 90))
        since = int(_time.time()) - days * 86400
        funnel = _product_store.funnel_summary(since_unix=since)
        funnel["days"] = days
        payments_summary = _product_store.payment_summary(since_unix=since)
        payments_summary["days"] = days
        charts = []
        if _chart_store is not None:
            charts = [c.to_dict() for c in _chart_store.list(limit=30)]
        return {
            "funnel": funnel,
            "payments_summary": payments_summary,
            "recent_payments": _product_store.list_payments(
                limit=40, since_unix=since
            ),
            "recent_events": _product_store.recent_events(limit=40),
            "entitlements": _product_store.list_entitlements(limit=30),
            "charts": charts,
            "admin_auth_required": bool(_admin_token),
            "demo_code_configured": bool(_demo_code),
            "webhook_secret_configured": bool(_webhook_secret),
        }

    @app.post("/api/v1/admin/entitlement/grant")
    async def admin_grant_entitlement(
        request: Request, req: AdminGrantRequest
    ) -> Dict[str, Any]:
        """Manually grant pro or package credits (ops tooling)."""
        _require_admin(request)
        if _product_store is None:
            raise HTTPException(status_code=503, detail="product store not available")
        device_id = (req.device_id or "").strip()
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id required")
        try:
            rec = _product_store.admin_grant(
                device_id,
                action=req.action,
                days=max(1, min(req.days, 365)),
                credits=max(1, min(req.credits, 50)),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "entitlement": rec.to_dict()}

    @app.post("/api/v1/product/checkout")
    async def product_checkout(req: CheckoutRequest) -> Dict[str, Any]:
        """Closed-loop checkout (demo provider): ledger + entitlement.

        Production adapters should create a pending order with the PSP and
        fulfill via ``/product/payment/webhook``; this path is for demo smoke
        and local e2e without an external gateway.
        """
        if _product_store is None:
            raise HTTPException(status_code=503, detail="product store not available")
        device_id = (req.device_id or "").strip()
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id required")
        product = (req.product or "pro").strip().lower()
        if product not in (
            "pro",
            "pro_month",
            "subscription_pro",
            "mingmirror_pro",
            "credit",
            "package",
            "package_1",
            "mingmirror_package",
        ):
            raise HTTPException(
                status_code=400,
                detail="product must be pro or package (or known SKU aliases)",
            )
        result = _product_store.checkout(
            device_id=device_id,
            product=product,
            provider=req.provider or "demo",
            amount_cents=req.amount_cents,
            currency=req.currency or "CNY",
            days=max(1, min(req.days, 365)),
            credits=max(1, min(req.credits, 50)),
            external_id=req.external_id or "",
        )
        return result

    @app.get("/api/v1/product/payments")
    async def product_list_payments(
        device_id: str = "",
        limit: int = 20,
    ) -> Dict[str, Any]:
        """List payments for a device (user self-serve history)."""
        if _product_store is None:
            raise HTTPException(status_code=503, detail="product store not available")
        if not (device_id or "").strip():
            raise HTTPException(status_code=400, detail="device_id required")
        items = _product_store.list_payments(
            device_id=device_id.strip(), limit=max(1, min(limit, 50))
        )
        return {"device_id": device_id.strip(), "count": len(items), "items": items}

    @app.get("/api/v1/product/payment/status")
    async def product_payment_status(
        provider: str = "demo",
        external_id: str = "",
    ) -> Dict[str, Any]:
        """Lookup a payment by provider + external order id."""
        if _product_store is None:
            raise HTTPException(status_code=503, detail="product store not available")
        if not (external_id or "").strip():
            raise HTTPException(status_code=400, detail="external_id required")
        row = _product_store.get_payment(
            provider=provider or "demo", external_id=external_id.strip()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="payment not found")
        ent = _product_store.get_entitlement(row["device_id"]).to_dict()
        return {"payment": row, "entitlement": ent}

    @app.post("/api/v1/product/payment/webhook")
    async def payment_webhook(
        request: Request, req: PaymentWebhookRequest
    ) -> Dict[str, Any]:
        """Payment provider webhook → entitlement.

        Idempotent on (provider, external_id). Wire Stripe/LemonSqueezy/wechat
        by mapping their payload into PaymentWebhookRequest in a thin adapter.
        """
        _require_webhook(request)
        if _product_store is None:
            raise HTTPException(status_code=503, detail="product store not available")
        if (req.status or "succeeded").lower() not in (
            "succeeded",
            "success",
            "paid",
            "complete",
            "completed",
        ):
            return {"ok": False, "reason": f"ignored status={req.status}"}
        try:
            ledger = _product_store.record_payment(
                provider=req.provider,
                external_id=req.external_id,
                device_id=req.device_id,
                product=req.product,
                amount_cents=req.amount_cents,
                currency=req.currency,
                status=req.status,
                raw=req.raw or req.model_dump(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if ledger.get("duplicate"):
            ent = _product_store.get_entitlement(req.device_id).to_dict()
            return {
                "ok": True,
                "duplicate": True,
                "payment_id": ledger.get("payment_id"),
                "entitlement": ent,
            }

        ent_rec = _product_store.apply_payment_product(
            req.device_id,
            req.product,
            days=max(1, min(req.days, 365)),
            credits=max(1, min(req.credits, 50)),
        )
        _product_store.track(
            "payment_webhook",
            device_id=req.device_id,
            props={
                "provider": req.provider,
                "product": req.product,
                "external_id": req.external_id,
                "amount_cents": req.amount_cents,
            },
        )
        return {
            "ok": True,
            "duplicate": False,
            "payment_id": ledger.get("payment_id"),
            "entitlement": ent_rec.to_dict(),
        }

    @app.get("/api/v1/product/entitlement")
    async def product_get_entitlement(device_id: str) -> Dict[str, Any]:
        if _product_store is None:
            raise HTTPException(status_code=503, detail="product store not available")
        if not (device_id or "").strip():
            raise HTTPException(status_code=400, detail="device_id required")
        return _product_store.get_entitlement(device_id.strip()).to_dict()

    @app.post("/api/v1/product/entitlement/activate")
    async def product_activate(req: EntitlementActivateRequest) -> Dict[str, Any]:
        """Demo activation. Production: replace with payment webhook."""
        if _product_store is None:
            raise HTTPException(status_code=503, detail="product store not available")
        device_id = (req.device_id or "").strip()
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id required")
        action = (req.action or "pro").strip().lower()
        code = (req.code or "").strip()
        # Allow empty code only for credit; pro requires demo code
        if action == "pro":
            if code != _demo_code:
                raise HTTPException(
                    status_code=403,
                    detail="invalid activation code",
                )
            rec = _product_store.activate_pro(device_id, days=max(1, min(req.days, 365)))
            _product_store.track(
                "pro_activated", device_id=device_id, props={"days": req.days}
            )
            return {"ok": True, "entitlement": rec.to_dict()}
        if action == "credit":
            # Soft gate: accept demo code or empty in non-strict demo mode
            if code and code != _demo_code:
                raise HTTPException(status_code=403, detail="invalid activation code")
            rec = _product_store.add_credits(device_id, n=max(1, min(req.credits, 20)))
            _product_store.track(
                "credit_purchased",
                device_id=device_id,
                props={"credits": req.credits},
            )
            return {"ok": True, "entitlement": rec.to_dict()}
        raise HTTPException(status_code=400, detail="action must be pro or credit")

    @app.post("/api/v1/product/entitlement/consume")
    async def product_consume(req: EntitlementConsumeRequest) -> Dict[str, Any]:
        if _product_store is None:
            raise HTTPException(status_code=503, detail="product store not available")
        device_id = (req.device_id or "").strip()
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id required")
        result = _product_store.consume_credit(device_id)
        if result.get("ok"):
            _product_store.track(
                "package_export",
                device_id=device_id,
                props={"reason": result.get("reason")},
            )
        else:
            _product_store.track(
                "package_export_blocked",
                device_id=device_id,
                props={"reason": result.get("reason")},
            )
        return result

    @app.post("/api/v1/charts/{chart_id}/events", response_model=EventResponse)
    async def create_event(chart_id: str, req: EventCreateRequest) -> EventResponse:
        """Record a life event for a given chart (UUID or legacy bazi)."""
        if _calibrator is None or _event_store is None:
            raise HTTPException(
                status_code=503,
                detail="event calibration subsystem not available",
            )
        scope_key, _bazi = _resolve_chart_scope(chart_id)
        try:
            from tools.destiny.calibrator import LifeEvent

            event = LifeEvent.create(
                chart_id=scope_key,
                event_type=req.event_type,
                happened_at=req.happened_at,
                description=req.description,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _event_store.add(event)
        return EventResponse(
            id=event.id,
            chart_id=event.chart_id,
            event_type=event.event_type,
            happened_at=event.happened_at,
            description=event.description,
        )

    @app.get("/api/v1/charts/{chart_id}/events", response_model=List[EventResponse])
    async def list_events(chart_id: str) -> List[EventResponse]:
        """List recorded life events for a given chart."""
        if _calibrator is None or _event_store is None:
            raise HTTPException(
                status_code=503,
                detail="event calibration subsystem not available",
            )
        scope_key, _bazi = _resolve_chart_scope(chart_id)
        return [
            EventResponse(
                id=e.id,
                chart_id=e.chart_id,
                event_type=e.event_type,
                happened_at=e.happened_at,
                description=e.description,
            )
            for e in _event_store.list(scope_key)
        ]

    @app.delete("/api/v1/charts/{chart_id}/events/{event_id}")
    async def delete_event(chart_id: str, event_id: str) -> Dict[str, Any]:
        """Delete a recorded life event."""
        if _event_store is None:
            raise HTTPException(
                status_code=503,
                detail="event calibration subsystem not available",
            )
        scope_key, _bazi = _resolve_chart_scope(chart_id)
        ok = _event_store.delete(scope_key, event_id.strip())
        if not ok:
            raise HTTPException(status_code=404, detail="event not found")
        return {"deleted": True, "id": event_id}

    @app.post("/api/v1/charts/{chart_id}/calibrate", response_model=CalibrationResponse)
    async def calibrate_chart(chart_id: str) -> CalibrationResponse:
        """Calibrate destiny system weights against recorded events."""
        if _calibrator is None or _event_store is None:
            raise HTTPException(
                status_code=503,
                detail="event calibration subsystem not available",
            )
        from tools.destiny.contract import ChartInfo

        scope_key, bazi = _resolve_chart_scope(chart_id)
        chart = ChartInfo(bazi=bazi)
        result = await _calibrator.calibrate(
            chart, storage_key=scope_key
        )
        return CalibrationResponse(
            chart_id=scope_key,
            event_count=result["event_count"],
            average_score=result["average_score"],
            system_scores=result["system_scores"],
            adjusted_weights=result["adjusted_weights"],
            suggested_hour_offset=result.get("suggested_hour_offset"),
            events=result.get("events", []),
            calibration_id=result.get("calibration_id"),
        )

    @app.get("/api/v1/charts/{chart_id}/calibrate/latest", response_model=CalibrationResponse)
    async def latest_calibration(chart_id: str) -> CalibrationResponse:
        """Return the most recently persisted calibration for a chart."""
        if _event_store is None:
            raise HTTPException(
                status_code=503,
                detail="event calibration subsystem not available",
            )
        latest_fn = getattr(_event_store, "latest_calibration", None)
        if not callable(latest_fn):
            raise HTTPException(
                status_code=501,
                detail="event store does not support calibration history",
            )
        scope_key, _bazi = _resolve_chart_scope(chart_id)
        result = latest_fn(scope_key)
        if not result:
            raise HTTPException(status_code=404, detail="no calibration found")
        return CalibrationResponse(
            chart_id=result["chart_id"],
            event_count=result["event_count"],
            average_score=result["average_score"],
            system_scores=result["system_scores"],
            adjusted_weights=result["adjusted_weights"],
            suggested_hour_offset=result.get("suggested_hour_offset"),
            events=result.get("events", []),
            calibration_id=result.get("id"),
            created_at=result.get("created_at"),
        )

    @app.post("/api/v1/bazi/compatibility")
    async def bazi_compatibility(req: CompatibilityRequest) -> Dict[str, Any]:
        """双盘合婚结构评分 + 可选共同择日/.ics(零 LLM)。"""
        try:
            from tools.bazi_ai.hehun import compare_charts
        except Exception as exc:  # pragma: no cover
            raise HTTPException(
                status_code=503,
                detail=f"compatibility subsystem not available: {exc}",
            ) from exc

        from datetime import date as _date

        date_from = None
        date_to = None
        try:
            if req.date_from:
                date_from = _date.fromisoformat(req.date_from)
            if req.date_to:
                date_to = _date.fromisoformat(req.date_to)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid date format: {exc}"
            ) from exc

        result = compare_charts(
            req.bazi_a.strip(),
            req.gender_a,
            req.bazi_b.strip(),
            req.gender_b,
            include_joint_days=req.include_joint_days,
            include_ics=req.include_ics,
            event_type=req.event_type,
            date_from=date_from,
            date_to=date_to,
            top_n=req.top_n,
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    # Serve the bundled frontend web UI under /app; redirect root to it.
    # Prefer the modern React build in web/dist; fall back to the legacy
    # frontend/ directory if the React app has not been built yet.
    web_dist_dir = Path(__file__).resolve().parents[1] / "web" / "dist"
    frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
    static_dir = web_dist_dir if web_dist_dir.is_dir() else frontend_dir
    if static_dir.is_dir():
        app.mount("/app", _SPAStaticFiles(directory=str(static_dir), html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/app/")

    return app


async def run_server(config: ConfigLoader, *, host: str, port: int) -> None:
    import uvicorn

    app = build_app(config)
    uv_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(uv_config)
    await server.serve()
