"""流式对话路由：校验请求、处理会话占用并输出 SSE。"""

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.chat_stream_response import ChatStreamingResponse
from app.api.dependencies import get_conversation_service
from app.config import DeepSeekSettings, get_deepseek_settings
from app.models.chat_request_context import ChatRequestContext
from app.schemas.chat_stream import ChatStreamRequest
from app.services.conversation import ConversationService
from app.services.deepseek import DeepSeekError
from app.errors.session_error import SessionError


router = APIRouter(tags=["问答"])
logger = logging.getLogger(__name__)


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "SSE：delta 为文本增量，done 表示本轮已保存，error 为生成失败。",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        409: {"description": "同一会话已有正在生成的回答。"},
        503: {"description": "模型密钥未配置，或内存会话数量达到上限。"},
    },
)
async def chat_stream(
    request: ChatStreamRequest,
    settings: Annotated[DeepSeekSettings, Depends(get_deepseek_settings)],
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> StreamingResponse:
    """在响应开始前检查配置并占用会话，保持普通 POST /chat 不变。"""
    if not settings.api_key:
        raise HTTPException(status_code=503, detail="服务端未配置 DEEPSEEK_API_KEY")

    try:
        context = service.begin_turn(str(request.session_id), request.message)
    except SessionError as error:
        status_code = 409 if error.reason == "busy" else 503
        raise HTTPException(status_code=status_code, detail=str(error)) from None

    try:
        return ChatStreamingResponse(
            send_chat_events(context, settings, service),
            on_close=lambda: service.release_turn(context),
        )
    except BaseException:
        service.release_turn(context)
        raise


async def send_chat_events(
    context: ChatRequestContext,
    settings: DeepSeekSettings,
    service: ConversationService,
) -> AsyncGenerator[str, None]:
    """转发增量，业务层提交成功后才发送 done；取消时不发送 error。"""
    try:
        async with aclosing(service.stream_reply(context, settings)) as parts:
            async for text in parts:
                yield format_event("delta", {"text": text})
    except DeepSeekError as error:
        service.release_turn(context)
        yield format_event("error", {"message": str(error)})
    except Exception as error:
        service.release_turn(context)
        # 只记录类型，避免密钥或会话内容进入日志。
        logger.error("流式对话发生未预期异常，类型：%s", type(error).__name__)
        yield format_event("error", {"message": "生成回答时发生异常，请稍后重试"})
    else:
        yield format_event("done", {})


def format_event(event: str, data: dict[str, str]) -> str:
    """通过 JSON 编码正文并以空行分隔 SSE 事件。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
