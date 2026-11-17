"""对话业务：协调历史、模型流和正常完成后的整轮保存。"""

from collections.abc import AsyncGenerator
from contextlib import aclosing

from anyio.lowlevel import checkpoint
from openai.types.chat import ChatCompletionMessageParam

from app.config import DeepSeekSettings
from app.models.chat_request_context import ChatRequestContext
from app.services.deepseek import DeepSeekError
from app.services.deepseek_stream import stream_deepseek
from app.storage.memory_session_store import MemorySessionStore


class ConversationService:
    """向路由提供对话操作，模型服务本身不负责管理会话。"""

    def __init__(self, store: MemorySessionStore) -> None:
        """注入当前应用的会话存储，不使用跨应用的全局字典。"""
        self._store = store

    def begin_turn(self, session_id: str, message: str) -> ChatRequestContext:
        """在开始 SSE 前占用会话，让并发冲突可以返回 HTTP 错误。"""
        return self._store.begin_turn(session_id, message)

    def release_turn(self, context: ChatRequestContext) -> None:
        """流式响应退出时归还占用，不保存失败或中断的内容。"""
        self._store.release_turn(context)

    async def stream_reply(
        self,
        context: ChatRequestContext,
        settings: DeepSeekSettings,
    ) -> AsyncGenerator[str, None]:
        """边转发边累积回答，模型正常结束且未取消时才保存历史。"""
        messages = self._build_messages(context)
        answer_parts: list[str] = []
        answer_characters = 0

        async with aclosing(stream_deepseek(messages, settings)) as parts:
            async for text in parts:
                answer_characters += len(text)
                if answer_characters > self._store.settings.max_answer_characters:
                    raise DeepSeekError("回答超过长度限制，生成已中断")
                answer_parts.append(text)
                yield text

        answer = "".join(answer_parts)
        if not answer.strip():
            raise DeepSeekError("模型未返回有效回答")

        # 给断开连接的监听任务一次执行机会，取消后不提交本轮。
        await checkpoint()
        self._store.complete_turn(context, answer)

    def _build_messages(
        self,
        context: ChatRequestContext,
    ) -> list[ChatCompletionMessageParam]:
        """按用户、助手的时间顺序组装历史，最后追加当前问题。"""
        messages: list[ChatCompletionMessageParam] = []
        for turn in context.turns:
            messages.append({"role": "user", "content": turn.user})
            messages.append({"role": "assistant", "content": turn.assistant})
        messages.append({"role": "user", "content": context.message})
        return messages
