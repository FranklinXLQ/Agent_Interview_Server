"""应用启动时创建会话服务，运行期间定时清理过期历史。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.services.conversation import ConversationService
from app.settings.session_settings import SessionSettings
from app.storage.memory_session_store import MemorySessionStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """每个应用实例拥有独立内存存储，退出时取消后台清理任务。"""
    store = MemorySessionStore(SessionSettings())
    app.state.conversation_service = ConversationService(store)
    cleanup_task = asyncio.create_task(cleanup_sessions(store))
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


async def cleanup_sessions(store: MemorySessionStore) -> None:
    """周期清理无人使用的历史，新请求到达时也会执行惰性清理。"""
    while True:
        await asyncio.sleep(store.settings.cleanup_interval_seconds)
        store.cleanup_expired()
