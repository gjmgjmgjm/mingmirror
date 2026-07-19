#!/usr/bin/env python3
"""Process-wide concurrency limiters for API + AI workloads."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


@dataclass
class ConcurrencyHub:
    """Shared semaphores for backend workloads.

    - ``ai``: LLM / heavy bazi/ziwei/council analyzes
    - ``export``: report / package export
    - ``download``: left to JobManager; exposed for metrics only
    """

    ai_limit: int = 4
    export_limit: int = 2
    _ai: asyncio.Semaphore = field(init=False)
    _export: asyncio.Semaphore = field(init=False)
    ai_inflight: int = 0
    export_inflight: int = 0
    ai_rejected: int = 0

    def __post_init__(self) -> None:
        self._ai = asyncio.Semaphore(max(1, int(self.ai_limit)))
        self._export = asyncio.Semaphore(max(1, int(self.export_limit)))

    @asynccontextmanager
    async def ai_slot(self, *, timeout: Optional[float] = 60.0) -> AsyncIterator[None]:
        try:
            if timeout is None:
                await self._ai.acquire()
            else:
                await asyncio.wait_for(self._ai.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            self.ai_rejected += 1
            raise TimeoutError("AI concurrency limit; retry later")
        self.ai_inflight += 1
        try:
            yield
        finally:
            self.ai_inflight = max(0, self.ai_inflight - 1)
            self._ai.release()

    @asynccontextmanager
    async def export_slot(self, *, timeout: Optional[float] = 30.0) -> AsyncIterator[None]:
        try:
            if timeout is None:
                await self._export.acquire()
            else:
                await asyncio.wait_for(self._export.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError("export concurrency limit; retry later")
        self.export_inflight += 1
        try:
            yield
        finally:
            self.export_inflight = max(0, self.export_inflight - 1)
            self._export.release()

    def stats(self) -> dict:
        return {
            "ai_limit": self.ai_limit,
            "export_limit": self.export_limit,
            "ai_inflight": self.ai_inflight,
            "export_inflight": self.export_inflight,
            "ai_rejected": self.ai_rejected,
        }


# Process singleton (overwritten in build_app if config overrides)
hub = ConcurrencyHub()
