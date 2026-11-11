"""为 SSE 响应统一处理断开监听、生成器关闭和会话释放。"""

from collections.abc import AsyncGenerator, Callable

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send


class ChatStreamingResponse(StreamingResponse):
    """在整个响应生命周期监听断开，确保请求占用和上游连接被清理。"""

    def __init__(self, content: AsyncGenerator[str, None], on_close: Callable[[], None]) -> None:
        """绑定唯一生成器及清理动作，清理动作必须可重复调用。"""
        super().__init__(
            content,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        self._content = content
        self._on_close = on_close

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """让发送和断开监听并行，任一结束后取消另一任务。"""
        try:
            async with anyio.create_task_group() as group:
                group.start_soon(self._send_and_close, send, group.cancel_scope)
                try:
                    await self.listen_for_disconnect(receive)
                finally:
                    group.cancel_scope.cancel()
        finally:
            # 包括响应头发送失败、首个事件前断开等情况。
            self._on_close()

    async def _send_and_close(
        self,
        send: Send,
        cancel_scope: anyio.CancelScope,
    ) -> None:
        """在发送任务内关闭生成器，避免异常悬停在 yield 后泄漏连接。"""
        try:
            await self.stream_response(send)
        except OSError:
            # ASGI 服务器也可能通过发送失败通知连接断开。
            pass
        finally:
            try:
                # 断开会取消任务；清理阶段屏蔽重复取消，显式关闭整条生成器链。
                with anyio.CancelScope(shield=True):
                    await self._content.aclose()
            finally:
                self._on_close()
                cancel_scope.cancel()
