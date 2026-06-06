from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from .config import Settings
from .db import (
    fail_chat_job,
    get_effective_tool_enabled_map,
    get_messages,
    get_session_summary,
    list_memory_items,
    recover_chat_jobs,
    requeue_chat_job,
    start_chat_job_attempt,
    succeed_chat_job,
)
from .modes.schema import AssistantMode
from .pipeline import run_post_chat_pipeline
from .tools.base import ToolContext
from .tools.registry import ToolsRegistry
from .tools.runner import run_tools

logger = logging.getLogger(__name__)


class ChatJobEngine:
    """
    In-process background engine for post-chat jobs (pipeline + tools).
    """

    def __init__(
        self,
        *,
        settings: Settings,
        modes: Dict[str, AssistantMode],
        tools_registry: ToolsRegistry,
    ) -> None:
        self._settings = settings
        self._modes = modes
        self._tools_registry = tools_registry
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=settings.chat_jobs_queue_size)
        self._workers: list[asyncio.Task[Any]] = []
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        recover_ids = await recover_chat_jobs(limit=self._settings.chat_jobs_queue_size)
        for job_id in recover_ids:
            if not self.enqueue_nowait(job_id):
                logger.warning("chat_jobs queue full while recovering job=%s", job_id)
                break
        worker_count = max(1, int(self._settings.chat_jobs_worker_count))
        for idx in range(worker_count):
            task = asyncio.create_task(self._worker_loop(idx))
            self._workers.append(task)
        logger.info("chat_jobs started workers=%d recovered=%d", worker_count, len(recover_ids))

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("chat_jobs stopped")

    def enqueue_nowait(self, job_id: str) -> bool:
        try:
            self._queue.put_nowait(job_id)
            return True
        except asyncio.QueueFull:
            return False

    async def _worker_loop(self, worker_idx: int) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._process_job(job_id)
            except Exception as e:
                logger.error("chat_jobs worker=%d crashed on job=%s err=%s", worker_idx, job_id, e, exc_info=True)
            finally:
                self._queue.task_done()

    async def _process_job(self, job_id: str) -> None:
        job = await start_chat_job_attempt(job_id)
        if not job:
            return

        try:
            mode_obj = self._modes.get(job["mode_id"])
            if not mode_obj:
                raise RuntimeError(f"Mode not found: {job['mode_id']}")
            mode = mode_obj.model_dump()

            pipeline_result = await run_post_chat_pipeline(session_id=job["session_id"], mode=mode)
            tool_events = await self._run_tools(job, mode)
            await succeed_chat_job(job_id, pipeline_result=pipeline_result, tool_events=tool_events)
        except Exception as e:
            err = str(e)
            attempts = int(job.get("attempts", 0))
            max_retries = int(job.get("max_retries", self._settings.chat_jobs_max_retries))
            if attempts <= max_retries:
                await requeue_chat_job(job_id, err)
                backoff_s = min(2 ** max(0, attempts - 1), 8)
                asyncio.create_task(self._requeue_later(job_id, backoff_s))
            else:
                await fail_chat_job(job_id, err)

    async def _requeue_later(self, job_id: str, delay_s: int) -> None:
        await asyncio.sleep(delay_s)
        if self._running and not self.enqueue_nowait(job_id):
            await fail_chat_job(job_id, "queue_full_after_retry")

    async def _run_tools(self, job: Dict[str, Any], mode: Dict[str, Any]) -> list[dict]:
        mem_items: list[dict] = []
        mem_policy = mode.get("memory_policy", {})
        if mem_policy.get("enabled"):
            scope = mem_policy.get("scope", "session")
            if scope == "global":
                mem_items = await list_memory_items(scope="global", session_id=None, limit=50)
            else:
                global_mem, session_mem = await asyncio.gather(
                    list_memory_items(scope="global", session_id=None, limit=50),
                    list_memory_items(scope="session", session_id=job["session_id"], limit=50),
                )
                mem_items = global_mem + session_mem

        tool_ids = [t.id for t in self._tools_registry.list_tools()]
        enabled_map, msgs_latest, session_summary = await asyncio.gather(
            get_effective_tool_enabled_map(job["session_id"], tool_ids),
            get_messages(job["session_id"], limit=50),
            get_session_summary(job["session_id"]),
        )

        recent10 = [{"role": m["role"], "content": m["content"]} for m in msgs_latest][-10:]
        assistant_final = job.get("assistant_final", "")
        if not assistant_final:
            for m in reversed(msgs_latest):
                if m.get("role") == "assistant":
                    assistant_final = m.get("content", "")
                    break

        tool_ctx = ToolContext(
            session_id=job["session_id"],
            mode=mode,
            memory_items=mem_items,
            session_summary=session_summary,
            recent_messages=recent10,
            user_message=job.get("user_message", ""),
            assistant_final=assistant_final,
        )
        return await asyncio.to_thread(run_tools, self._tools_registry, tool_ctx, enabled_map)
